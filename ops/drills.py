"""Operations drill helpers — recovery & security drills (docs/operations/DRILLS.md).

Pure orchestration utilities used by the drill drivers
(scripts/drill_worker_kill.py, scripts/drill_outbox_crash.py,
scripts/drill_provider_outage.py) and covered by
tests/unit/test_drill_helpers.py. They never mutate anything on their own:
every effect goes through the real storage/broker clients the caller passes
in, so the unit tests run against fakes with zero infrastructure.

What each drill needs from here:

- drill 1 (worker-kill recovery): wait_for_status, wait_for_checkpoint_count,
  wait_for_lease_available, terminal_transitions, side_effect_counts,
  resume_job, build_deterministic_fixture.
- drill 2 (provider outage): honest_degradation_report.
- drill 4 (outbox relay crash window): crash_window_publish,
  wait_for_idempotency_key, outbox_event_id, terminal_transitions,
  side_effect_counts.
"""
from __future__ import annotations

import subprocess
import time
from collections.abc import Callable, Collection, Mapping
from pathlib import Path
from typing import Any, Protocol, cast

from providers.resilience import (
    CircuitBreaker,
    RetryPolicy,
    _extract_status,
    classify_retry,
)
from storage.mysql import InvalidStateTransition

#: Job statuses the state machine treats as terminal (storage/mysql.py).
TERMINAL_JOB_STATUSES: frozenset[str] = frozenset(
    {"VERIFIED", "BLOCKED", "STALE", "CANCELLED", "ERROR"}
)
#: Audit action written for every successful state transition (storage/mysql.py).
TRANSITION_ACTION = "job_status_transition"
#: Redis key prefix the worker's idempotency check uses (storage/rabbitmq.py).
IDEMPOTENCY_KEY_PREFIX = "specproof:idempotent:"

DEFAULT_POLL_INTERVAL = 0.25


class DrillError(Exception):
    """Base error for the operations drill tooling."""


class DrillInfraUnavailableError(DrillError):
    """A drill needs live infrastructure that is not reachable."""


class DrillTargetError(DrillError):
    """The drill target (job / outbox row / lease) is not in the expected state."""


# ── Injectable client surfaces (protocols; satisfied by the storage clients) ──


class JobReader(Protocol):
    def get_job(self, job_id: str) -> dict[str, Any] | None: ...
    def get_job_summary(self, job_id: str) -> dict[str, Any] | None: ...


class SqlConnection(Protocol):
    def cursor(self) -> Any: ...
    def __enter__(self) -> Any: ...
    def __exit__(self, *exc_info: Any) -> Any: ...


class JobAuditStore(Protocol):
    """Storage surface for job status and audit rows (storage.mysql.MySQLStore)."""

    def connection(self) -> SqlConnection: ...
    def transition_job_status(
        self,
        job_id: str,
        to_status: str,
        *,
        from_status: str | None = None,
        worker_id: str | None = None,
        error_msg: str | None = None,
    ) -> bool: ...
    def save_job_summary(self, job_id: str, summary: Mapping[str, Any]) -> None: ...


class SideEffectStore(JobReader, JobAuditStore, Protocol):
    """Combined job surface for side-effect accounting (satisfied by MySQLStore)."""


class ProgressStream(Protocol):
    def xread_progress(
        self, job_id: str, from_id: str = "0", count: int = 100,
    ) -> list[dict[str, Any]]: ...


class CheckpointCollection(Protocol):
    """A pymongo collection: count_documents({"thread_id": job_id})."""

    def count_documents(self, query: Mapping[str, Any]) -> int: ...


class IdempotencyRedis(Protocol):
    def get(self, key: str) -> bytes | str | None: ...


class LeaseStore(Protocol):
    def acquire_lease(self, job_id: str, worker_id: str, ttl: int = 30) -> bool: ...
    def get_lease_owner(self, job_id: str) -> str | None: ...
    def release_lease(self, job_id: str, worker_id: str) -> None: ...


class Publisher(Protocol):
    def publish(
        self, routing_key: str, payload: Mapping[str, Any],
        exchange: str | None = None,
    ) -> None: ...


