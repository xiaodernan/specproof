"""§14 任务 8 — worker cancellation checkpoints and lease-loss fail-fast.

Coverage (no Docker, no live services — MySQL/Redis and the LangGraph
stream are fakes; the executor under test is a plain fake function):

- cancel honored BEFORE a Maven/differential execution (executor skipped);
- cancel honored AFTER the execution (result discarded, wrapper raises);
- cancel honored BEFORE the next LLM retry iteration (real
  _generate_with_compile_loop, fake provider + fake compile);
- worker marks CANCELLED reason='cancelled_at_checkpoint' at a stage
  boundary and writes nothing else (no summary, no verdict, no completion
  event) — including a cancel that lands during the final stage;
- lease loss (renew_lease -> False) fails fast with reason='lease_lost'
  and stops business writes;
- lease renew count/duration + per-stage duration metrics land in
  observability.metrics, and an un-cancelled job still completes VERIFIED
  (identical behavior when not cancelled);
- the terminal write is atomic: the verdict transition itself carries the
  summary, a refused CAS announces no completion and persists no evidence, and
  a summary that cannot be built leaves no bare verdict behind (#63);
- both outward channels of a terminal failure — the GitHub Check Run and the
  webhook notification — run after the accepted write, in that order, on the
  SAME summary, and neither runs when the CAS was refused or the job parked (#65).
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

import agent.job_control as control
import agent.worker as worker_module
from agent.job_control import (
    JobCancelledError,
    check_cancelled,
    run_with_cancel_checks,
)
from agent.worker import Worker
from integrations.contract_counts import COUNT_KEYS
from storage.mysql import InvalidStateTransition


class _FakeMysql:
    """MySQLStore fake: status + recorded transitions/audits.

    The summary now travels INSIDE the terminal status transition, so an
    evidence write is observable as a ``summary=`` kwarg and nothing else.
    Deliberately no ``save_job_summary`` here: a production path that still
    used the two-write sequence would fail loudly instead of passing on a
    fake nobody calls anymore.
    """

    def __init__(
        self, status: str = "RUNNING", *, refuse: set[str] | None = None,
        raise_on: set[str] | None = None, log: list[str] | None = None,
    ) -> None:
        self.status = status
        self.refuse = refuse or set()
        self.raise_on = raise_on or set()
        self.log = log
        self.transitions: list[tuple[str, dict[str, Any]]] = []
        self.applied: list[tuple[str, dict[str, Any]]] = []
        self.audits: list[dict[str, Any]] = []
        self.provider_waits: list[dict[str, Any]] = []

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return {"id": job_id, "status": self.status, "tenant_id": None}

    def transition_job_status(
        self, job_id: str, to_status: str, **kwargs: Any,
    ) -> bool:
        if self.log is not None:
            self.log.append("w:" + to_status)
        self.transitions.append((to_status, kwargs))
        if to_status in self.raise_on:
            raise InvalidStateTransition(f"RUNNING -> {to_status} is illegal")
        if to_status in self.refuse:
            return False  # CAS lost: nothing this call carried became visible
        if kwargs.get("summary") is not None:
            self.applied.append((to_status, dict(kwargs["summary"])))
        return True

    def enter_provider_wait(
        self, job_id: str, **kwargs: Any,
    ) -> bool:
        """CAS RUNNING -> WAITING_FOR_PROVIDER (same refusal semantics)."""
        if self.log is not None:
            self.log.append("w:WAITING_FOR_PROVIDER")
        self.provider_waits.append(kwargs)
        return "WAITING_FOR_PROVIDER" not in self.refuse

    def record_audit(self, **kwargs: Any) -> None:
        self.audits.append(kwargs)

    def written_summaries(self) -> list[dict[str, Any]]:
        """Summaries that reached the row — a refused CAS persisted nothing."""
        return [summary for _status, summary in self.applied]

    def close(self) -> None:
        return None


class _FakeRedis:
    """RedisStore fake: lease + progress events."""

    def __init__(
        self, lease_ok: bool = True, log: list[str] | None = None,
    ) -> None:
        self.lease_ok = lease_ok
        self.log = log
        self.renews = 0
        self.events: list[tuple[str, str, str]] = []
        self.released: list[str] = []

    def acquire_lease(
        self, job_id: str, worker_id: str, ttl: int,
        max_hold_seconds: int | None = None,
    ) -> bool:
        return True

    def renew_lease(self, job_id: str, worker_id: str, ttl: int) -> bool:
        self.renews += 1
        return self.lease_ok

    def release_lease(self, job_id: str, worker_id: str) -> None:
        self.released.append(job_id)

    def xadd_progress(
        self, job_id: str, node: str, status: str,
        message: str = "", percent: float = 0.0,
    ) -> str:
        if self.log is not None:
            self.log.append("e:" + status)
        self.events.append((node, status, message))
        return "1-0"

    def close(self) -> None:
        return None


class _FakeGraph:
    """LangGraph stream fake: dual-mode (mode, chunk) tuples."""

    def __init__(
        self,
        stages: list[str],
        final: dict[str, Any],
        on_stage: Callable[[str], None] | None = None,
        on_values: Callable[[], None] | None = None,
    ) -> None:
        self._stages = stages
        self._final = final
        self._on_stage = on_stage
        self._on_values = on_values
        self.stream_modes: Any = None

    def stream(self, state: Any, config: Any, stream_mode: Any = None) -> Any:
        self.stream_modes = stream_mode
        for stage in self._stages:
            yield ("updates", {stage: {"_done": stage}})
            if self._on_stage is not None:
                self._on_stage(stage)
        if self._on_values is not None:
            self._on_values()
        yield ("values", self._final)


def _make_worker(
    mysql: _FakeMysql,
    redis: _FakeRedis,
    graph: _FakeGraph,
    monkeypatch: pytest.MonkeyPatch,
) -> Worker:
    monkeypatch.setattr(worker_module, "MySQLStore", lambda: mysql)
    monkeypatch.setattr(worker_module, "RedisStore", lambda: redis)
    monkeypatch.setattr(worker_module, "MongoDBSaver", lambda: None)
    monkeypatch.setattr(
        worker_module, "build_phase0_graph", lambda checkpointer=None: graph,
    )

    class _FakeRabbit:
        def close(self) -> None:
            return None

    monkeypatch.setattr(worker_module, "RabbitMQClient", _FakeRabbit)
    worker = Worker(worker_id="w-test", lease_ttl=30)
    worker._running = True
    return worker


def _final_state() -> dict[str, Any]:
    return {"errors": [], "confirmed_findings": [],
            "matrix": {"unverified": 0, "passed": 1,
                       "rows": [{"contract_id": "C-1", "result": "PASS",
                                 "experiment": "test", "evidence": "e-1"}]}}


# ── checkpoint helper: fake executor ───────────────────────────────────────


def test_cancel_before_maven_execution_skips_executor() -> None:
    """Before-checkpoint: the executor must never run on a cancelled job."""
    store = _FakeMysql(status="CANCELLED")
    calls: list[str] = []

    def fake_maven(workspace: str, **kwargs: Any) -> dict[str, Any]:
        calls.append(workspace)
        return {"exit_code": 0}

    with pytest.raises(JobCancelledError):
        run_with_cancel_checks(
            "job-1", "maven_base", fake_maven, "/ws", store=store,
        )
    assert calls == []


def test_cancel_after_maven_execution_discards_result() -> None:
    """After-checkpoint: the run happened, but its result never returns."""
    store = _FakeMysql(status="RUNNING")
    calls: list[str] = []

    def fake_maven(workspace: str, **kwargs: Any) -> dict[str, Any]:
        calls.append(workspace)
        store.status = "CANCELLED"  # user cancels while Maven runs
        return {"exit_code": 0}

    with pytest.raises(JobCancelledError):
        run_with_cancel_checks(
            "job-1", "maven_base", fake_maven, "/ws", store=store,
        )
    assert calls == ["/ws"]


def test_cancel_before_llm_retry_iteration_stops_loop() -> None:
    """Per-iteration checkpoint: attempt 2 must not reach its LLM call."""
    store = _FakeMysql(status="RUNNING")
    llm_calls: list[int] = []
    with pytest.raises(JobCancelledError):
        for attempt in (1, 2, 3):
            check_cancelled("job-1", "llm_generate_attempt", store=store)
            llm_calls.append(attempt)
            if attempt == 1:
                store.status = "CANCELLED"  # user cancels during attempt 1
    assert llm_calls == [1]


def test_real_llm_loop_honors_cancel_before_retry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """The production _generate_with_compile_loop honors the checkpoints:
    cancel during the compile of attempt 1 -> JobCancelledError before the
    LLM retry iteration 2, with the compile result never consumed."""
    from agent.nodes import generate_counterexamples as gce

    store = _FakeMysql(status="RUNNING")
    llm_calls: list[int] = []
    compile_calls: list[str] = []

    async def fake_llm(findings: Any, contracts: Any, requirement_text: str) -> str:
        llm_calls.append(len(llm_calls) + 1)
        return "class SpecProofGeneratedTest {}"

    def fake_compile(workspace: str, test_file: str) -> tuple[int, str]:
        compile_calls.append(workspace)
        store.status = "CANCELLED"  # cancel lands during the Maven compile
        return 1, "compile failed"

    monkeypatch.setattr(gce, "_get_provider", lambda: object())
    monkeypatch.setattr(gce, "_llm_generate_junit", fake_llm)
    monkeypatch.setattr(gce, "_compile_test", fake_compile)
    monkeypatch.setattr(gce, "_validate_test_schema", lambda code: [])
    monkeypatch.setattr(control, "MySQLStore", lambda: store)

    with pytest.raises(JobCancelledError):
        asyncio.run(
            gce._generate_with_compile_loop(
                str(tmp_path), [], [], "spec", job_id="job-1",
            )
        )
    assert llm_calls == [1]
    assert compile_calls == [str(tmp_path)]


# ── worker stage boundaries ────────────────────────────────────────────────


def test_worker_marks_cancelled_at_checkpoint_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cancel landing between stages marks CANCELLED with
    reason='cancelled_at_checkpoint' and performs no further side effects."""
    mysql = _FakeMysql(status="RUNNING")

    def cancel_after_intake(stage: str) -> None:
        if stage == "intake":
            mysql.status = "CANCELLED"

    graph = _FakeGraph(
        ["intake", "prepare_base", "publish_report"],
        _final_state(),
        on_stage=cancel_after_intake,
    )
    redis = _FakeRedis(lease_ok=True)
    worker = _make_worker(mysql, redis, graph, monkeypatch)

    worker._handle_job_impl("job-1", {"repo_path": "/r", "spec_path": "/s"})

    assert graph.stream_modes == ["updates", "values"]
    cancelled = [kw for t, kw in mysql.transitions if t == "CANCELLED"]
    assert len(cancelled) == 1
    assert cancelled[0]["error_msg"] == "cancelled_at_checkpoint"
    assert cancelled[0]["from_status"] == "RUNNING"
    assert any(
        a.get("detail") == "cancelled_at_checkpoint" for a in mysql.audits
    )
    assert any(m == "cancelled_at_checkpoint" for _, _, m in redis.events)
    # No further side effects: no summary, no verdict, no completion event.
    assert mysql.written_summaries() == []
    assert "VERIFIED" not in [t for t, _kw in mysql.transitions]
    assert all(node != "publish_report" for node, _, _ in redis.events)
    assert redis.released == ["job-1"]


