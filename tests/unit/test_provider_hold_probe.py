"""#133 — the sweep's provider-readiness probe (DB-attested park freshness).

`_reclaim_once` used to pass no `provider_ready` at all, so an operator who
opted into timed provider-wait recovery (`WORKER_PROVIDER_PARK_MAX_SECONDS`)
released parked rows purely by age — spending retry budgets straight into an
ongoing outage. The probe this file pins is the cross-process signal the
ledger asked for (DRILLS §6 rows 1/2): "was any WAITING_FOR_PROVIDER row
parked within the last N seconds, by any worker, on the database clock?"

The honest reading is narrow on purpose — "nobody faulted lately" is not
"the provider is healthy" — and the hold defaults to off, so today's
behaviour is byte-for-byte what it was until an operator opts in.
"""

from __future__ import annotations

from typing import Any

import pytest

import agent.worker as worker_module
from agent.worker import ReclaimPass, Worker, run_reclaim_pass
from observability.metrics import snapshot
from storage.mysql import ReclaimOutcome

HELD = "worker_reclaim_provider_wait_held_total"
PROBE_ERROR = "worker_reclaim_provider_probe_error_total"


# ── fakes shaped like the real stores ────────────────────────────────────────


class _Cursor:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self.row = row
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        self.executed.append((sql, params))

    def fetchone(self) -> dict[str, Any] | None:
        return self.row


class _Conn:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self.cursor_obj = _Cursor(row)

    def cursor(self) -> _Cursor:
        return self.cursor_obj

    def __enter__(self) -> _Conn:
        return self

    def __exit__(self, *args: Any) -> None:
        return None


class FakeScopeRedis:
    def __init__(self, token: str | None = "tok-1") -> None:
        self.token = token
        self.closed = 0

    def acquire_scope_lock(self, scope: str, ttl: int = 300) -> str | None:
        return self.token

    def release_scope_lock(self, scope: str, token: str) -> bool:
        return True

    def close(self) -> None:
        self.closed += 1


class FakeProbeStore:
    """Answers only the freshness question; explodes on anything else."""

    def __init__(self, fresh: bool = False, error: str = "") -> None:
        self.fresh = fresh
        self.error = error
        self.hold_calls: list[int] = []

    def has_fresh_provider_park(self, within_seconds: int) -> bool:
        self.hold_calls.append(within_seconds)
        if self.error:
            raise ConnectionError(self.error)
        return self.fresh

    def get_jobs_by_status(self, status: str) -> list[dict[str, Any]]:
        raise AssertionError("freshness hold must decide before any row is read")

    def list_provider_wait_parked(
        self, min_parked_seconds: int
    ) -> list[dict[str, Any]]:
        raise AssertionError("freshness hold must decide before any row is read")

    def recover_provider_wait(
        self, job_id: str
    ) -> tuple[bool, str | None]:
        raise AssertionError("held jobs must never reach the CAS")

    def close(self) -> None:
        return None


class FakeRecover:
    """Records the probe it was given and answers it once, honestly."""

    def __init__(self, outcome: tuple[bool, str] = (True, "QUEUED")) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []
        self.probe_answers: list[bool | None] = []

    def __call__(
        self,
        *,
        provider_ready: Any = None,
        min_parked_seconds: int = 0,
    ) -> list[tuple[str, str]]:
        self.calls.append(
            {
                "provider_ready": provider_ready,
                "min_parked_seconds": min_parked_seconds,
            }
        )
        # The real function's head, faithfully: a False probe parks everything.
        answer = provider_ready() if callable(provider_ready) else None
        self.probe_answers.append(answer)
        if answer is False:
            return []
        return [("job-9", self.outcome[1])] if self.outcome[0] else []


