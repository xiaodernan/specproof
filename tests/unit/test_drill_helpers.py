"""Unit tests for ops.drills — the operations drill helpers (DRILLS.md).

Runs entirely on fakes: no Docker, no live MySQL/Redis/Mongo/RabbitMQ, no
network and no real sleeps. Every helper receives its storage surfaces by
injection, so these tests pin the orchestration contract the drill drivers
rely on.
"""
from __future__ import annotations

import subprocess
from collections.abc import Mapping
from typing import Any

import pytest

import ops.drills as drills
from ops.drills import (
    DrillTargetError,
    crash_window_publish,
    honest_degradation_report,
    outbox_event_id,
    resume_job,
    side_effect_counts,
    terminal_transitions,
    wait_for_checkpoint_count,
    wait_for_idempotency_key,
    wait_for_lease_available,
    wait_for_progress_event,
    wait_for_status,
)

# ── Fakes ───────────────────────────────────────────────────────────────────


class FakeCursor:
    def __init__(
        self,
        rows: list[dict[str, Any]],
        executed: list[tuple[str, tuple[Any, ...]]],
    ) -> None:
        self._rows = rows
        self._executed = executed

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self._executed.append((sql, params or ()))

    def fetchall(self) -> list[dict[str, Any]]:
        _sql, params = self._executed[-1]
        job_id, action = params[0], params[1]
        return [
            row for row in self._rows
            if row.get("job_id") == job_id and row.get("action") == action
        ]


class FakeConnection:
    def __init__(
        self,
        rows: list[dict[str, Any]],
        executed: list[tuple[str, tuple[Any, ...]]],
    ) -> None:
        self._rows = rows
        self._executed = executed

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *exc_info: Any) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor(self._rows, self._executed)


class FakeJobStore:
    """In-memory job/audit/summary surface for the accounting helpers."""

    def __init__(self, flip: dict[str, tuple[int, str]] | None = None) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self.summaries: dict[str, dict[str, Any]] = {}
        self.audit: list[dict[str, Any]] = []
        self.transitions: list[tuple[str, str]] = []
        self._executed: list[tuple[str, tuple[Any, ...]]] = []
        self.get_calls = 0
        self.flip = flip or {}

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        self.get_calls += 1
        flip = self.flip.get(job_id)
        if flip is not None and self.get_calls >= flip[0]:
            self.jobs[job_id] = {"status": flip[1]}
        return self.jobs.get(job_id)

    def get_job_summary(self, job_id: str) -> dict[str, Any] | None:
        return self.summaries.get(job_id)

    def connection(self) -> FakeConnection:
        return FakeConnection(self.audit, self._executed)

    def transition_job_status(
        self,
        job_id: str,
        to_status: str,
        *,
        from_status: str | None = None,
        worker_id: str | None = None,
        error_msg: str | None = None,
    ) -> bool:
        self.transitions.append((job_id, to_status))
        if job_id not in self.jobs:
            return False
        self.jobs[job_id]["status"] = to_status
        return True

    def save_job_summary(self, job_id: str, summary: Mapping[str, Any]) -> None:
        self.summaries[job_id] = dict(summary)
        self.jobs[job_id]["summary"] = "stored"


class FakeStream:
    def __init__(self) -> None:
        self.events: dict[str, list[dict[str, Any]]] = {}

    def xread_progress(
        self, job_id: str, from_id: str = "0", count: int = 100,
    ) -> list[dict[str, Any]]:
        return self.events.get(job_id, [])


class FakeCheckpoints:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def count_documents(self, query: Mapping[str, Any]) -> int:
        return self.counts.get(str(query["thread_id"]), 0)


class FakeRedis:
    def __init__(self) -> None:
        self.keys: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.keys.get(key)


class FakeLeases:
    def __init__(self, release_after: int | None = None) -> None:
        self.owner: dict[str, str | None] = {}
        self.released: list[tuple[str, str]] = []
        self.get_calls = 0
        self.release_after = release_after

    def acquire_lease(self, job_id: str, worker_id: str, ttl: int = 30) -> bool:
        if self.owner.get(job_id) is not None:
            return False
        self.owner[job_id] = worker_id
        return True

    def get_lease_owner(self, job_id: str) -> str | None:
        self.get_calls += 1
        if self.release_after is not None and self.get_calls >= self.release_after:
            return None
        return self.owner.get(job_id)

    def release_lease(self, job_id: str, worker_id: str) -> None:
        self.released.append((job_id, worker_id))
        if self.owner.get(job_id) == worker_id:
            self.owner[job_id] = None