def test_cancel_during_final_stage_stops_terminal_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cancel landing while publish_report runs must stop the terminal
    verdict write (the post-loop boundary check)."""
    mysql = _FakeMysql(status="RUNNING")
    graph = _FakeGraph(
        ["intake", "publish_report"],
        _final_state(),
        on_values=lambda: setattr(mysql, "status", "CANCELLED"),
    )
    redis = _FakeRedis(lease_ok=True)
    worker = _make_worker(mysql, redis, graph, monkeypatch)

    worker._handle_job_impl("job-2", {"repo_path": "/r", "spec_path": "/s"})

    assert any(
        t == "CANCELLED" and kw.get("error_msg") == "cancelled_at_checkpoint"
        for t, kw in mysql.transitions
    )
    assert mysql.written_summaries() == []
    assert "VERIFIED" not in [t for t, _kw in mysql.transitions]


def test_worker_lease_lost_fails_fast_without_business_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """renew_lease -> False: FAILED with reason='lease_lost', no summary."""
    mysql = _FakeMysql(status="RUNNING")
    graph = _FakeGraph(["intake", "prepare_base"], _final_state())
    redis = _FakeRedis(lease_ok=False)
    worker = _make_worker(mysql, redis, graph, monkeypatch)

    worker._handle_job_impl("job-3", {"repo_path": "/r", "spec_path": "/s"})

    failed = [kw for t, kw in mysql.transitions if t == "FAILED"]
    assert len(failed) == 1
    assert failed[0]["error_msg"] == "lease_lost"
    assert any(m == "lease_lost" for _, _, m in redis.events)
    assert mysql.written_summaries() == []
    assert "VERIFIED" not in [t for t, _kw in mysql.transitions]
    assert redis.released == ["job-3"]


# ── #66: the stop frames follow the row, not the intention ─────────────────


def test_cancel_frame_narrates_cancelled_not_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The row says CANCELLED, so the timeline must not read '执行失败' on a
    job the user cancelled — the frame's status follows the row (#66)."""
    mysql = _FakeMysql(status="RUNNING")

    def cancel_after_intake(stage: str) -> None:
        if stage == "intake":
            mysql.status = "CANCELLED"

    graph = _FakeGraph(
        ["intake", "prepare_base", "publish_report"],
        _final_state(),
        on_stage=cancel_after_intake,
    )
    redis = _FakeRedis(lease_ok=True)
    worker = _make_worker(mysql, redis, graph, monkeypatch)

    worker._handle_job_impl("job-66a", {"repo_path": "/r", "spec_path": "/s"})

    cancel_frames = [
        (node, status) for node, status, _m in redis.events
        if node == "cancel_checkpoint"
    ]
    assert cancel_frames == [("cancel_checkpoint", "cancelled")]