def _outcome(**kwargs: Any) -> ReclaimOutcome:
    defaults: dict[str, Any] = {
        "reclaimed": [{"id": "job-1"}],
        "candidates": 1,
        "probed": 1,
    }
    defaults.update(kwargs)
    return ReclaimOutcome(**defaults)


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    probe_store: FakeProbeStore,
    recover: FakeRecover,
    *,
    reclaimed: list[dict[str, Any]] | None = None,
) -> FakeScopeRedis:
    redis = FakeScopeRedis()
    monkeypatch.setattr(worker_module, "RedisStore", lambda: redis)
    monkeypatch.setattr(worker_module, "MySQLStore", lambda: probe_store)

    def reclaim(lease_ttl_seconds: int) -> ReclaimOutcome:
        return _outcome(
            reclaimed=reclaimed if reclaimed is not None else [{"id": "job-1"}]
        )

    monkeypatch.setattr(worker_module, "reclaim_stale_running_jobs", reclaim)
    monkeypatch.setattr(
        worker_module, "recover_waiting_for_provider_jobs", recover
    )
    return redis


def _counters() -> dict[str, float]:
    return dict(snapshot()["counters"])


# ── the store question ───────────────────────────────────────────────────────


def test_freshness_query_uses_the_database_clock() -> None:
    from storage.mysql import MySQLStore

    conn = _Conn({"1": 1})
    store = MySQLStore.__new__(MySQLStore)
    store.connection = lambda: conn  # type: ignore[assignment, return-value]

    assert store.has_fresh_provider_park(300) is True

    sql, params = conn.cursor_obj.executed[0]
    assert "status = 'WAITING_FOR_PROVIDER'" in sql
    assert "updated_at > (NOW(3) - INTERVAL %s SECOND)" in sql
    assert "LIMIT 1" in sql
    assert params == (300,)

    conn2 = _Conn(None)
    store2 = MySQLStore.__new__(MySQLStore)
    store2.connection = lambda: conn2  # type: ignore[assignment, return-value]
    assert store2.has_fresh_provider_park(300) is False


def test_freshness_query_rejects_a_non_positive_window() -> None:
    from storage.mysql import MySQLStore

    conn = _Conn({"1": 1})
    store = MySQLStore.__new__(MySQLStore)
    store.connection = lambda: conn  # type: ignore[assignment, return-value]

    with pytest.raises(ValueError):
        store.has_fresh_provider_park(0)
    with pytest.raises(ValueError):
        store.has_fresh_provider_park(-5)

    assert conn.cursor_obj.executed == []


# ── the sweep's hold ─────────────────────────────────────────────────────────


def test_hold_keeps_every_parked_row_without_reading_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe_store = FakeProbeStore(fresh=True)
    recover = FakeRecover()
    _wire(monkeypatch, probe_store, recover)
    before = _counters()

    result = run_reclaim_pass(
        min_parked_seconds=900, provider_hold_seconds=300,
    )

    assert result.provider_recovered == []
    assert probe_store.hold_calls == [300]
    # The recover function is still the one that enforces the hold — it is
    # called with the probe, and the probe answers False before any row is
    # read (FakeProbeStore's row methods are tripwires: they raise).
    assert len(recover.calls) == 1
    assert recover.probe_answers == [False]
    after = _counters()
    assert after.get(HELD, 0.0) == before.get(HELD, 0.0) + 1