class ResumeWorker(Protocol):
    """Worker surface resume_job needs (satisfied by agent.worker.Worker)."""

    def execute_job(
        self, job_id: str, payload: Mapping[str, Any],
    ) -> dict[str, Any]: ...


# ── Polling helpers ─────────────────────────────────────────────────────────


def wait_for_status(
    store: JobReader,
    job_id: str,
    statuses: Collection[str],
    timeout: float = 120.0,
    interval: float = DEFAULT_POLL_INTERVAL,
) -> dict[str, Any] | None:
    """Poll MySQL until the job row reaches one of ``statuses`` (or timeout).

    Returns the job row dict, or None on timeout.
    """
    wanted = frozenset(statuses)
    deadline = time.monotonic() + timeout
    while True:
        row = store.get_job(job_id)
        if row is not None and str(row.get("status", "")) in wanted:
            return row
        if time.monotonic() >= deadline:
            return None
        time.sleep(interval)


def wait_for_progress_event(
    stream: ProgressStream,
    job_id: str,
    node: str,
    status: str,
    timeout: float = 120.0,
    interval: float = DEFAULT_POLL_INTERVAL,
) -> dict[str, Any] | None:
    """Poll the Redis progress stream for a (node, status) event."""
    deadline = time.monotonic() + timeout
    while True:
        for event in stream.xread_progress(job_id, "0", 500):
            if event.get("node") == node and event.get("status") == status:
                return event
        if time.monotonic() >= deadline:
            return None
        time.sleep(interval)


def wait_for_checkpoint_count(
    checkpoints: CheckpointCollection,
    job_id: str,
    min_count: int,
    timeout: float = 120.0,
    interval: float = DEFAULT_POLL_INTERVAL,
) -> int:
    """Poll the Mongo checkpoint collection until >= min_count docs exist.

    Returns the final count (which may still be below min_count on timeout).
    """
    deadline = time.monotonic() + timeout
    count = 0
    while True:
        count = checkpoints.count_documents({"thread_id": job_id})
        if count >= min_count or time.monotonic() >= deadline:
            return count
        time.sleep(interval)


def wait_for_lease_available(
    leases: LeaseStore,
    job_id: str,
    timeout: float = 60.0,
    interval: float = DEFAULT_POLL_INTERVAL,
) -> bool:
    """Wait until the crashed worker's Redis lease has expired or been released."""
    deadline = time.monotonic() + timeout
    while True:
        if leases.get_lease_owner(job_id) is None:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval)


def wait_for_idempotency_key(
    redis: IdempotencyRedis,
    event_id: str,
    timeout: float = 60.0,
    interval: float = DEFAULT_POLL_INTERVAL,
) -> bool:
    """Wait until the worker's idempotency key exists for an event."""
    key = IDEMPOTENCY_KEY_PREFIX + event_id
    deadline = time.monotonic() + timeout
    while True:
        if redis.get(key) is not None:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval)


# ── Side-effect accounting ──────────────────────────────────────────────────


def _audit_rows(store: JobAuditStore, job_id: str, action: str) -> list[dict[str, Any]]:
    """Audit rows for one job and action, oldest first."""
    with store.connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, actor, action, from_status, to_status, detail, created_at "
            "FROM audit_logs WHERE job_id = %s AND action = %s ORDER BY id",
            (job_id, action),
        )
        return cast(list[dict[str, Any]], cur.fetchall())


def terminal_transitions(store: JobAuditStore, job_id: str) -> list[dict[str, Any]]:
    """Every status transition into a terminal state recorded for the job."""
    return [
        row for row in _audit_rows(store, job_id, TRANSITION_ACTION)
        if row.get("to_status") in TERMINAL_JOB_STATUSES
    ]


def count_audit_actions(store: JobAuditStore, job_id: str, action: str) -> int:
    """Number of audit rows of one action for the job."""
    return len(_audit_rows(store, job_id, action))