def test_refused_cancel_cas_with_cancelled_row_still_narrates_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The API's cancel CAS usually owns the row (this CAS's refusal is the
    norm, not an anomaly); the frame may still say 'cancelled' because a
    read-back confirms the row, and the checkpoint audit stays this
    worker's fact to record under exactly that confirmation."""
    mysql = _FakeMysql(status="RUNNING", refuse={"CANCELLED"})

    def cancel_after_intake(stage: str) -> None:
        if stage == "intake":
            mysql.status = "CANCELLED"

    graph = _FakeGraph(
        ["intake", "prepare_base", "publish_report"],
        _final_state(),
        on_stage=cancel_after_intake,
    )
    redis = _FakeRedis(lease_ok=True)
    worker = _make_worker(mysql, redis, graph, monkeypatch)

    worker._handle_job_impl("job-66b", {"repo_path": "/r", "spec_path": "/s"})

    cancel_frames = [
        (node, status) for node, status, _m in redis.events
        if node == "cancel_checkpoint"
    ]
    assert cancel_frames == [("cancel_checkpoint", "cancelled")]
    assert any(
        a.get("detail") == "cancelled_at_checkpoint" for a in mysql.audits
    )


def test_unconfirmed_cancel_narrates_nothing_and_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A row this worker cannot confirm as CANCELLED gets no cancel frame
    and no audit — silence plus a counter, never a narrated guess."""
    from observability import metrics as metrics_module

    before = metrics_module.snapshot()
    mysql = _FakeMysql(status="RUNNING", refuse={"CANCELLED"})

    def cancel_after_intake(stage: str) -> None:
        if stage == "intake":
            mysql.status = "CANCELLED"
            reads: list[str] = []

            def drifting_read(job_id: str) -> dict[str, Any]:
                reads.append(job_id)
                # First read: the boundary checkpoint observes the cancel.
                # Later reads: the row has moved on (the defensive branch) —
                # the read-back after the refused CAS no longer confirms
                # CANCELLED, so nothing may be narrated.
                status = "CANCELLED" if len(reads) == 1 else "RUNNING"
                return {"id": job_id, "status": status, "tenant_id": None}

            mysql.get_job = drifting_read

    graph = _FakeGraph(
        ["intake", "prepare_base", "publish_report"],
        _final_state(),
        on_stage=cancel_after_intake,
    )
    redis = _FakeRedis(lease_ok=True)
    worker = _make_worker(mysql, redis, graph, monkeypatch)

    worker._handle_job_impl("job-66c", {"repo_path": "/r", "spec_path": "/s"})

    assert [node for node, _s, _m in redis.events] == []
    assert mysql.audits == []
    after = metrics_module.snapshot()
    assert _counter_delta(
        after, before, "worker_cancel_checkpoint_unconfirmed_total"
    ) == 1.0


def test_lease_lost_frame_follows_the_row_when_cas_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a refused lease-lost CAS the row may already be QUEUED (the
    reclaimer requeued it) — narrating 'failed' would announce an outcome
    the row does not carry, and the retry the row promises would read as a
    death."""
    mysql = _FakeMysql(status="RUNNING", refuse={"FAILED"})
    # Read-back: the reclaimer already requeued the job.
    mysql.get_job = lambda job_id: {
        "id": job_id, "status": "QUEUED", "tenant_id": None,
    }
    graph = _FakeGraph(["intake", "prepare_base"], _final_state())
    redis = _FakeRedis(lease_ok=False)
    worker = _make_worker(mysql, redis, graph, monkeypatch)

    worker._handle_job_impl("job-66d", {"repo_path": "/r", "spec_path": "/s"})

    lease_frames = [
        (node, status) for node, status, _m in redis.events if node == "lease"
    ]
    assert lease_frames == [("lease", "queued")]


