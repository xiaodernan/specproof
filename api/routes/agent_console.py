"""SpecCraft Web Agent Console API (商业化计划书任务 8, U 车道).

Endpoints (all key-protected and rate limited like /jobs and /api/v1/*):

  POST /agent/jobs                    create an agent job (repo_path + spec_text)
  GET  /agent/jobs                    list jobs, optional ?status= filter
  GET  /agent/jobs/{job_id}           detail (status, plan, progress, result)
  POST /agent/jobs/{job_id}/cancel    cancel a non-terminal job
  POST /agent/jobs/{job_id}/approve   approval decision (approve/reject + note)
  GET  /agent/jobs/{job_id}/approvals list approval records for a job
  GET  /agent/jobs/{job_id}/events    SSE stream (plan/tool_call/tool_result/
                                      edit/gate/progress; closes after terminal)
  GET  /agent/jobs/{job_id}/diff      structured diff of the change bundle

Strict create allowlist (backlog #8): POST /agent/jobs accepts only
repo_path / spec_text / task_name / auto_start. Any other payload key —
including tool/command/env/docker-style parameters — is refused with
422 VALIDATION_FAILED naming the offending field(s), never silently
dropped.

Persistence: durable job projections live in storage/agent_jobs.py (the W30
Agent-Plan task 3 module — InMemory/SQLite/MySQL backends behind one
protocol with create/get/list/update_status/set_plan/set_progress/lease/
renew/release/cancel). The backend is chosen at import via
SPECPROOF_AGENT_JOBS_URL ("" = in-memory; "sqlite:<path>" = SQLite;
"mysql://..." = MySQL) and fails closed on an unknown scheme. Console-only
state that the job store deliberately does not own — repo_path/task_name
metadata, the SSE event log, approval records and the change bundle — is
kept in a process-local _ConsoleState beside it.

Console status vocabulary is a stable API surface mapped onto the store's
statuses: PLANNING/AWAITING_APPROVAL → pending, EXECUTING → running,
COMPLETED → succeeded, FAILED → failed, CANCELLED → cancelled. The store's
cancel is an unconditional override, so this module enforces the HTTP-level
rule itself: cancelling a terminal job is 409 STATE_CONFLICT.

Error responses use the §8.1 envelope via ApiError (codes from api/errors.py,
never new codes): JOB_NOT_FOUND / STATE_CONFLICT / VALIDATION_FAILED /
EVIDENCE_UNVERIFIED / PROVIDER_UNAVAILABLE. Nothing is fabricated: missing
plans/bundles are honest errors.

Run-time execution (W42): a create request with auto_start=true hands the
job to api/agent_runtime.py, which runs a real deterministic CraftLoop (no
LLM / network / Docker) in a daemon thread — the caller's repo+spec when
both are given, the bundled api/_agent_demo task otherwise. Live
plan/tool/gate/progress events enter the SSE log through emit_event; the
loop's own store wiring projects plan/progress/result and the post-hoc
accept gate summary (attach_accept_result, W35.1). auto_start defaults to
False, keeping the passive W31 projection and approval workflow untouched.
"""

from __future__ import annotations

import asyncio
import builtins
import difflib
import json
import logging
import os
import threading
import uuid
from collections.abc import AsyncGenerator
from contextlib import suppress
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal, Protocol, Self, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from api._agent_demo import DEMO_SPEC_TEXT
from api.auth import enforce_rate_limit, require_api_key
from api.errors import (
    EVIDENCE_UNVERIFIED,
    JOB_NOT_FOUND,
    PROVIDER_UNAVAILABLE,
    STATE_CONFLICT,
    ApiError,
)
from storage.agent_jobs import (
    TERMINAL_JOB_STATUSES,
    AgentJob,
    AgentJobStore,
    AgentJobStoreError,
    InMemoryAgentJobStore,
    InvalidJobTransitionError,
    JobNotFoundError,
    MySqlAgentJobStore,
    SqliteAgentJobStore,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/agent",
    tags=["agent-console"],
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)

# ── Console status vocabulary (stable API surface) ──────────────────────────
# PLANNING → AWAITING_APPROVAL → EXECUTING → COMPLETED; FAILED/CANCELLED
# anywhere. Derived from the store projection (see _console_status).

