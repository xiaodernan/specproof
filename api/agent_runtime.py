"""Agent runtime: real deterministic CraftLoops behind /agent/jobs (W42).

The W31 console stored agent jobs as passive projections; this module makes
them run. AgentRuntime.start() launches a daemon thread that drives a real
craft.loop.CraftLoop in deterministic mode — no LLM client, no network, no
Docker — the same honest path scripts/bench_craft.py exercises (deterministic
plan + explicitly injected fix rules):

  - workspace: the caller-supplied repo, or the bundled api/_agent_demo
    task materialized into a fresh temp directory under workspace_root;
  - planning: craft.planner.compile_plan(mode="deterministic") — a "plan"
    SSE event carries the compiled plan;
  - execution: CraftLoop(store=...), so the loop itself writes the durable
    projection (create/lease/renew/set_progress/update_status per the W30
    Integration note); a projection watcher thread turns every store
    progress transition into a live "progress" event;
  - tools: the loop editor is wrapped in _EventedEditor, which publishes
    tool_call / tool_result / edit events for every real editor operation
    (reads, apply_edit, write_file);
  - gates: the loop runs the five-gate pipeline at finish; each gate entry
    and the overall summary become "gate" events, and the terminal verdict
    becomes the final "progress" event;
  - accept: for terminal succeeded/failed jobs the gate summary is attached
    to the closed projection through craft.accept.persist_accept_result
    (attach_accept_result, W35.1) with an honest verdict — the runtime lane
    never claims VERIFIED, because the full closure (SpecProof verification
    + certificate + Ed25519 signing) needs a git repo with base/head refs
    and a signing key and stays with the `specproof craft accept` CLI.

cancel() sets a cooperative flag plus the durable store.cancel (which wins
even over a leased worker); the loop flushes an honest CANCELLED terminal
and never fights the supervisor projection. All state is guarded by a
per-runtime lock and the per-job handle (cancel event + thread); the
console state and the job store are already thread-safe.
"""

from __future__ import annotations

import json
import logging
import tempfile
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from api._agent_demo import (
    DEMO_FIX_REGISTRY,
    DEMO_SPEC_TEXT,
    DEMO_TASK_NAME,
    materialize_demo_workspace,
)
from craft.accept import AcceptResult, persist_accept_result
from craft.editor import MAX_READ_LINES, EditError, Editor
from craft.loop import CraftLoop, CraftLoopError, FixFunction
from craft.planner import CraftModeError, CraftPlanError, compile_plan
from craft.spec import SpecParseError, parse_spec
from craft.tools import ToolRegistry
from storage.agent_jobs import (
    TERMINAL_JOB_STATUSES,
    AgentJob,
    AgentJobStore,
    AgentJobStoreError,
    InvalidJobTransitionError,
    JobNotFoundError,
)

logger = logging.getLogger(__name__)


class AgentRuntimeError(RuntimeError):
    """The runtime cannot start the requested job (e.g. already running)."""


class ConsoleState(Protocol):
    """The console-state surface the runtime uses (api/routes/agent_console).

    Kept as a Protocol so AgentRuntime stays importable without a hard
    import cycle: the concrete _ConsoleState lives in the routes module.
    """

    def set_meta(self, job_id: str, repo_path: str, task_name: str | None) -> None: ...

    def meta_for(self, job_id: str) -> dict[str, str]: ...

    def record_event(self, job_id: str, etype: str, data: dict[str, Any]) -> dict[str, Any]: ...

    def set_bundle(self, job_id: str, files: list[dict[str, Any]]) -> None: ...

    def bundle_for(self, job_id: str) -> list[dict[str, Any]]: ...


def console_status_label(job: AgentJob) -> str:
    """Map the store status onto the console vocabulary (stable API surface).

    Mirrors api/routes/agent_console._console_status; kept local so the
    runtime stays decoupled from the routes module internals.
    """
    if job.status == "pending":
        return "AWAITING_APPROVAL" if job.plan_json else "PLANNING"
    if job.status == "running":
        return "EXECUTING"
    if job.status == "succeeded":
        return "COMPLETED"
    if job.status == "failed":
        return "FAILED"
    return "CANCELLED"