def test_lease_lost_unconfirmed_narrates_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lease-lost stop whose row state cannot be read back narrates
    nothing — the counter records the silence instead of a guessed status."""
    from observability import metrics as metrics_module

    before = metrics_module.snapshot()
    mysql = _FakeMysql(status="RUNNING", refuse={"FAILED"})

    def broken_read(job_id: str) -> dict[str, Any]:
        raise RuntimeError("mysql down")

    mysql.get_job = broken_read
    graph = _FakeGraph(["intake", "prepare_base"], _final_state())
    redis = _FakeRedis(lease_ok=False)
    worker = _make_worker(mysql, redis, graph, monkeypatch)

    worker._handle_job_impl("job-66e", {"repo_path": "/r", "spec_path": "/s"})

    assert redis.events == []
    after = metrics_module.snapshot()
    assert _counter_delta(
        after, before, "worker_lease_lost_unconfirmed_total"
    ) == 1.0


def test_worker_records_lease_and_stage_duration_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§14 任务 8 metrics: lease renew count/duration + per-stage duration
    histograms — and the un-cancelled job still completes VERIFIED."""
    from observability import metrics as metrics_module

    before = metrics_module.snapshot()
    mysql = _FakeMysql(status="RUNNING")
    graph = _FakeGraph(
        ["intake", "prepare_base", "publish_report"], _final_state(),
    )
    redis = _FakeRedis(lease_ok=True)
    worker = _make_worker(mysql, redis, graph, monkeypatch)

    worker._handle_job_impl("job-4", {"repo_path": "/r", "spec_path": "/s"})

    after = metrics_module.snapshot()

    def counter_delta(name: str) -> float:
        return after["counters"].get(name, 0.0) - before["counters"].get(name, 0.0)

    def hist_delta(name: str) -> float:
        b = before["histograms"].get(name, {}).get("count", 0)
        a = after["histograms"].get(name, {}).get("count", 0)
        return a - b

    assert counter_delta("worker_lease_renews_total") >= 3
    assert hist_delta("worker_lease_renew_seconds") >= 3
    for stage in ("intake", "prepare_base", "publish_report"):
        assert hist_delta("worker_stage_duration_seconds_" + stage) == 1
    # Identical behavior when not cancelled: honest terminal verdict, and the
    # summary that justifies it written by that same transition.
    assert "VERIFIED" in [t for t, _kw in mysql.transitions]
    assert [s["verdict"] for s in mysql.written_summaries()] == ["VERIFIED"]
    assert any(
        node == "publish_report" and status == "completed"
        for node, status, _m in redis.events
    )


