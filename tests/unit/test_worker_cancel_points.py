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
  (identical behavior when not cancelled).
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import agent.job_control as control
import agent.worker as worker_module
from agent.job_control import (
    JobCancelledError,
    check_cancelled,
    run_with_cancel_checks,
)
from agent.worker import Worker


class _FakeMysql:
    """MySQLStore fake: status + recorded transitions/audits/summaries."""

    def __init__(self, status: str = "RUNNING") -> None:
        self.status = status
        self.transitions: list[tuple[str, dict[str, Any]]] = []
        self.audits: list[dict[str, Any]] = []
        self.summaries: list[tuple[str, dict[str, Any]]] = []

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return {"id": job_id, "status": self.status, "tenant_id": None}

    def transition_job_status(
        self, job_id: str, to_status: str, **kwargs: Any,
    ) -> bool:
        self.transitions.append((to_status, kwargs))
        return True

    def record_audit(self, **kwargs: Any) -> None:
        self.audits.append(kwargs)

    def save_job_summary(self, job_id: str, summary: dict[str, Any]) -> None:
        self.summaries.append((job_id, summary))

    def close(self) -> None:
        return None


class _FakeRedis:
    """RedisStore fake: lease + progress events."""

    def __init__(self, lease_ok: bool = True) -> None:
        self.lease_ok = lease_ok
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
    return {"errors": [], "confirmed_findings": [], "matrix": {"unverified": 0}}


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
    assert mysql.summaries == []
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
    assert mysql.summaries == []
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
    assert mysql.summaries == []
    assert "VERIFIED" not in [t for t, _kw in mysql.transitions]
    assert redis.released == ["job-3"]


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
    # Identical behavior when not cancelled: honest terminal verdict + summary.
    assert "VERIFIED" in [t for t, _kw in mysql.transitions]
    assert len(mysql.summaries) == 1
    assert any(
        node == "publish_report" and status == "completed"
        for node, status, _m in redis.events
    )