def side_effect_counts(store: SideEffectStore, job_id: str) -> dict[str, int]:
    """Count every durable business side effect a job produced.

    The drill assertions read this dict: a crash-recovered job must show
    exactly the same counts as an uninterrupted control run of the same
    deterministic payload — one terminal transition, one summary write, one
    set of findings and capsules (no duplicated side effects).
    """
    job = store.get_job(job_id)
    summary = store.get_job_summary(job_id) or {}
    summary_writes = 1 if job is not None and job.get("summary") else 0
    terminal = len(terminal_transitions(store, job_id))
    total = count_audit_actions(store, job_id, TRANSITION_ACTION)
    return {
        "terminal_transitions": terminal,
        "running_transitions": total - terminal,
        "summary_writes": summary_writes,
        "findings": len(summary.get("findings", [])),
        "capsules": len(summary.get("capsules", [])),
        "errors": len(summary.get("errors", [])),
    }


# ── Crash-window / resume orchestration ─────────────────────────────────────


def outbox_event_id(row: Mapping[str, Any]) -> str:
    """The deterministic event id the relay puts on the wire (storage/outbox_relay.py)."""
    return f"outbox-{row['id']}"


def crash_window_publish(
    publisher: Publisher,
    flatten: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    row: Mapping[str, Any],
) -> dict[str, Any]:
    """Reconstruct the relay's kill window: publish the row's wire payload
    WITHOUT marking the row published.

    The real relay marks a row published only after the broker confirms
    (storage/outbox_relay.OutboxRelay.drain_pending). A kill that lands
    between the confirm and the UPDATE leaves exactly this state: message
    on the broker, row still pending. The caller decides the mark —
    exactly like the relay — so the unit test proves this helper publishes
    once and marks zero times.
    """
    wire = dict(flatten(row))
    publisher.publish(routing_key=str(row["routing_key"]), payload=wire)
    return wire


def resume_job(
    worker: ResumeWorker,
    leases: LeaseStore,
    store: JobAuditStore,
    job_id: str,
    payload: Mapping[str, Any],
    worker_id: str,
    *,
    verdict_fn: Callable[[Mapping[str, Any]], str],
    summary_fn: Callable[[Mapping[str, Any], str], Mapping[str, Any]],
) -> str:
    """Drive a crashed job to its single terminal state via checkpoint resume.

    Mirrors the post-lease half of Worker._handle_job_impl: acquire the
    lease (the crashed worker's lease must have expired), re-run the graph
    under the same thread_id so LangGraph skips completed nodes, then make
    exactly one terminal transition and write the summary. Raises
    DrillTargetError when the lease is still held or the job is missing.
    """
    if not leases.acquire_lease(job_id, worker_id):
        owner = leases.get_lease_owner(job_id)
        raise DrillTargetError(
            f"job {job_id} lease still held by {owner or 'another worker'}"
        )
    try:
        final_state = worker.execute_job(job_id, dict(payload))
        verdict = verdict_fn(final_state)
        try:
            if not store.transition_job_status(job_id, verdict):
                raise DrillTargetError(f"terminal transition refused for job {job_id}")
        except InvalidStateTransition as exc:
            raise DrillTargetError(f"terminal transition refused: {exc}") from exc
        store.save_job_summary(job_id, summary_fn(final_state, verdict))
        return verdict
    finally:
        leases.release_lease(job_id, worker_id)


# ── Honest provider degradation ─────────────────────────────────────────────