# ── terminal write: the verdict and its evidence are one statement (#63) ──


def _completion_announces(events: list[tuple[str, str, str]]) -> list[str]:
    """Messages that tell the dashboard "this job is done".

    Every stage frame also carries status='completed', so the message is the
    only thing that separates "a stage finished" from "the worker declared a
    terminal verdict" — and only the second one is forbidden after a refused
    write.
    """
    return [
        message
        for _node, status, message in events
        if status == "completed" and message.startswith("Job completed")
    ]


def test_terminal_verdict_carries_its_summary_in_the_same_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A row must not announce VERIFIED without carrying the report for it.

    The worker used to flip the status first and save the summary afterwards,
    so a reader could observe a completed job with no evidence — and because
    that second write sat inside a suppressed block, a failing write left the
    job that way permanently.
    """
    mysql = _FakeMysql(status="RUNNING")
    graph = _FakeGraph(["intake", "publish_report"], _final_state())
    redis = _FakeRedis(lease_ok=True)
    worker = _make_worker(mysql, redis, graph, monkeypatch)

    worker._handle_job_impl("job-atomic", {"repo_path": "/r", "spec_path": "/s"})

    verdict_writes = [
        kw for status, kw in mysql.transitions if status == "VERIFIED"
    ]
    assert len(verdict_writes) == 1
    summary = verdict_writes[0]["summary"]
    assert summary["verdict"] == "VERIFIED", (
        "the terminal transition itself must carry the summary"
    )
    assert mysql.written_summaries() == [summary]
    assert _completion_announces(redis.events) == ["Job completed: VERIFIED"]


def test_refused_terminal_cas_announces_no_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CAS lost: this run's verdict is not the job's status.

    The reclaimer or a cancel can move the row while the worker finishes. The
    refused write persisted nothing, so announcing completion would report a
    verdict the durable record does not carry.
    """
    from observability import metrics as metrics_module

    before = metrics_module.snapshot()
    mysql = _FakeMysql(status="RUNNING", refuse={"VERIFIED"})
    graph = _FakeGraph(["intake", "publish_report"], _final_state())
    redis = _FakeRedis(lease_ok=True)
    worker = _make_worker(mysql, redis, graph, monkeypatch)

    worker._handle_job_impl("job-cas-lost", {"repo_path": "/r", "spec_path": "/s"})

    after = metrics_module.snapshot()

    def counter_delta(name: str) -> float:
        return after["counters"].get(name, 0.0) - before["counters"].get(name, 0.0)

    # The attempt happened (the run did reach a verdict) ...
    assert "VERIFIED" in [status for status, _kw in mysql.transitions]
    # ... but nothing of it became visible, and nothing claimed otherwise.
    assert mysql.written_summaries() == []
    assert counter_delta("jobs_completed_total") == 0.0
    assert counter_delta("worker_terminal_cas_lost_total") == 1.0
    assert _completion_announces(redis.events) == []
    assert redis.released == ["job-cas-lost"]