class RecordingPublisher:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    def publish(
        self, routing_key: str, payload: Mapping[str, Any],
        exchange: str | None = None,
    ) -> None:
        self.published.append((routing_key, dict(payload)))


class FakeWorker:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute_job(self, job_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append((job_id, dict(payload)))
        return self.state


class AlwaysRaising:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        raise self.exc


def _verdict_fn(state: Mapping[str, Any]) -> str:
    return "BLOCKED" if state.get("confirmed_findings") else "VERIFIED"


def _summary_fn(state: Mapping[str, Any], verdict: str) -> dict[str, Any]:
    return {"verdict": verdict, "findings": state.get("confirmed_findings", [])}


# ── Polling helpers ─────────────────────────────────────────────────────────


class TestWaitForStatus:
    def test_returns_row_when_already_terminal(self) -> None:
        store = FakeJobStore()
        store.jobs["j-1"] = {"status": "BLOCKED"}
        row = wait_for_status(store, "j-1", ["BLOCKED"], timeout=0.0, interval=0.0)
        assert row is not None
        assert row["status"] == "BLOCKED"

    def test_times_out_without_match(self) -> None:
        store = FakeJobStore()
        store.jobs["j-1"] = {"status": "RUNNING"}
        assert wait_for_status(store, "j-1", ["BLOCKED"], timeout=0.0, interval=0.0) is None

    def test_flips_mid_poll(self) -> None:
        store = FakeJobStore(flip={"j-1": (3, "FAILED")})
        store.jobs["j-1"] = {"status": "RUNNING"}
        row = wait_for_status(store, "j-1", ["FAILED"], timeout=5.0, interval=0.0)
        assert row is not None
        assert row["status"] == "FAILED"


class TestWaitForProgressEvent:
    def test_finds_matching_event(self) -> None:
        stream = FakeStream()
        stream.events["j-1"] = [
            {"node": "run_static_checks", "status": "running"},
            {"node": "run_static_checks", "status": "completed"},
        ]
        event = wait_for_progress_event(
            stream, "j-1", "run_static_checks", "completed", timeout=1.0, interval=0.0,
        )
        assert event is not None
        assert event["node"] == "run_static_checks"

    def test_none_on_timeout(self) -> None:
        stream = FakeStream()
        assert wait_for_progress_event(
            stream, "j-1", "x", "y", timeout=0.0, interval=0.0,
        ) is None


class TestWaitForCheckpointCount:
    def test_reaches_min_count(self) -> None:
        checkpoints = FakeCheckpoints()
        checkpoints.counts["j-1"] = 3
        count = wait_for_checkpoint_count(checkpoints, "j-1", 2, timeout=1.0, interval=0.0)
        assert count == 3

    def test_reports_lower_count_on_timeout(self) -> None:
        checkpoints = FakeCheckpoints()
        checkpoints.counts["j-1"] = 1
        count = wait_for_checkpoint_count(checkpoints, "j-1", 2, timeout=0.0, interval=0.0)
        assert count == 1


class TestWaitForLeaseAvailable:
    def test_waits_until_released(self) -> None:
        leases = FakeLeases(release_after=3)
        leases.owner["j-1"] = "worker-old"
        assert wait_for_lease_available(leases, "j-1", timeout=5.0, interval=0.0) is True

    def test_false_when_lease_never_released(self) -> None:
        leases = FakeLeases()
        leases.owner["j-1"] = "worker-old"
        assert wait_for_lease_available(leases, "j-1", timeout=0.0, interval=0.0) is False


class TestWaitForIdempotencyKey:
    def test_detects_key(self) -> None:
        redis = FakeRedis()
        redis.keys["specproof:idempotent:outbox-7"] = "1"
        assert wait_for_idempotency_key(redis, "outbox-7", timeout=1.0, interval=0.0) is True

    def test_false_on_timeout(self) -> None:
        assert wait_for_idempotency_key(FakeRedis(), "outbox-7", timeout=0.0, interval=0.0) is False


# ── Side-effect accounting ──────────────────────────────────────────────────


_TRANSITION = "job_status_transition"


class TestSideEffectAccounting:
    def _store(self, job_id: str) -> FakeJobStore:
        store = FakeJobStore()
        store.jobs[job_id] = {"status": "BLOCKED", "summary": "stored"}
        store.summaries[job_id] = {
            "verdict": "BLOCKED",
            "findings": [{"id": "AUTH-01"}],
            "capsules": ["capsule-AUTH-01"],
            "errors": [],
        }
        store.audit = [
            {
                "job_id": job_id, "action": _TRANSITION,
                "from_status": "QUEUED", "to_status": "RUNNING",
            },
            {
                "job_id": job_id, "action": _TRANSITION,
                "from_status": "RUNNING", "to_status": "BLOCKED",
            },
            {
                "job_id": job_id, "action": _TRANSITION,
                "from_status": "RUNNING", "to_status": "BLOCKED",
            },
            {
                "job_id": job_id, "action": "job_cancelled_at_checkpoint",
                "from_status": "RUNNING", "to_status": "CANCELLED",
            },
        ]
        return store

    def test_terminal_transitions_counts_once(self) -> None:
        store = self._store("j-1")
        terminals = terminal_transitions(store, "j-1")
        assert len(terminals) == 2
        assert all(row["to_status"] == "BLOCKED" for row in terminals)

    def test_side_effect_counts_full_ledger(self) -> None:
        store = self._store("j-1")
        counts = side_effect_counts(store, "j-1")
        assert counts == {
            "terminal_transitions": 2,
            "running_transitions": 1,
            "summary_writes": 1,
            "findings": 1,
            "capsules": 1,
            "errors": 0,
        }

    def test_no_summary_row_counts_zero(self) -> None:
        store = FakeJobStore()
        store.jobs["j-2"] = {"status": "RUNNING"}
        counts = side_effect_counts(store, "j-2")
        assert counts["summary_writes"] == 0
        assert counts["terminal_transitions"] == 0


# ── Crash window ────────────────────────────────────────────────────────────


class TestCrashWindowPublish:
    def test_publishes_once_and_marks_zero_times(self) -> None:
        publisher = RecordingPublisher()
        row: dict[str, Any] = {
            "id": 7, "aggregate_id": "j-1", "routing_key": "q.p1.verify.job",
        }

        def flatten(source: Mapping[str, Any]) -> dict[str, Any]:
            return {"event_id": outbox_event_id(source), "job_id": source["aggregate_id"]}

        wire = crash_window_publish(publisher, flatten, row)
        assert len(publisher.published) == 1
        routing_key, payload = publisher.published[0]
        assert routing_key == "q.p1.verify.job"
        assert payload["event_id"] == "outbox-7"
        assert payload["job_id"] == "j-1"
        # The crash-window contract: the helper never marks the row —
        # "published_at" must not appear anywhere on the source row.
        assert "published_at" not in row
        assert wire["event_id"] == "outbox-7"


# ── Resume ──────────────────────────────────────────────────────────────────


class TestResumeJob:
    def test_lease_held_by_other_worker_refuses(self) -> None:
        leases = FakeLeases()
        leases.owner["j-1"] = "worker-old"
        worker = FakeWorker({"confirmed_findings": []})
        with pytest.raises(DrillTargetError, match="lease still held"):
            resume_job(
                worker, leases, FakeJobStore(), "j-1", {"job_id": "j-1"},
                "worker-new", verdict_fn=_verdict_fn, summary_fn=_summary_fn,
            )

    def test_success_makes_exactly_one_terminal_transition(self) -> None:
        store = FakeJobStore()
        store.jobs["j-1"] = {"status": "RUNNING"}
        leases = FakeLeases()
        worker = FakeWorker({"confirmed_findings": [{"id": "AUTH-01"}]})
        verdict = resume_job(
            worker, leases, store, "j-1", {"job_id": "j-1"},
            "worker-new", verdict_fn=_verdict_fn, summary_fn=_summary_fn,
        )
        assert verdict == "BLOCKED"
        assert store.transitions == [("j-1", "BLOCKED")]
        job = store.get_job("j-1")
        assert job is not None
        assert job["status"] == "BLOCKED"
        assert store.summaries["j-1"]["verdict"] == "BLOCKED"
        assert leases.released == [("j-1", "worker-new")]
        assert worker.calls == [("j-1", {"job_id": "j-1"})]

    def test_releases_lease_even_when_transition_refused(self) -> None:
        store = FakeJobStore()  # job missing → transition_job_status returns False
        leases = FakeLeases()
        worker = FakeWorker({"confirmed_findings": []})
        with pytest.raises(DrillTargetError, match="refused"):
            resume_job(
                worker, leases, store, "no-such-job", {"job_id": "no-such-job"},
                "worker-new", verdict_fn=_verdict_fn, summary_fn=_summary_fn,
            )
        assert leases.released == [("no-such-job", "worker-new")]


# ── Honest provider degradation ─────────────────────────────────────────────


class _StaticClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class TestHonestDegradationReport:
    def test_unreachable_endpoint_surfaces_failure(self) -> None:
        report = honest_degradation_report(
            AlwaysRaising(ConnectionError("refused")),
            max_attempts=3,
            clock=_StaticClock(),
            sleep_fn=lambda seconds: None,
        )
        assert report["attempts"] == 3
        assert report["elapsed_seconds"] == 0.0
        assert report["failure_surfaced"] is True
        assert report["result_produced"] is False
        assert report["exception_class"] == "ConnectionError"
        assert report["final_decision_reason"] == "connection"
        assert report["final_decision_retryable"] is True
        assert report["breaker_state"] == "open"
        assert report["breaker_total_failures"] == 3

    def test_working_endpoint_produces_result(self) -> None:
        report = honest_degradation_report(
            lambda: "healthy",
            max_attempts=3,
            clock=_StaticClock(),
            sleep_fn=lambda seconds: None,
        )
        assert report["attempts"] == 1
        assert report["failure_surfaced"] is False
        assert report["result_produced"] is True
        assert report["breaker_state"] == "closed"


# ── Deterministic fixture ───────────────────────────────────────────────────


class TestBuildDeterministicFixture:
    def test_creates_repo_and_tags(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any,
    ) -> None:
        commands: list[list[str]] = []

        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            argv = [str(a) for a in args[0]]
            commands.append(argv)
            return subprocess.CompletedProcess(
                args=argv, returncode=0, stdout="", stderr="",
            )

        monkeypatch.setattr("ops.drills.subprocess.run", fake_run)
        base_java = (
            "package com.example;\n\npublic class UserController {\n"
            "    @PreAuthorize(\"isAuthenticated()\")\n"
            "    public String change() { return \"ok\"; }\n}\n"
        )
        head_java = (
            "package com.example;\n\npublic class UserController {\n"
            "    public String change() { return \"ok\"; }\n}\n"
        )
        payload = drills.build_deterministic_fixture(
            tmp_path,
            spec_text="The endpoint must require authentication.",
            java_sources={"src/main/java/com/example/UserController.java": base_java},
            head_java_sources={
                "src/main/java/com/example/UserController.java": head_java,
            },
            padding_files=2,
        )
        assert payload["repo_path"] == str(tmp_path)
        assert payload["base_ref"] == "base"
        assert payload["head_ref"] == "head-v1"
        assert payload["spec_path"] == str(tmp_path / "spec.md")
        # head content wins on disk
        controller = (tmp_path / "src/main/java/com/example/UserController.java").read_text("utf-8")
        assert "@PreAuthorize" not in controller
        assert (tmp_path / "src/main/java/com/example/pad/Pad000.java").exists()
        assert (tmp_path / "src/main/java/com/example/pad/Pad001.java").exists()
        joined = [" ".join(c) for c in commands]
        assert any(c.startswith("git -C") and " init" in c for c in joined)
        assert any(c.endswith(" tag base") for c in joined)
        assert any(c.endswith(" tag head-v1") for c in joined)

    def test_git_failure_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any,
    ) -> None:
        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args=["git"], returncode=128, stdout="", stderr="boom",
            )

        monkeypatch.setattr("ops.drills.subprocess.run", fake_run)
        with pytest.raises(DrillTargetError, match="git init failed"):
            drills.build_deterministic_fixture(
                tmp_path,
                spec_text="x",
                java_sources={},
                head_java_sources={},
            )