def honest_degradation_report(
    attempt: Callable[[], Any],
    *,
    max_attempts: int = 3,
    base_backoff: float = 1.0,
    max_backoff: float = 2.0,
    jitter: float = 0.1,
    clock: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """Exercise one provider call under the real retry policy and report the
    honest degradation envelope.

    The driver wires ``attempt`` to a real provider pointed at an
    unreachable endpoint; the unit tests wire it to a fake that raises a
    connection error. The report records attempts, wall-clock seconds, the
    surfaced exception, the retry classification that ended the run and the
    breaker state — the data the drill uses to prove the outage degraded
    honestly (no hang, no fabricated output, failure surfaced).
    """
    breaker = CircuitBreaker(
        failure_threshold=max_attempts, recovery_timeout=30.0, clock=clock,
    )
    policy = RetryPolicy(
        max_attempts=max_attempts,
        base_backoff=base_backoff,
        max_backoff=max_backoff,
        jitter=jitter,
        breaker=breaker,
        sleep_fn=sleep_fn,
    )
    started = clock()
    surfaced: BaseException | None = None
    try:
        policy.execute(attempt)
    except Exception as exc:  # noqa: BLE001 — capturing is the report's purpose
        surfaced = exc
    elapsed = round(clock() - started, 3)
    decision = classify_retry(
        _extract_status(surfaced) if surfaced is not None else None,
        surfaced,
        attempt=1,
        base_backoff=base_backoff,
        max_backoff=max_backoff,
        jitter=jitter,
    )
    return {
        "attempts": policy.attempts,
        "elapsed_seconds": elapsed,
        "failure_surfaced": surfaced is not None,
        "result_produced": surfaced is None,
        "exception_class": type(surfaced).__name__ if surfaced is not None else "",
        "exception_message": str(surfaced)[:200] if surfaced is not None else "",
        "final_decision_reason": decision.reason,
        "final_decision_retryable": decision.retryable,
        "breaker_state": breaker.state,
        "breaker_total_failures": breaker.total_failures,
    }


# ── Canonical deterministic drill fixture ───────────────────────────────────

#: The auth-regression fixture both kill drills run: base protects a
#: mutating endpoint with @PreAuthorize, head removes it. No pom.xml — the
#: differential node degrades honestly (NON_REPRODUCIBLE) while the static
#: auth checker produces exactly one finding. Deterministic, offline, fast.
AUTH_FIXTURE_SPEC_TEXT = (
    "Authentication requirement:\n"
    "The change-email endpoint must require authentication.\n"
    "Unauthenticated requests must receive 401 Unauthorized.\n"
)
AUTH_FIXTURE_CONTROLLER_REL = "src/main/java/com/example/UserController.java"
AUTH_FIXTURE_BASE_JAVA = """package com.example;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class UserController {

    @PostMapping("/api/users/change-email")
    @PreAuthorize("isAuthenticated()")
    public String changeEmail(@RequestBody String newEmail) {
        return "email-changed";
    }
}
"""
AUTH_FIXTURE_HEAD_JAVA = AUTH_FIXTURE_BASE_JAVA.replace(
    '    @PreAuthorize("isAuthenticated()")\n', "",
)


# ── Deterministic fixture repo ──────────────────────────────────────────────


def _git(root: Path, *args: str) -> None:
    """git in argument-list form (no shell, no interpolation)."""
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise DrillTargetError(
            f"git {' '.join(args)} failed: {result.stderr.strip()[:300]}"
        )


def build_deterministic_fixture(
    root: Path,
    *,
    spec_text: str,
    java_sources: Mapping[str, str],
    head_java_sources: Mapping[str, str],
    padding_files: int = 0,
    base_tag: str = "base",
    head_tag: str = "head-v1",
) -> dict[str, str]:
    """Create a minimal deterministic git fixture repo with two tagged refs.

    Commits java_sources on the default branch and tags it base_tag; then
    overwrites the keys given in head_java_sources, commits and tags
    head_tag. padding_files adds identical one-line classes on both refs to
    widen the mid-job kill window (slow, deterministic nodes only). Returns
    the job payload fields (repo_path/base_ref/head_ref/spec_path).
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "spec.md").write_text(spec_text, encoding="utf-8")
    for rel, content in java_sources.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    for i in range(padding_files):
        target = (
            root / "src" / "main" / "java" / "com" / "example" / "pad"
            / f"Pad{i:03d}.java"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            f"package com.example.pad;\n\npublic class Pad{i:03d} {{\n"
            f"    public int value() {{ return {i}; }}\n}}\n",
            encoding="utf-8",
        )
    _git(root, "init")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "base", "--no-gpg-sign")
    _git(root, "tag", base_tag)
    for rel, content in head_java_sources.items():
        (root / rel).write_text(content, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "head", "--no-gpg-sign")
    _git(root, "tag", head_tag)
    return {
        "repo_path": str(root),
        "base_ref": base_tag,
        "head_ref": head_tag,
        "spec_path": str(root / "spec.md"),
    }