def test_summary_that_cannot_be_built_leaves_no_bare_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No evidence, no verdict: building the summary is now part of finishing.

    Before the atomic write this was the quiet failure — the row went VERIFIED
    and the suppressed summary write dropped the report. Now the exception
    reaches the handler, which fails (or parks) the job with a classified
    reason instead of announcing a conclusion nobody can check.
    """

    def boom(state: dict[str, Any], verdict: str) -> dict[str, Any]:
        raise RuntimeError("summary build exploded")

    monkeypatch.setattr(worker_module, "_state_summary", boom)
    mysql = _FakeMysql(status="RUNNING")
    graph = _FakeGraph(["intake", "publish_report"], _final_state())
    redis = _FakeRedis(lease_ok=True)
    worker = _make_worker(mysql, redis, graph, monkeypatch)

    worker._handle_job_impl("job-nosummary", {"repo_path": "/r", "spec_path": "/s"})

    statuses = [status for status, _kw in mysql.transitions]
    assert "VERIFIED" not in statuses
    assert {"FAILED", "WAITING_FOR_PROVIDER"} & set(statuses)
    assert mysql.written_summaries() == []
    assert _completion_announces(redis.events) == []


# ── failure path: announcements follow the stored outcome (#64) ──


class _RaisingGraph:
    """A pipeline that dies mid-run: there is no final state to count from."""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def stream(self, state: Any, config: Any, stream_mode: Any = None) -> Any:
        yield ("updates", {"intake": {"_done": "intake"}})
        raise self._exc


def _rate_limited() -> httpx.HTTPStatusError:
    """A retryable provider outage — the one failure the worker parks."""
    request = httpx.Request("POST", "https://provider.example/v1/chat")
    response = httpx.Response(429, request=request)
    return httpx.HTTPStatusError("Too Many Requests", request=request,
                                 response=response)


def _run_failing_job(
    monkeypatch: pytest.MonkeyPatch,
    exc: BaseException,
    *,
    refuse: set[str] | None = None,
    raise_on: set[str] | None = None,
) -> tuple[list[str], _FakeMysql, _FakeRedis, _Announcements]:
    """Run one dying job and return the ORDERED side-effect log.

    `log` interleaves row writes (``w:``), progress frames (``e:``) and
    external publications (``p:`` for the Check Run, ``n:`` for the outbound
    notification), so "announced before stored" and "announced although
    refused" are both visible as a wrong sequence rather than as an absence
    someone has to trust.
    """
    log: list[str] = []
    announcements = _Announcements()
    mysql = _FakeMysql(status="RUNNING", refuse=refuse, raise_on=raise_on, log=log)
    redis = _FakeRedis(lease_ok=True, log=log)
    worker = _make_worker(mysql, redis, _RaisingGraph(exc), monkeypatch)

    def _check(job_id: str, verdict: str, summary: dict[str, Any], *_rest: Any) -> None:
        log.append("p:" + verdict)
        announcements.published.append((verdict, summary))

    def _notify(job_id: str, summary: dict[str, Any]) -> None:
        # The verdict is read FROM the summary because that is how production
        # calls it: one summary feeds both outward channels, so the two can
        # never report the same failure differently.
        log.append("n:" + str(summary.get("verdict")))
        announcements.notified.append(summary)

    worker._maybe_publish_github_check = _check  # type: ignore[method-assign]
    worker._maybe_notify_terminal = _notify  # type: ignore[method-assign]
    worker._handle_job_impl("job-fail", {"repo_path": "/r", "spec_path": "/s"})
    return log, mysql, redis, announcements


class _Announcements:
    """Both outward channels of one terminal write, kept apart for assertions."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []
        self.notified: list[dict[str, Any]] = []