def test_stale_window_releases_by_age(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe_store = FakeProbeStore(fresh=False)
    recover = FakeRecover()
    _wire(monkeypatch, probe_store, recover)

    result = run_reclaim_pass(
        min_parked_seconds=900, provider_hold_seconds=300,
    )

    assert result.provider_recovered == [("job-9", "QUEUED")]
    assert len(recover.calls) == 1
    assert recover.calls[0]["min_parked_seconds"] == 900
    assert callable(recover.calls[0]["provider_ready"])
    assert recover.probe_answers == [True]


def test_hold_is_off_by_default_and_asks_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe_store = FakeProbeStore(fresh=True)
    recover = FakeRecover()
    _wire(monkeypatch, probe_store, recover)

    result = run_reclaim_pass(min_parked_seconds=900)

    assert result.provider_recovered == [("job-9", "QUEUED")]
    assert probe_store.hold_calls == []
    assert recover.calls[0]["provider_ready"] is None


def test_an_explicit_probe_always_wins_over_the_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe_store = FakeProbeStore(fresh=False)
    recover = FakeRecover()
    _wire(monkeypatch, probe_store, recover)
    explicit = lambda: False  # noqa: E731 — the probe under test, not production code

    result = run_reclaim_pass(
        min_parked_seconds=900,
        provider_hold_seconds=300,
        provider_ready=explicit,
    )

    assert result.provider_recovered == []
    assert recover.calls[0]["provider_ready"] is explicit
    assert probe_store.hold_calls == [], "the explicit probe replaces the DB one"


def test_a_blind_probe_holds_and_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe_store = FakeProbeStore(error="redis is gone, and so is mysql")
    recover = FakeRecover()
    _wire(monkeypatch, probe_store, recover)
    before = _counters()

    result = run_reclaim_pass(
        min_parked_seconds=900, provider_hold_seconds=300,
    )

    assert result.provider_recovered == []
    assert len(recover.calls) == 1
    assert recover.probe_answers == [False]
    after = _counters()
    assert after.get(PROBE_ERROR, 0.0) == before.get(PROBE_ERROR, 0.0) + 1
    assert after.get(HELD, 0.0) == before.get(HELD, 0.0), (
        "a probe error is 'unknown', not 'fresh' — the two counters stay apart"
    )


def test_hold_does_not_touch_the_running_lane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh provider parks hold the provider lane only; RUNNING still sweeps."""
    probe_store = FakeProbeStore(fresh=True)
    recover = FakeRecover()
    _wire(monkeypatch, probe_store, recover, reclaimed=[{"id": "job-old"}])

    result = run_reclaim_pass(
        min_parked_seconds=900, provider_hold_seconds=300,
    )

    assert result.reclaimed == ["job-old"]
    assert result.provider_recovered == []


def test_no_park_timer_no_hold_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe_store = FakeProbeStore(fresh=True)
    recover = FakeRecover()
    _wire(monkeypatch, probe_store, recover)

    result = run_reclaim_pass(provider_hold_seconds=300)

    assert result.provider_recovered == []
    assert recover.calls == []
    assert probe_store.hold_calls == [], "without a park timer there is nothing to hold"


# ── worker wiring ────────────────────────────────────────────────────────────


def _bare_worker(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> Worker:
    monkeypatch.setattr(worker_module, "MySQLStore", lambda: None)
    monkeypatch.setattr(worker_module, "RedisStore", lambda: None)
    monkeypatch.setattr(worker_module, "RabbitMQClient", lambda: None)
    return Worker(worker_id="w-hold", **kwargs)


def test_hold_defaults_to_off_and_comes_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WORKER_PROVIDER_HOLD_SECONDS", raising=False)
    assert _bare_worker(monkeypatch).provider_hold_seconds == 0

    monkeypatch.setenv("WORKER_PROVIDER_HOLD_SECONDS", "120")
    assert _bare_worker(monkeypatch).provider_hold_seconds == 120
    assert _bare_worker(monkeypatch, provider_hold_seconds=45).provider_hold_seconds == 45


def test_reclaim_once_forwards_the_hold_to_the_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _bare_worker(
        monkeypatch, provider_park_seconds=900, provider_hold_seconds=300,
    )
    seen: dict[str, Any] = {}

    def capture(**kwargs: Any) -> ReclaimPass:
        seen.update(kwargs)
        return ReclaimPass(lock_state="acquired")

    monkeypatch.setattr(worker_module, "run_reclaim_pass", capture)

    worker._reclaim_once()

    assert seen["min_parked_seconds"] == 900
    assert seen["provider_hold_seconds"] == 300
    assert "provider_hold_seconds" in seen, "the tick must name the probe window"