_CANCELLABLE_STATUSES = frozenset({"PLANNING", "AWAITING_APPROVAL", "EXECUTING"})
_TERMINAL_CONSOLE_STATUSES = frozenset({"COMPLETED", "FAILED", "CANCELLED"})

#: Event types carried by the SSE stream (plus "progress").
EVENT_TYPES = ("plan", "tool_call", "tool_result", "edit", "gate", "progress")

#: Human-readable status labels mirrored by the SPA timeline.
STATUS_LABELS: dict[str, str] = {
    "PLANNING": "规划中 Planning",
    "AWAITING_APPROVAL": "等待计划审批 Awaiting approval",
    "EXECUTING": "执行中 Executing",
    "COMPLETED": "已完成 Completed",
    "FAILED": "失败 Failed",
    "CANCELLED": "已取消 Cancelled",
}

#: Console status filter → store status (see _store_status_for_filter).
_CONSOLE_TO_STORE_STATUS: dict[str, str] = {
    "PLANNING": "pending",
    "AWAITING_APPROVAL": "pending",
    "EXECUTING": "running",
    "COMPLETED": "succeeded",
    "FAILED": "failed",
    "CANCELLED": "cancelled",
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _iso(epoch_seconds: float | None) -> str:
    if epoch_seconds is None:
        return _now_iso()
    return datetime.fromtimestamp(epoch_seconds, tz=UTC).isoformat()


# ── Console-only state (metadata / events / approvals / bundle) ─────────────


class _ConsoleState:
    """Process-local state the job store does not own.

    The durable projection (status/plan/progress/result/lease) lives in
    storage/agent_jobs.py; this object keeps the console's live-view extras:
    repo_path/task_name metadata, the SSE event log (monotonic seq per job),
    approval records and the change bundle rendered by the diff endpoint.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._meta: dict[str, dict[str, str]] = {}
        self._events: dict[str, builtins.list[dict[str, Any]]] = {}
        self._approvals: dict[str, builtins.list[dict[str, Any]]] = {}
        self._bundles: dict[str, builtins.list[dict[str, Any]]] = {}

    def set_meta(self, job_id: str, repo_path: str, task_name: str | None) -> None:
        with self._lock:
            self._meta[job_id] = {
                "repo_path": repo_path,
                "task_name": task_name or f"agent-{job_id[:8]}",
            }

    def meta_for(self, job_id: str) -> dict[str, str]:
        with self._lock:
            return dict(self._meta.get(job_id, {"repo_path": "", "task_name": job_id}))

    def record_event(self, job_id: str, etype: str, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            events = self._events.setdefault(job_id, [])
            event: dict[str, Any] = {
                "seq": len(events) + 1,
                "type": etype,
                "at": _now_iso(),
                "data": data,
            }
            events.append(event)
            return dict(event)

    def events_since(self, job_id: str, after_seq: int) -> builtins.list[dict[str, Any]]:
        with self._lock:
            events = self._events.get(job_id)
            if events is None:
                return []
            return [dict(e) for e in events if e["seq"] > after_seq]

    def events_count(self, job_id: str) -> int:
        with self._lock:
            return len(self._events.get(job_id, []))

    def record_approval(
        self,
        job_id: str,
        target: str,
        decision: str,
        note: str | None,
        step_index: int | None,
        actor: str = "console",
    ) -> dict[str, Any]:
        approval: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "job_id": job_id,
            "target": target,
            "step_index": step_index,
            "decision": decision,
            "note": note,
            "actor": actor,
            "created_at": _now_iso(),
        }
        with self._lock:
            self._approvals.setdefault(job_id, []).append(approval)
        self.record_event(job_id, "gate", {"approval": dict(approval)})
        return dict(approval)

    def approvals_for(self, job_id: str) -> builtins.list[dict[str, Any]]:
        with self._lock:
            return [dict(a) for a in self._approvals.get(job_id, [])]

    def approvals_count(self, job_id: str) -> int:
        with self._lock:
            return len(self._approvals.get(job_id, []))

    def set_bundle(self, job_id: str, files: builtins.list[dict[str, Any]]) -> None:
        with self._lock:
            self._bundles[job_id] = [dict(f) for f in files]
        self.record_event(
            job_id, "edit", {"bundle": {"files_changed": len(files)}}
        )

    def bundle_for(self, job_id: str) -> builtins.list[dict[str, Any]]:
        with self._lock:
            return [dict(f) for f in self._bundles.get(job_id, [])]


# ── Backend selection (storage/agent_jobs.py) ───────────────────────────────


def _build_backend() -> AgentJobStore:
    """Pick the durable backend from SPECPROOF_AGENT_JOBS_URL (fail closed)."""
    url = os.getenv("SPECPROOF_AGENT_JOBS_URL", "").strip()
    if not url:
        return InMemoryAgentJobStore()
    if url.startswith("sqlite:"):
        backend: AgentJobStore = SqliteAgentJobStore(url[len("sqlite:"):])
    elif url.startswith(("mysql://", "mysql+pymysql://")):
        backend = MySqlAgentJobStore(url)
    else:
        raise RuntimeError(
            "SPECPROOF_AGENT_JOBS_URL must be '', 'sqlite:<path>' or a "
            f"mysql:// URL (got {url!r}) — refusing to start with an "
            "unknown agent job store backend"
        )
    backend.ensure_schema()
    return backend


_store: AgentJobStore = _build_backend()
_state = _ConsoleState()


def get_store() -> AgentJobStore:
    """Durable agent job projection (storage/agent_jobs.py backend)."""
    return _store


def get_state() -> _ConsoleState:
    """Console-only live state (metadata/events/approvals/bundle)."""
    return _state


def emit_event(job_id: str, etype: str, data: dict[str, Any]) -> dict[str, Any]:
    """Append a live event to the console SSE log (public runtime entry).

    Additive convenience for external writers such as api/agent_runtime.py;
    _ConsoleState.record_event remains the single implementation, so every
    existing consumer keeps its exact behavior.
    """
    return get_state().record_event(job_id, etype, data)


if TYPE_CHECKING:
    from api.agent_runtime import AgentRuntime

_runtime: AgentRuntime | None = None
_runtime_lock = threading.Lock()


def get_runtime() -> AgentRuntime:
    """Process-wide AgentRuntime singleton (W42, lazy import avoids a cycle).

    The runtime resolves store/state through get_store()/get_state() at
    call time, so tests that monkeypatch the module globals are honored.
    """
    global _runtime
    runtime = _runtime
    if runtime is None:
        from api.agent_runtime import AgentRuntime

        with _runtime_lock:
            runtime = _runtime
            if runtime is None:
                runtime = _runtime = AgentRuntime()
    assert runtime is not None
    return runtime


# ── Request models ──────────────────────────────────────────────────────────


#: Documented POST /agent/jobs payload fields (backlog #8 hardening).
#: Anything else — including any tool/command/env/docker-style parameters —
#: is refused with 422 VALIDATION_FAILED instead of being silently dropped:
#: the agent console must never become an execution-directive surface.
AGENT_JOB_CREATE_ALLOWLIST = frozenset(
    {"repo_path", "spec_text", "task_name", "auto_start"}
)


class AgentJobCreateRequest(BaseModel):
    """Agent job submission payload (strict allowlist, backlog #8).

    Only repo_path / spec_text / task_name / auto_start are accepted; any
    other key — including tool/command/env/docker-style parameters — is
    rejected with 422 VALIDATION_FAILED naming the offending field(s), so
    execution directives can never ride along on a create request.
    """

    repo_path: str | None = Field(default=None, min_length=1, max_length=1024)
    spec_text: str | None = Field(default=None, min_length=1, max_length=200_000)
    task_name: str | None = Field(default=None, min_length=1, max_length=255)
    auto_start: bool = Field(
        default=False,
        description=(
            "start a real deterministic CraftLoop immediately (no LLM / network / "
            "Docker); uses repo_path+spec_text when both are given, otherwise the "
            "bundled calc.py demo task"
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _reject_unknown_fields(cls, data: Any) -> Any:
        """Refuse any payload key outside AGENT_JOB_CREATE_ALLOWLIST.

        Fail-closed (backlog #8): unknown keys are rejected with
        422 VALIDATION_FAILED and never silently ignored, unlike pydantic's
        default extra-field handling.
        """
        if isinstance(data, dict):
            unknown = sorted(
                str(key)
                for key in data
                if not isinstance(key, str) or key not in AGENT_JOB_CREATE_ALLOWLIST
            )
            if unknown:
                raise ValueError(f"Unknown field(s): {', '.join(unknown)}")
        return data

    @model_validator(mode="after")
    def _check_run_shape(self) -> Self:
        """auto_start wants repo+spec together, or neither (bundled demo)."""
        if self.auto_start:
            if (self.repo_path is None) != (self.spec_text is None):
                raise ValueError(
                    "auto_start 需要同时提供 repo_path+spec_text, "
                    "或两者都不提供 (使用内置 demo)"
                )
            return self
        if self.repo_path is None or self.spec_text is None:
            raise ValueError(
                "repo_path 与 spec_text 必填 (或开启 auto_start 使用内置 demo)"
            )
        return self


class ApprovalRequest(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=2000)
    target: Literal["plan", "step", "gate"] = Field(default="plan")
    step_index: int | None = Field(default=None, ge=0, le=11)


# ── Projection → API view helpers ───────────────────────────────────────────


def _console_status(job: AgentJob) -> str:
    if job.status == "pending":
        return "AWAITING_APPROVAL" if job.plan_json else "PLANNING"
    if job.status == "running":
        return "EXECUTING"
    if job.status == "succeeded":
        return "COMPLETED"
    if job.status == "failed":
        return "FAILED"
    return "CANCELLED"


def _store_status_for_filter(
    status: str | None,
) -> Literal["pending", "running", "succeeded", "failed", "cancelled"] | None:
    if not status:
        return None
    return cast(
        "Literal['pending', 'running', 'succeeded', 'failed', 'cancelled']",
        _CONSOLE_TO_STORE_STATUS[status],
    )


def _job_view(job: AgentJob) -> dict[str, Any]:
    """Merge the durable projection with console state into the API shape."""
    state = get_state()
    plan = json.loads(job.plan_json) if job.plan_json else None
    progress = json.loads(job.progress_json) if job.progress_json else None
    if progress is None:
        progress = {
            "percent": 0.0,
            "message": "Job created; planner not started",
            "updated_at": _iso(job.created_at),
        }
    result = json.loads(job.result_json) if job.result_json else None
    if result is None and job.status == "cancelled":
        result = {"verdict": "CANCELLED", "reason": job.error or "Cancelled by user"}
    meta = state.meta_for(job.id)
    return {
        "id": job.id,
        "task_name": meta["task_name"],
        "repo_path": meta["repo_path"],
        "spec_text": job.spec_text,
        "status": _console_status(job),
        "plan": plan,
        "progress": progress,
        "result": result,
        "worker_id": job.lease_owner,
        "created_at": _iso(job.created_at),
        "updated_at": _iso(job.updated_at),
        "events_count": state.events_count(job.id),
        "approvals_count": state.approvals_count(job.id),
    }


def _summary_view(job: AgentJob) -> dict[str, Any]:
    view = _job_view(job)
    plan = view["plan"]
    return {
        "id": job.id,
        "task_name": view["task_name"],
        "repo_path": view["repo_path"],
        "status": view["status"],
        "plan_steps": len(plan["steps"]) if plan else 0,
        "events_count": view["events_count"],
        "approvals_count": view["approvals_count"],
        "created_at": view["created_at"],
        "updated_at": view["updated_at"],
    }


def _job_or_404(job_id: str) -> AgentJob:
    try:
        job = get_store().get(job_id)
    except AgentJobStoreError as exc:
        raise ApiError(
            status_code=503,
            code=PROVIDER_UNAVAILABLE,
            detail=f"Agent job store unavailable: {exc}",
        ) from exc
    if job is None:
        raise ApiError(
            status_code=404,
            code=JOB_NOT_FOUND,
            detail=f"Agent job {job_id} not found",
        )
    return job


def _transition(
    job_id: str,
    status: Literal["running", "failed", "succeeded"],
    error: str | None = None,
    result_json: dict[str, Any] | None = None,
) -> AgentJob:
    """Map console-level transitions onto the store (honest 409 on conflicts)."""
    try:
        return get_store().update_status(
            job_id,
            status,
            error=error,
            result_json=result_json,
        )
    except InvalidJobTransitionError as exc:
        raise ApiError(
            status_code=409,
            code=STATE_CONFLICT,
            detail=str(exc),
        ) from exc
    except JobNotFoundError as exc:
        raise ApiError(
            status_code=404,
            code=JOB_NOT_FOUND,
            detail=f"Agent job {job_id} not found",
        ) from exc
    except AgentJobStoreError as exc:
        raise ApiError(
            status_code=503,
            code=PROVIDER_UNAVAILABLE,
            detail=f"Agent job store unavailable: {exc}",
        ) from exc


def _apply_approval(
    job: AgentJob, target: str, decision: str, note: str | None,
    step_index: int | None,
) -> None:
    """Mutate job state per the approval decision (status + plan + result)."""
    job_id = job.id
    if target == "step":
        if step_index is None:
            raise ApiError(
                status_code=422,
                code=STATE_CONFLICT,
                detail="step_index is required when target is 'step'",
            )
        plan = json.loads(job.plan_json) if job.plan_json else None
        if not plan or not plan.get("steps"):
            raise ApiError(
                status_code=409,
                code=STATE_CONFLICT,
                detail=f"Agent job {job_id} has no plan to approve step {step_index}",
            )
        steps = plan["steps"]
        if step_index >= len(steps):
            raise ApiError(
                status_code=422,
                code=STATE_CONFLICT,
                detail=f"step_index {step_index} out of range (plan has {len(steps)} steps)",
            )
        steps[step_index]["status"] = "approved" if decision == "approve" else "rejected"
        steps[step_index]["approval"] = {
            "decision": decision,
            "note": note,
            "at": _now_iso(),
        }
        get_store().set_plan(job_id, plan)
        if decision == "reject":
            reason = f"Plan step {step_index} rejected"
            _transition(
                job_id, "failed", error=reason,
                result_json={"verdict": "FAILED", "reason": reason},
            )
            return
        if all(s.get("status") == "approved" for s in steps):
            _transition(job_id, "running")
        return
    if target == "plan":
        if decision == "approve":
            _transition(job_id, "running")
            return
        reason = note or "Plan rejected"
        _transition(
            job_id, "failed", error=reason,
            result_json={"verdict": "FAILED", "reason": reason},
        )
        return
    # target == "gate"
    if decision == "approve":
        _transition(job_id, "succeeded", result_json={"verdict": "COMPLETED", "reason": note})
        return
    reason = note or "Gate rejected"
    _transition(
        job_id, "failed", error=reason,
        result_json={"verdict": "FAILED", "reason": reason},
    )


def _require_cancellable(job: AgentJob) -> None:
    status = _console_status(job)
    if status in _TERMINAL_CONSOLE_STATUSES:
        raise ApiError(
            status_code=409,
            code=STATE_CONFLICT,
            detail=f"Agent job {job.id} is {status} — cannot cancel a terminal job",
        )


def _start_runtime_job(
    job_id: str, repo_path: str, spec_text: str, task_name: str | None
) -> None:
    """Kick off the deterministic runtime thread (best effort).

    The runtime thread owns every honest failure projection (store terminal
    write + SSE event); a start() exception here degrades to a FAILED
    projection instead of breaking the 202 response shape.
    """
    try:
        get_runtime().start(job_id, repo_path, spec_text, task_name=task_name)
    except Exception as exc:  # noqa: BLE001 — a broken runtime must not fail the 202
        logger.exception("agent runtime failed to start")
        reason = f"agent runtime failed to start: {exc}"
        get_state().record_event(job_id, "progress", {"status": "FAILED", "message": reason})
        with suppress(Exception):
            _transition(
                job_id, "failed", error=reason,
                result_json={"verdict": "FAILED", "reason": reason},
            )


# ── Routes ──────────────────────────────────────────────────────────────────


@router.post("/jobs", status_code=202)
async def create_agent_job(payload: AgentJobCreateRequest) -> dict[str, Any]:
    """Create an agent job (repo path + spec text) and return its id.

    The durable projection is created in storage/agent_jobs.py; the job
    starts pending (console status PLANNING). Accepted only once the store
    holds the row, mirroring the /jobs honesty rule.

    auto_start=True hands the job to AgentRuntime (api/agent_runtime.py),
    which runs a real deterministic CraftLoop in a daemon thread: the
    request's repo+spec when both are given, otherwise the bundled demo
    task. The response shape is unchanged either way.
    """
    job_id = str(uuid.uuid4())
    repo_path = payload.repo_path or ""
    spec_text = payload.spec_text or ""
    if payload.auto_start and not spec_text:
        spec_text = DEMO_SPEC_TEXT
    try:
        job = get_store().create(job_id, spec_text)
    except Exception as exc:  # noqa: BLE001 — backend down must reject honestly
        logger.exception("Failed to persist agent job")
        raise ApiError(
            status_code=503,
            code=PROVIDER_UNAVAILABLE,
            detail=f"Job NOT accepted — persistence failed: {exc}",
        ) from exc
    get_state().set_meta(job_id, repo_path, payload.task_name)
    get_state().record_event(job_id, "progress", {"status": "PLANNING", "message": "Job created"})
    if payload.auto_start:
        _start_runtime_job(job_id, repo_path, spec_text, payload.task_name)
    return {"job_id": job_id, "status": _console_status(job)}


@router.get("/jobs")
async def list_agent_jobs(status: str | None = None, limit: int = 200) -> dict[str, Any]:
    """List agent jobs, optionally filtered by exact console status."""
    if status is not None and status not in STATUS_LABELS:
        raise ApiError(
            status_code=422,
            code=STATE_CONFLICT,
            detail=f"Unknown status filter {status!r}",
        )
    store_status = _store_status_for_filter(status)
    try:
        rows = get_store().list(status=store_status, limit=limit)
    except AgentJobStoreError as exc:
        raise ApiError(
            status_code=503,
            code=PROVIDER_UNAVAILABLE,
            detail=f"Agent job store unavailable: {exc}",
        ) from exc
    summaries = [
        _summary_view(job)
        for job in rows
        if status != "PLANNING" or not job.plan_json
        if status != "AWAITING_APPROVAL" or job.plan_json
    ]
    return {"jobs": summaries, "count": len(summaries), "filter": {"status": status}}


@router.get("/jobs/{job_id}")
async def get_agent_job(job_id: str) -> dict[str, Any]:
    """Return full job detail: status, plan, progress, result, counts."""
    return {"job": _job_view(_job_or_404(job_id))}


@router.post("/jobs/{job_id}/cancel", status_code=202)
async def cancel_agent_job(job_id: str) -> dict[str, Any]:
    """Cancel a non-terminal agent job (terminal jobs are immutable here).

    The runtime is signalled first (cooperative cancel flag), then the
    durable override lands through the same AgentJobStore.cancel the
    passive projection always used — cancel wins even over a leased worker.
    """
    job = _job_or_404(job_id)
    _require_cancellable(job)
    try:
        get_runtime().cancel(job_id)
    except AgentJobStoreError as exc:
        raise ApiError(
            status_code=503,
            code=PROVIDER_UNAVAILABLE,
            detail=f"Agent job store unavailable: {exc}",
        ) from exc
    get_state().record_event(
        job_id, "progress", {"status": "CANCELLED", "message": "Cancelled by user"}
    )
    return {"job_id": job_id, "status": "CANCELLED"}


@router.post("/jobs/{job_id}/approve")
async def approve_agent_job(job_id: str, payload: ApprovalRequest) -> dict[str, Any]:
    """Record an approval decision and apply it to the job state machine.

    target=plan approves/rejects the whole plan (→ EXECUTING / FAILED),
    target=step decides one plan step (all approved → EXECUTING, any
    rejected → FAILED), target=gate is the final gate decision
    (→ COMPLETED / FAILED). Every decision is persisted as an approval
    record retrievable via GET /agent/jobs/{job_id}/approvals.
    """
    job = _job_or_404(job_id)
    if _console_status(job) in _TERMINAL_CONSOLE_STATUSES:
        raise ApiError(
            status_code=409,
            code=STATE_CONFLICT,
            detail=(
                f"Agent job {job_id} is {_console_status(job)} — "
                "terminal jobs accept no approvals"
            ),
        )
    if payload.target == "step" and payload.step_index is None:
        raise ApiError(
            status_code=422,
            code=STATE_CONFLICT,
            detail="step_index is required when target is 'step'",
        )
    _apply_approval(job, payload.target, payload.decision, payload.note, payload.step_index)
    approval = get_state().record_approval(
        job_id, payload.target, payload.decision, payload.note, payload.step_index,
    )
    fresh = _job_or_404(job_id)
    return {
        "approval": approval,
        "job": {"id": job_id, "status": _console_status(fresh)},
    }


@router.get("/jobs/{job_id}/approvals")
async def list_agent_approvals(job_id: str) -> dict[str, Any]:
    """List every approval decision recorded for a job."""
    _job_or_404(job_id)
    approvals = get_state().approvals_for(job_id)
    return {"job_id": job_id, "approvals": approvals, "count": len(approvals)}


class _DisconnectProbe(Protocol):
    """Minimal surface _event_stream needs from a request (testable)."""

    async def is_disconnected(self) -> bool: ...


async def _event_stream(
    job_id: str, request: _DisconnectProbe, store: AgentJobStore,
    state: _ConsoleState, from_seq: int,
) -> AsyncGenerator[str, None]:
    """Yield SSE frames; closes with "done" on terminal, stops on disconnect.

    Extracted from the route so the reconnect/disconnect protocol is
    testable without a live socket (unit tests drive this generator with a
    fake request whose is_disconnected() flips).
    """
    delivered = 0
    seen = from_seq
    while True:
        if await request.is_disconnected():
            break
        events = state.events_since(job_id, seen)
        for ev in events:
            payload = json.dumps(ev, ensure_ascii=False)
            yield f"id: {ev['seq']}\n"
            yield f"event: {ev['type']}\n"
            yield f"data: {payload}\n\n"
            seen = int(ev["seq"])
            delivered += 1
        if events:
            continue
        current = store.get(job_id)
        if current is not None and current.status in TERMINAL_JOB_STATUSES:
            done = json.dumps(
                {"job_id": job_id, "status": current.status,
                 "delivered": delivered},
                ensure_ascii=False,
            )
            yield "id: done\n"
            yield "event: done\n"
            yield f"data: {done}\n\n"
            return
        await asyncio.sleep(0.25)


@router.get("/jobs/{job_id}/events")
async def stream_agent_events(job_id: str, request: Request) -> StreamingResponse:
    """SSE stream of plan / tool_call / tool_result / edit / gate / progress.

    Frame format mirrors /jobs/{job_id}/progress:

        id: <seq>
        event: <type>
        data: {"seq": N, "type": "...", "at": "...", "data": {...}}

    Reconnection: pass Last-Event-ID with the last seen seq and the stream
    resumes from there. The stream closes itself with a final "done" event
    once the job is terminal and every event has been delivered; a live
    (non-terminal) job streams until the client disconnects.
    """
    _job_or_404(job_id)
    raw_last = request.headers.get("Last-Event-ID", "0")
    try:
        from_seq = int(raw_last)
    except ValueError:
        from_seq = 0
    return StreamingResponse(
        _event_stream(job_id, request, get_store(), get_state(), from_seq),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Structured diff ─────────────────────────────────────────────────────────


def _diff_hunks(old_text: str, new_text: str, context: int = 3) -> builtins.list[dict[str, Any]]:
    """Build structured hunks (unified-style, line numbered) for two texts."""
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    opcodes = matcher.get_opcodes()
    changed = [i for i, (tag, *_rest) in enumerate(opcodes) if tag != "equal"]
    if not changed:
        return []
    groups: builtins.list[tuple[int, int]] = []
    g_start = changed[0]
    g_end = changed[0]
    for i in changed[1:]:
        between = sum(opcodes[j][2] - opcodes[j][1] for j in range(g_end + 1, i))
        if between <= context * 2:
            g_end = i
        else:
            groups.append((g_start, g_end))
            g_start = i
            g_end = i
    groups.append((g_start, g_end))

    hunks: builtins.list[dict[str, Any]] = []
    for gs, ge in groups:
        lines: builtins.list[dict[str, Any]] = []
        old_no = opcodes[gs][1] + 1
        new_no = opcodes[gs][3] + 1

        if gs > 0 and opcodes[gs - 1][0] == "equal":
            eq = old_lines[opcodes[gs - 1][1]:opcodes[gs - 1][2]]
            ctx_before = eq[-context:]
            for k, text in enumerate(ctx_before):
                old_off = opcodes[gs - 1][1] + len(eq) - len(ctx_before) + k
                new_off = opcodes[gs - 1][3] + len(eq) - len(ctx_before) + k
                lines.append({
                    "type": "context", "old_no": old_off + 1,
                    "new_no": new_off + 1, "text": text,
                })
                old_no = old_off + 1
                new_no = new_off + 1

        for j in range(gs, ge + 1):
            tag, i1, i2, j1, j2 = opcodes[j]
            if tag == "equal":
                for k in range(i1, i2):
                    lines.append({
                        "type": "context", "old_no": k + 1, "new_no": j1 + (k - i1) + 1,
                        "text": old_lines[k],
                    })
            else:
                if tag in ("delete", "replace"):
                    for k in range(i1, i2):
                        lines.append({
                            "type": "del", "old_no": k + 1, "new_no": None,
                            "text": old_lines[k],
                        })
                if tag in ("insert", "replace"):
                    for k in range(j1, j2):
                        lines.append({
                            "type": "add", "old_no": None, "new_no": k + 1,
                            "text": new_lines[k],
                        })

        if ge + 1 < len(opcodes) and opcodes[ge + 1][0] == "equal":
            eq = new_lines[opcodes[ge + 1][3]:opcodes[ge + 1][4]]
            ctx_after = eq[:context]
            for k, text in enumerate(ctx_after):
                lines.append({
                    "type": "context", "old_no": opcodes[ge + 1][1] + k + 1,
                    "new_no": opcodes[ge + 1][3] + k + 1, "text": text,
                })

        old_count = sum(1 for line in lines if line["old_no"] is not None)
        new_count = sum(1 for line in lines if line["new_no"] is not None)
        hunks.append({
            "old_start": old_no, "old_count": old_count,
            "new_start": new_no, "new_count": new_count,
            "lines": lines,
        })
    return hunks


@router.get("/jobs/{job_id}/diff")
async def get_agent_diff(
    job_id: str, mode: Literal["unified", "split"] = "unified",
) -> dict[str, Any]:
    """Structured diff of the current change bundle.

    The bundle is a list of {path, status(added|modified|deleted), before,
    after} records produced by the agent's edit tool; this endpoint renders
    them as line-numbered hunks (type add/del/context) plus aggregate
    stats. Honest 404 when no bundle exists yet.
    """
    _job_or_404(job_id)
    files = get_state().bundle_for(job_id)
    if not files:
        raise ApiError(
            status_code=404,
            code=EVIDENCE_UNVERIFIED,
            detail=f"Agent job {job_id} has no change bundle yet",
        )
    rendered: builtins.list[dict[str, Any]] = []
    total_added = 0
    total_deleted = 0
    for entry in files:
        path = str(entry.get("path", ""))
        status = str(entry.get("status", "modified"))
        before = str(entry.get("before", ""))
        after = str(entry.get("after", ""))
        hunks = _diff_hunks(before, after)
        added = sum(1 for h in hunks for line in h["lines"] if line["type"] == "add")
        deleted = sum(1 for h in hunks for line in h["lines"] if line["type"] == "del")
        total_added += added
        total_deleted += deleted
        rendered.append({
            "path": path,
            "status": status,
            "hunks": hunks,
            "insertions": added,
            "deletions": deleted,
        })
    rendered.sort(key=lambda f: f["path"])
    return {
        "job_id": job_id,
        "mode": mode,
        "stats": {
            "files_changed": len(rendered),
            "insertions": total_added,
            "deletions": total_deleted,
        },
        "files": rendered,
        "generated_at": _now_iso(),
    }