def test_failure_announces_only_after_the_row_was_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from observability import metrics as metrics_module

    before = metrics_module.snapshot()
    log, _mysql, redis, announcements = _run_failing_job(
        monkeypatch, TimeoutError("mvnw timed out"),
    )
    after = metrics_module.snapshot()

    assert log == [
        "w:RUNNING", "w:FAILED", "e:failed", "p:FAILED", "n:FAILED",
    ]
    # The frame used to carry the job id as its "stage", which the timeline
    # then printed as a raw UUID.
    assert [node for node, status, _m in redis.events if status == "failed"] == [
        "terminal"
    ]
    published, notified = announcements.published, announcements.notified
    assert len(published) == 1
    verdict, summary = published[0]
    assert verdict == "FAILED"
    # The notification is the SAME summary object the Check Run got, not a
    # second derived copy that could drift.
    assert notified == [summary]
    # No statistics existed to report, so none may be reported: this call
    # site handed the renderer literal zeros and GitHub published
    # "Contracts: 0 total — 0 passed, 0 failed, 0 unverified."
    assert not set(summary) & set(COUNT_KEYS)
    assert "findings" not in summary
    assert summary["errors"] and "timeout" in summary["errors"][0]
    assert _counter_delta(after, before, "worker_terminal_cas_lost_total") == 0.0


def test_refused_failure_write_announces_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The row is no longer this worker's to declare failed.

    A reclaimer or a cancel already moved it; the refused CAS persisted
    nothing, so a failure frame and a Check Run would report an outcome the
    durable record does not carry — and the notification channel is a third
    such outcome, the one nobody watching GitHub would ever notice.
    """
    from observability import metrics as metrics_module

    before = metrics_module.snapshot()
    log, _mysql, redis, announcements = _run_failing_job(
        monkeypatch, TimeoutError("mvnw timed out"), refuse={"FAILED"},
    )
    after = metrics_module.snapshot()

    assert log == ["w:RUNNING", "w:FAILED"]
    assert redis.events == []
    assert announcements.published == []
    assert announcements.notified == []
    assert _counter_delta(after, before, "worker_terminal_cas_lost_total") == 1.0
    # Refusing to announce is not refusing to clean up: the lease goes back.
    assert redis.released == ["job-fail"]


def test_illegal_failure_transition_announces_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same refusal through the raising door (row already CANCELLED)."""
    log, _mysql, redis, announcements = _run_failing_job(
        monkeypatch, TimeoutError("mvnw timed out"), raise_on={"FAILED"},
    )
    assert log == ["w:RUNNING", "w:FAILED"]
    assert redis.events == []
    assert announcements.published == []
    assert announcements.notified == []


def test_parked_job_reports_waiting_not_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retryable provider outage parks the row; the stream must not call it failed.

    The frame used to be written first, unconditionally, so the timeline said
    "failed" for a job whose row said WAITING_FOR_PROVIDER — and the retried
    run then completed honestly, leaving a contradiction in the stream.
    """
    from observability import metrics as metrics_module

    before = metrics_module.snapshot()
    log, mysql, redis, announcements = _run_failing_job(monkeypatch, _rate_limited())
    after = metrics_module.snapshot()

    assert log == [
        "w:RUNNING", "w:WAITING_FOR_PROVIDER", "e:waiting_for_provider",
    ]
    assert "FAILED" not in [status for status, _kw in mysql.transitions]
    assert [s for _n, s, _m in redis.events] == ["waiting_for_provider"]
    # The in-progress Check Run stays open: closing it as a failure would
    # report a conclusion the retry has not produced yet. Same for the
    # notification — a retry may still end VERIFIED.
    assert announcements.published == []
    assert announcements.notified == []
    assert _counter_delta(after, before, "worker_provider_wait_total") == 1.0
    assert _counter_delta(after, before, "worker_terminal_cas_lost_total") == 0.0


def test_refused_park_announces_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A park that lost its CAS is still a refused write."""
    log, _mysql, redis, announcements = _run_failing_job(
        monkeypatch, _rate_limited(), refuse={"WAITING_FOR_PROVIDER"},
    )
    assert log == ["w:RUNNING", "w:WAITING_FOR_PROVIDER"]
    assert redis.events == []
    assert announcements.published == []
    assert announcements.notified == []