@dataclass
class _JobHandle:
    """Per-job runtime bookkeeping (guarded by AgentRuntime._lock)."""

    job_id: str
    cancel_event: threading.Event = field(default_factory=threading.Event)
    watcher_stop: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None


class _EventedEditor(Editor):
    """Editor wrapper publishing tool_call / tool_result / edit SSE events.

    Every real editor operation is announced before it runs and its honest
    outcome after: reads become read_file tool calls, apply_edit/write_file
    become tool calls plus edit records (before/after) feeding the console
    timeline. EditError outcomes are reported as failed tool results and
    re-raised — the loop keeps its original semantics untouched.
    """

    def __init__(
        self,
        workspace: str | Path,
        *,
        backup_dir: str | Path | None,
        audit_path: str | Path | None,
        emit: Callable[[str, dict[str, Any]], None],
    ) -> None:
        super().__init__(workspace, backup_dir=backup_dir, audit_path=audit_path)
        self._emit = emit
        self._call_seq = 0

    def _next_call_id(self) -> str:
        self._call_seq += 1
        return f"ed-{self._call_seq:04d}"

    def _peek(self, path: str) -> str:
        """Current file content without auditing a read ("" when absent)."""
        try:
            target = self._resolve(path)
            return target.read_text(encoding="utf-8") if target.is_file() else ""
        except (EditError, OSError):
            return ""

    def read_file(
        self, path: str, offset: int = 1, limit: int = MAX_READ_LINES
    ) -> list[tuple[int, str]]:
        call_id = self._next_call_id()
        self._emit(
            "tool_call",
            {"tool": "read_file", "call_id": call_id, "path": path,
             "offset": offset, "limit": limit},
        )
        try:
            lines = super().read_file(path, offset=offset, limit=limit)
        except EditError as exc:
            self._emit(
                "tool_result",
                {"tool": "read_file", "call_id": call_id, "path": path,
                 "ok": False, "error": str(exc)},
            )
            raise
        self._emit(
            "tool_result",
            {"tool": "read_file", "call_id": call_id, "path": path,
             "ok": True, "lines": len(lines)},
        )
        return lines

    def apply_edit(
        self, path: str, old: str, new: str, *, expected_digest: str | None = None
    ) -> None:
        call_id = self._next_call_id()
        before_text = self._peek(path)
        self._emit(
            "tool_call",
            {"tool": "apply_edit", "call_id": call_id, "path": path,
             "old": old, "new": new},
        )
        try:
            super().apply_edit(path, old, new, expected_digest=expected_digest)
        except EditError as exc:
            self._emit(
                "tool_result",
                {"tool": "apply_edit", "call_id": call_id, "path": path,
                 "ok": False, "error": str(exc)},
            )
            raise
        self._emit(
            "tool_result",
            {"tool": "apply_edit", "call_id": call_id, "path": path, "ok": True},
        )
        self._emit(
            "edit",
            {"path": path, "status": "modified", "before": before_text,
             "after": self._peek(path)},
        )

    def write_file(
        self, path: str, content: str, *, expected_digest: str | None = None
    ) -> None:
        call_id = self._next_call_id()
        before_text = self._peek(path)
        self._emit(
            "tool_call",
            {"tool": "write_file", "call_id": call_id, "path": path},
        )
        try:
            super().write_file(path, content, expected_digest=expected_digest)
        except EditError as exc:
            self._emit(
                "tool_result",
                {"tool": "write_file", "call_id": call_id, "path": path,
                 "ok": False, "error": str(exc)},
            )
            raise
        self._emit(
            "tool_result",
            {"tool": "write_file", "call_id": call_id, "path": path, "ok": True},
        )
        self._emit(
            "edit",
            {"path": path, "status": "modified" if before_text else "added",
             "before": before_text, "after": content},
        )


class AgentRuntime:
    """Run real deterministic CraftLoops for the Web Agent Console (W42).

    store/state default to the console singletons (resolved lazily at call
    time, so tests swapping api.routes.agent_console._store/_state are
    honored); pass explicit instances to run standalone.
    """

    DEFAULT_LEASE_TTL_SECONDS = 900.0

    def __init__(
        self,
        *,
        store: AgentJobStore | None = None,
        state: ConsoleState | None = None,
        workspace_root: str | Path | None = None,
        lease_ttl_seconds: float = DEFAULT_LEASE_TTL_SECONDS,
    ) -> None:
        self._store = store
        self._state = state
        self._workspace_root = (
            Path(workspace_root)
            if workspace_root is not None
            else Path(tempfile.gettempdir()) / "specproof-agent-console"
        )
        self._lease_ttl_seconds = lease_ttl_seconds
        self._lock = threading.RLock()
        self._handles: dict[str, _JobHandle] = {}

    # -- console singletons (lazy: avoids an import cycle with the routes) --

    def _store_for(self) -> AgentJobStore:
        if self._store is not None:
            return self._store
        from api.routes.agent_console import get_store

        return get_store()

    def _state_for(self) -> ConsoleState:
        if self._state is not None:
            return self._state
        from api.routes.agent_console import get_state

        return get_state()

    # -- public surface ---------------------------------------------------

    def start(
        self,
        job_id: str,
        repo_path: str | None,
        spec_text: str | None,
        *,
        task_name: str | None = None,
        fix_registry: dict[str, FixFunction] | None = None,
    ) -> None:
        """Spawn a daemon thread running a real deterministic CraftLoop.

        repo_path/spec_text both empty (or None) select the bundled demo
        task materialized into a fresh temp workspace. The durable row is
        probe-then-created (create raises on duplicates, so a row already
        created by the console endpoint is reused). Every failure after the
        spawn is owned by the runtime thread and projected honestly.
        """
        store = self._store_for()
        effective_spec = spec_text if spec_text and spec_text.strip() else DEMO_SPEC_TEXT
        effective_repo = repo_path if repo_path and repo_path.strip() else ""
        with self._lock:
            existing = self._handles.get(job_id)
            if (
                existing is not None
                and existing.thread is not None
                and existing.thread.is_alive()
            ):
                raise AgentRuntimeError(f"agent job {job_id} already running in this runtime")
        if store.get(job_id) is None:
            store.create(job_id, effective_spec)
        handle = _JobHandle(job_id=job_id)
        thread = threading.Thread(
            target=self._run_job,
            args=(handle, effective_repo, effective_spec, task_name, fix_registry),
            name=f"agent-runtime-{job_id[:8]}",
            daemon=True,
        )
        handle.thread = thread
        with self._lock:
            self._handles[job_id] = handle
        thread.start()

    def cancel(self, job_id: str, reason: str = "Cancelled by user") -> bool:
        """Cooperative cancel flag + the durable supervisor override.

        store.cancel wins even over a leased worker; the loop flushes an
        honest CANCELLED terminal at the next step boundary. Terminal jobs
        are never flipped (the console rejects them at the HTTP layer) and
        unknown jobs return False.
        """
        store = self._store_for()
        job = store.get(job_id)
        if job is None or job.status in TERMINAL_JOB_STATUSES:
            return False
        with self._lock:
            handle = self._handles.get(job_id)
            if handle is None:
                handle = _JobHandle(job_id=job_id)
                self._handles[job_id] = handle
        handle.cancel_event.set()
        store.cancel(job_id, reason)
        return True

    def wait_until_terminal(self, job_id: str, timeout: float = 60.0) -> bool:
        """Wait for the terminal projection AND the runtime thread's post-run.

        The store turns terminal inside CraftLoop._finish, but the runtime
        still emits gate/bundle/terminal events afterwards; callers that
        assert on the event log (tests, SSE consumers) need this to join the
        thread before reading events.
        """
        store = self._store_for()
        deadline = time.monotonic() + timeout
        terminal = False
        while time.monotonic() < deadline:
            job = store.get(job_id)
            if job is not None and job.status in TERMINAL_JOB_STATUSES:
                terminal = True
                break
            time.sleep(0.05)
        with self._lock:
            handle = self._handles.get(job_id)
        if handle is not None and handle.thread is not None and handle.thread.is_alive():
            handle.thread.join(timeout=max(0.0, deadline - time.monotonic()))
        return terminal and not (
            handle is not None and handle.thread is not None and handle.thread.is_alive()
        )

    # -- thread body ------------------------------------------------------

    def _run_job(
        self,
        handle: _JobHandle,
        repo_path: str,
        spec_text: str,
        task_name: str | None,
        fix_registry: dict[str, FixFunction] | None,
    ) -> None:
        store = self._store_for()
        state = self._state_for()
        try:
            self._execute(handle, store, state, repo_path, spec_text, task_name, fix_registry)
        except Exception as exc:  # noqa: BLE001 — a daemon thread never dies silently
            logger.exception("agent runtime thread crashed for %s", handle.job_id)
            self._crash_terminal(store, state, handle.job_id, f"runtime crashed: {exc}")
        finally:
            handle.watcher_stop.set()

    def _execute(
        self,
        handle: _JobHandle,
        store: AgentJobStore,
        state: ConsoleState,
        repo_path: str,
        spec_text: str,
        task_name: str | None,
        fix_registry: dict[str, FixFunction] | None,
    ) -> None:
        job_id = handle.job_id
        job = store.get(job_id)
        if job is None:
            self._crash_terminal(store, state, job_id, "job missing from the durable store")
            return
        if handle.cancel_event.is_set() or job.status == "cancelled":
            state.record_event(
                job_id, "progress",
                {"status": "CANCELLED", "message": "cancelled before the run started"},
            )
            return

        # -- workspace (bundled demo materialized per job, no shared state) --
        is_demo = not repo_path.strip()
        if is_demo:
            workspace = materialize_demo_workspace(self._workspace_root)
        else:
            workspace = Path(repo_path)
            if not workspace.is_dir():
                self._crash_terminal(
                    store, state, job_id, f"repo_path 不存在: {repo_path}",
                )
                return
        meta_name = state.meta_for(job_id).get("task_name")
        label = meta_name or task_name or (DEMO_TASK_NAME if is_demo else None)
        state.set_meta(job_id, str(workspace), label)

        # -- deterministic plan (no LLM client, ever) --
        try:
            spec = parse_spec(spec_text)
        except SpecParseError as exc:
            self._crash_terminal(store, state, job_id, f"spec 解析失败: {exc}")
            return
        try:
            plan = compile_plan(spec, mode="deterministic")
        except (CraftPlanError, CraftModeError) as exc:
            self._crash_terminal(store, state, job_id, f"计划编译失败: {exc}")
            return
        state.record_event(job_id, "plan", {"plan": plan.to_dict(), "mode": "deterministic"})
        state.record_event(
            job_id, "progress",
            {"status": "EXECUTING", "message": "deterministic CraftLoop starting (no LLM)"},
        )

        # -- fix rules: explicit injection only (M1 never invents them) --
        # The demo registry applies only when the caller injected nothing;
        # an explicit registry (even empty) is used verbatim, so jobs that
        # must fail without fixes fail honestly.
        registry = dict(fix_registry) if fix_registry is not None else {}
        if is_demo and fix_registry is None:
            registry = dict(DEMO_FIX_REGISTRY)

        artifact_dir = workspace / ".specraft" / "jobs" / job_id

        def publish(etype: str, data: dict[str, Any]) -> None:
            state.record_event(job_id, etype, data)

        editor = _EventedEditor(
            workspace,
            backup_dir=artifact_dir / "backup",
            audit_path=artifact_dir / "audit.jsonl",
            emit=publish,
        )
        loop = CraftLoop(
            spec,
            plan,
            workspace,
            job_id=job_id,
            fix_registry=registry,
            exec_mode="local",
            store=store,
            lease_ttl_seconds=self._lease_ttl_seconds,
            tool_registry=ToolRegistry(workspace, editor=editor),
        )

        watcher = threading.Thread(
            target=self._watch_progress,
            args=(handle, store, state),
            name=f"agent-watcher-{job_id[:8]}",
            daemon=True,
        )
        watcher.start()
        try:
            report = loop.run()
        except CraftLoopError as exc:
            self._crash_terminal(store, state, job_id, f"craft loop aborted: {exc}")
            return
        finally:
            handle.watcher_stop.set()
            watcher.join(timeout=5.0)
        self._post_run(handle, store, state, loop, report)

    # -- post-run: gates / bundle / terminal / accept projection ----------

    def _post_run(
        self,
        handle: _JobHandle,
        store: AgentJobStore,
        state: ConsoleState,
        loop: CraftLoop,
        report: dict[str, Any],
    ) -> None:
        job_id = handle.job_id
        gates = report.get("gates")
        if isinstance(gates, dict):
            raw_entries = gates.get("gates") or []
            if isinstance(raw_entries, list):
                for entry in raw_entries:
                    if isinstance(entry, dict):
                        state.record_event(
                            job_id, "gate", {**entry, "overall": gates.get("overall")},
                        )
            state.record_event(
                job_id, "gate",
                {
                    "overall": gates.get("overall"),
                    "note": gates.get("overall_note"),
                    "summary": gates.get("summary"),
                },
            )
        bundle = self._bundle_from_editor(loop.editor)
        if bundle:
            state.set_bundle(job_id, bundle)
        current = store.get(job_id)
        if current is None:
            self._crash_terminal(store, state, job_id, "job missing after the run")
            return
        if current.status == "cancelled":
            state.record_event(
                job_id, "progress",
                {"status": "CANCELLED", "message": "cancelled by user (cancel wins)"},
            )
            return
        verdict = str(report.get("result", ""))
        state.record_event(
            job_id, "progress",
            {
                "status": console_status_label(current),
                "verdict": verdict,
                "message": f"craft run finished: {verdict}",
            },
        )
        if current.status in ("succeeded", "failed"):
            accept = self._gate_accept_projection(report)
            attached = persist_accept_result(store, job_id, accept)
            logger.info(
                "agent job %s: accept projection attached=%s verdict=%s",
                job_id, attached, accept.verdict,
            )

    @staticmethod
    def _gate_accept_projection(report: dict[str, Any]) -> AcceptResult:
        """AcceptResult from the loop's real five-gate run (W35.1 attach).

        The runtime lane never claims VERIFIED: the full closure (SpecProof
        independent verification + Merge Certificate + Ed25519 signature)
        requires a git repo with base/head refs and a signing key and stays
        with `specproof craft accept`. The gate summary is the honest
        evidence this lane can produce, so the verdict is BLOCKED (no
        certificate was issued) with the closure deferral on record.
        """
        gates = report.get("gates")
        if not isinstance(gates, dict):
            return AcceptResult(
                "ERROR", None, [], None, False,
                note="gate summary missing from the craft report; closure not run",
            )
        overall = gates.get("overall")
        if overall == "error":
            return AcceptResult(
                "ERROR", None, [], dict(gates), False,
                note="gate pipeline error: " + str(gates.get("overall_note", "")),
            )
        if overall == "failed":
            findings: list[dict[str, Any]] = []
            raw_entries = gates.get("gates") or []
            if isinstance(raw_entries, list):
                for entry in raw_entries:
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("status") not in ("failed", "error"):
                        continue
                    raw_findings = entry.get("findings") or []
                    if isinstance(raw_findings, list):
                        for finding in raw_findings:
                            if isinstance(finding, dict):
                                findings.append(dict(finding))
            return AcceptResult(
                "BLOCKED", None, findings, dict(gates), False,
                note="内部门禁 FAIL: " + str(gates.get("overall_note", "")),
            )
        return AcceptResult(
            "BLOCKED", None, [], dict(gates), False,
            note=(
                "runtime lane: 门禁摘要通过; 完整 accept 闭包 (SpecProof 验证 + 证书 + 签名)"
                " 需 git base/head 与签名密钥, 交由 craft accept CLI 执行"
            ),
        )

    @staticmethod
    def _bundle_from_editor(editor: Editor) -> list[dict[str, Any]]:
        """Change bundle (before/after) from the editor audit + backups."""
        changed = sorted(
            {
                entry.path
                for entry in editor.audit
                if entry.action in ("write", "edit", "move", "delete")
            }
        )
        if not changed:
            return []
        backups: dict[str, str] = {}
        for entry in editor.audit:
            if entry.action != "backup" or entry.path in backups:
                continue
            backup_name = entry.detail.removeprefix("→ ").strip()
            backup_path = Path(editor.backup_dir) / backup_name
            try:
                backups[entry.path] = backup_path.read_text(encoding="utf-8")
            except OSError:
                backups[entry.path] = ""
        files: list[dict[str, Any]] = []
        for path in changed:
            after = ""
            try:
                target = editor.workspace / path
                if target.is_file():
                    after = target.read_text(encoding="utf-8")
            except OSError:
                after = ""
            before = backups.get(path, "")
            status = "deleted" if not after else ("modified" if before else "added")
            files.append({"path": path, "status": status, "before": before, "after": after})
        return files

    # -- projection watcher -------------------------------------------------

    def _watch_progress(
        self,
        handle: _JobHandle,
        store: AgentJobStore,
        state: ConsoleState,
    ) -> None:
        """Stream durable progress transitions as live "progress" events.

        Terminal transitions are left to the main thread (gate events must
        precede the terminal event), so the watcher stops at the first
        terminal snapshot.
        """
        job_id = handle.job_id
        signature: tuple[object, ...] | None = None
        while not handle.watcher_stop.wait(0.15):
            job = store.get(job_id)
            if job is None:
                return
            current = (job.status, job.current_step, job.progress_json)
            if current != signature:
                signature = current
                if job.status not in TERMINAL_JOB_STATUSES:
                    progress: dict[str, Any] | None = None
                    if job.progress_json:
                        try:
                            loaded = json.loads(job.progress_json)
                        except json.JSONDecodeError:
                            loaded = None
                        if isinstance(loaded, dict):
                            progress = loaded
                    state.record_event(
                        job_id, "progress",
                        {
                            "status": console_status_label(job),
                            "current_step": job.current_step,
                            "progress": progress,
                            "message": (
                                f"step {job.current_step}"
                                if job.current_step
                                else "craft loop executing"
                            ),
                        },
                    )
            if job.status in TERMINAL_JOB_STATUSES:
                return

    # -- failure projection --------------------------------------------------

    @staticmethod
    def _crash_terminal(
        store: AgentJobStore,
        state: ConsoleState,
        job_id: str,
        reason: str,
    ) -> None:
        """Honest terminal write for aborted runs (cancel never overwritten)."""
        current = store.get(job_id)
        if current is not None and current.status in TERMINAL_JOB_STATUSES:
            state.record_event(
                job_id, "progress",
                {"status": console_status_label(current), "message": reason},
            )
            return
        with suppress(InvalidJobTransitionError, JobNotFoundError, AgentJobStoreError):
            store.update_status(
                job_id, "failed", error=reason,
                result_json={"verdict": "FAILED", "reason": reason},
            )
        state.record_event(job_id, "progress", {"status": "FAILED", "message": reason})