def _counter_delta(after: dict, before: dict, name: str) -> float:
    return after["counters"].get(name, 0.0) - before["counters"].get(name, 0.0)


# ── #13.6-3: the failure can say where the run died ────────────────────────


def test_failure_summary_names_the_stage_the_run_died_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The stream's updates chunks are the only observation of "where it
    died": the row's last_error and both outward channels must record the
    last stage that COMPLETED, not a guessed stage name."""
    announcements = _Announcements()
    log: list[str] = []
    mysql = _FakeMysql(status="RUNNING", log=log)
    redis = _FakeRedis(lease_ok=True, log=log)

    def die_after_intake(stage: str) -> None:
        if stage == "intake":
            raise RuntimeError("mvnw exploded")

    graph = _FakeGraph(
        ["intake", "prepare_base"], _final_state(), on_stage=die_after_intake,
    )
    worker = _make_worker(mysql, redis, graph, monkeypatch)

    def _check(job_id: str, verdict: str, summary: dict[str, Any], *_rest: Any) -> None:
        log.append("p:" + verdict)
        announcements.published.append((verdict, summary))

    def _notify(job_id: str, summary: dict[str, Any]) -> None:
        log.append("n:" + str(summary.get("verdict")))
        announcements.notified.append(summary)

    worker._maybe_publish_github_check = _check  # type: ignore[method-assign]
    worker._maybe_notify_terminal = _notify  # type: ignore[method-assign]

    worker._handle_job_impl("job-stage", {"repo_path": "/r", "spec_path": "/s"})

    failed = [kw for t, kw in mysql.transitions if t == "FAILED"]
    assert len(failed) == 1
    envelope = json.loads(failed[0]["error_msg"])
    assert envelope["failed_after_stage"] == "intake"
    # Both channels read the same fact, and the announce order is unchanged.
    assert announcements.published[0][1]["failed_after_stage"] == "intake"
    assert announcements.notified[0]["failed_after_stage"] == "intake"
    assert log == [
        "w:RUNNING", "w:FAILED", "e:failed", "p:FAILED", "n:FAILED",
    ]


def test_failure_before_any_stage_records_no_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A run that died before any stage completed has nothing to say about
    stages — the key is absent, not empty, in both the row and the channels
    (an empty string would read as "stage known but unnamed").

    _RaisingGraph cannot play this role: it yields the intake completion
    chunk before dying, which IS a completed stage — the row then honestly
    names it (see the sibling test)."""
    announcements = _Announcements()

    class _ImmediateDeath:
        def stream(self, state: Any, config: Any, stream_mode: Any = None) -> Any:
            raise TimeoutError("died before any stage completed")
            yield  # pragma: no cover — makes this a generator function

    mysql = _FakeMysql(status="RUNNING")
    redis = _FakeRedis(lease_ok=True)
    worker = _make_worker(mysql, redis, _ImmediateDeath(), monkeypatch)

    def _check(job_id: str, verdict: str, summary: dict[str, Any], *_rest: Any) -> None:
        announcements.published.append((verdict, summary))

    def _notify(job_id: str, summary: dict[str, Any]) -> None:
        announcements.notified.append(summary)

    worker._maybe_publish_github_check = _check  # type: ignore[method-assign]
    worker._maybe_notify_terminal = _notify  # type: ignore[method-assign]

    worker._handle_job_impl("job-nostage", {"repo_path": "/r", "spec_path": "/s"})

    failed = [kw for t, kw in mysql.transitions if t == "FAILED"]
    envelope = json.loads(failed[0]["error_msg"])
    assert "failed_after_stage" not in envelope
    assert "failed_after_stage" not in announcements.published[0][1]
    assert "failed_after_stage" not in announcements.notified[0]
