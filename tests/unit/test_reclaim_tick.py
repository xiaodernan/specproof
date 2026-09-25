"""#71 — the stuck-job sweep gets a clock, so the clock itself is the risk.

`reclaim_stale_running_jobs` and `recover_waiting_for_provider_jobs` were
already correct and already reachable — from a human typing
`specproof ops recover`. A job whose worker died still waited for someone to
notice. These tests pin the four things that make an automatic sweep safe to
leave running:

- it runs once per fleet, not once per replica (a shared scope lock, and no
  release of a lock this pass does not hold);
- it does not guess about the model provider — with no health probe in the
  codebase, parked jobs are only released at an operator-stated age, and that
  age is measured by the database clock like every other staleness call;
- a pass that raises leaves the timer running (the outage that broke the
  sweep is the outage that will leave jobs stuck needing the next one);
- the report says who did the work: "skipped, another holder" is not
  "checked, nothing was stuck".
"""
from __future__ import annotations

from typing import Any

import pytest

import agent.worker as worker_module
from agent.worker import ReclaimPass, Worker, run_reclaim_pass
from storage.mysql import ReclaimOutcome
from storage.redis import SCOPE_LOCK_PREFIX, RedisStore

# ── fakes shaped like the real stores ───────────────────────────


class FakeScopeRedis:
    """Stands in for RedisStore's scope-lock surface, recording every call."""

    def __init__(self, token: str | None = "tok-1", *, probe_error: str = "") -> None:
        self.token = token
        self.probe_error = probe_error
        self.acquired: list[tuple[str, int]] = []
        self.released: list[tuple[str, str]] = []
        self.closed = 0

    def acquire_scope_lock(self, scope: str, ttl: int = 300) -> str | None:
        if self.probe_error:
            raise ConnectionError(self.probe_error)
        self.acquired.append((scope, ttl))
        return self.token

    def release_scope_lock(self, scope: str, token: str) -> bool:
        self.released.append((scope, token))
        return True

    def close(self) -> None:
        self.closed += 1


class FakeReclaimStore:
    def __init__(self, outcome: ReclaimOutcome) -> None:
        self.outcome = outcome
        self.calls: list[int] = []

    def __call__(self, lease_ttl_seconds: int) -> ReclaimOutcome:
        self.calls.append(lease_ttl_seconds)
        return self.outcome


class FakeProviderStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

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
        return [("job-9", "QUEUED")]


def _outcome(**kwargs: Any) -> ReclaimOutcome:
    """A real ReclaimOutcome, so the pass reads production's field names."""
    defaults: dict[str, Any] = {
        "reclaimed": [{"id": "job-1"}],
        "candidates": 1,
        "probed": 1,
    }
    defaults.update(kwargs)
    return ReclaimOutcome(**defaults)


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    redis: FakeScopeRedis,
    reclaim: FakeReclaimStore,
    recover: FakeProviderStore,
) -> None:
    monkeypatch.setattr(worker_module, "RedisStore", lambda: redis)
    monkeypatch.setattr(worker_module, "reclaim_stale_running_jobs", reclaim)
    monkeypatch.setattr(
        worker_module, "recover_waiting_for_provider_jobs", recover
    )


def _no_reclaim() -> Any:
    def forbidden(lease_ttl_seconds: int) -> ReclaimOutcome:
        raise AssertionError("sweep ran while the scope lock was not ours")

    return forbidden


# ── one sweep per fleet ─────────────────────────────────────────


def test_sweep_runs_only_when_it_holds_the_scope_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """N replicas ticking at the same second must re-deliver each job once."""
    redis = FakeScopeRedis(token=None)
    _wire(monkeypatch, redis, _no_reclaim(), FakeProviderStore())

    result = run_reclaim_pass()

    assert result.lock_state == "held_by_other"
    assert result.ran() is False
    assert redis.released == [], "a pass that never held the lock must not release it"
    assert redis.closed == 1


def test_sweep_releases_the_token_it_was_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeScopeRedis(token="tok-77")
    reclaim = FakeReclaimStore(_outcome())
    _wire(monkeypatch, redis, reclaim, FakeProviderStore())

    result = run_reclaim_pass(lease_ttl_seconds=45)

    assert result.lock_state == "acquired"
    assert redis.acquired == [("stale-job-sweep", 120)]
    assert redis.released == [("stale-job-sweep", "tok-77")]
    assert reclaim.calls == [45], "the worker's own lease ttl governs staleness"
    assert result.reclaimed == ["job-1"]


def test_unknown_lock_state_skips_instead_of_sweeping_unlocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redis down is not "free lock": it is also the lease probe.

    Sweeping anyway would reclaim nothing (the probe stops at the first
    candidate) while risking a duplicate sweep the moment Redis returns.
    """
    redis = FakeScopeRedis(probe_error="redis unreachable")
    _wire(monkeypatch, redis, _no_reclaim(), FakeProviderStore())

    result = run_reclaim_pass()

    assert result.lock_state == "unavailable"
    assert redis.released == []


def test_lock_releases_even_when_the_sweep_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A locked-out fleet with a dead holder is the worse failure."""
    redis = FakeScopeRedis(token="tok-x")
    _wire(monkeypatch, redis, FakeReclaimStore(_outcome()), FakeProviderStore())

    def boom(lease_ttl_seconds: int) -> ReclaimOutcome:
        raise RuntimeError("mysql restarting")

    monkeypatch.setattr(worker_module, "reclaim_stale_running_jobs", boom)

    with pytest.raises(RuntimeError):
        run_reclaim_pass()

    assert redis.released == [("stale-job-sweep", "tok-x")]


# ── the provider branch must not pretend to have a health probe ──


def test_provider_wait_is_deferred_without_a_park_age(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default: only the RUNNING sweep runs.

    Releasing every WAITING_FOR_PROVIDER row on a timer would spend each
    job's retry budget while the provider is still down, converting a
    recoverable park into a FAILED job that needs a human.
    """
    redis = FakeScopeRedis()
    reclaim = FakeReclaimStore(_outcome())
    recover = FakeProviderStore()
    _wire(monkeypatch, redis, reclaim, recover)

    result = run_reclaim_pass()

    assert result.provider_recovered == []
    assert recover.calls == []


def test_park_age_is_passed_through_to_the_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sweep is the caller with no probe, so the age is the whole gate."""
    redis = FakeScopeRedis()
    recover = FakeProviderStore()
    _wire(monkeypatch, redis, FakeReclaimStore(_outcome()), recover)

    result = run_reclaim_pass(min_parked_seconds=900)

    assert result.provider_recovered == [("job-9", "QUEUED")]
    assert recover.calls == [{"provider_ready": None, "min_parked_seconds": 900}]


# ── the report says who did the work ────────────────────────────


def test_summary_distinguishes_skipped_from_checked_and_clean() -> None:
    """Both read as "nothing happened"; only one is evidence of health."""
    held = ReclaimPass(lock_state="held_by_other")
    clean = ReclaimPass(lock_state="acquired")

    assert held.summary().startswith("skipped")
    assert "reclaimed=0" in clean.summary()
    assert clean.ran() is True


def test_summary_names_the_jobs_it_moved_and_killed() -> None:
    result = ReclaimPass(
        lock_state="acquired",
        reclaimed=["job-1", "job-2"],
        exhausted=["job-3"],
    )

    text = result.summary()

    assert "reclaimed=2" in text and "job-1" in text
    assert "budget_exhausted=1" in text and "job-3" in text


# ── the tick itself ─────────────────────────────────────────────


def test_recovery_uses_the_park_age_query_only_when_aged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two row sources differ by one thing: who judges how long.

    `min_parked_seconds=0` keeps the manual command's behaviour (every
    parked row), a positive age asks the database which rows have waited
    that long. Silently reading both the same way is how an operator
    setting a threshold gets an immediate release anyway.
    """
    from agent.worker import recover_waiting_for_provider_jobs

    store = FakeRecoverStore()
    monkeypatch.setattr(worker_module, "MySQLStore", lambda: store)
    monkeypatch.setattr(worker_module, "RabbitMQClient", lambda: FakeStore())

    assert recover_waiting_for_provider_jobs(min_parked_seconds=900) == [
        ("job-aged", "QUEUED")
    ]
    assert store.aged_calls == [900]
    assert store.status_calls == []

    assert recover_waiting_for_provider_jobs() == [("job-aged", "QUEUED")]
    assert store.aged_calls == [900], "0 must not run the age query at all"
    assert store.status_calls == ["WAITING_FOR_PROVIDER"]


class FakeRecoverStore:
    """A MySQLStore stand-in that answers both parked-row queries."""

    def __init__(self) -> None:
        self.aged_calls: list[int] = []
        self.status_calls: list[str] = []

    def list_provider_wait_parked(
        self, min_parked_seconds: int
    ) -> list[dict[str, Any]]:
        self.aged_calls.append(min_parked_seconds)
        return [{"id": "job-aged", "retry_count": 0}]

    def get_jobs_by_status(self, status: str) -> list[dict[str, Any]]:
        self.status_calls.append(status)
        return [{"id": "job-aged", "retry_count": 0}]

    def recover_provider_wait(self, job_id: str) -> tuple[bool, str | None]:
        return True, "QUEUED"

    def close(self) -> None:
        return None


def _bare_worker(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> Worker:
    """A Worker wired to fakes: no MySQL/Redis/broker connection is made."""
    mysql = FakeStore()
    redis = FakeStore()
    rabbit = FakeStore()
    monkeypatch.setattr(worker_module, "MySQLStore", lambda: mysql)
    monkeypatch.setattr(worker_module, "RedisStore", lambda: redis)
    monkeypatch.setattr(worker_module, "RabbitMQClient", lambda: rabbit)
    return Worker(worker_id="w-tick", **kwargs)


class FakeStore:
    """Accepts any store method; records nothing it is not asked about."""

    def __getattr__(self, name: str) -> Any:
        def _any(*args: Any, **kwargs: Any) -> None:
            return None

        return _any


def test_interval_zero_disables_the_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opting out is allowed, but it must not look like a working sweeper."""
    worker = _bare_worker(monkeypatch, reclaim_interval=0)

    worker._start_reclaim_tick()

    assert worker._reclaim_thread is None


def test_default_interval_comes_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKER_RECLAIM_INTERVAL_SECONDS", "60")
    monkeypatch.setenv("WORKER_PROVIDER_PARK_MAX_SECONDS", "900")

    worker = _bare_worker(monkeypatch)

    assert worker.reclaim_interval == 60
    assert worker.provider_park_seconds == 900


def test_default_provider_park_is_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """No probe, no automatic release — the default has to be the safe one."""
    monkeypatch.delenv("WORKER_PROVIDER_PARK_MAX_SECONDS", raising=False)

    worker = _bare_worker(monkeypatch)

    assert worker.provider_park_seconds == 0
    assert worker.reclaim_interval == 300


def test_raising_pass_does_not_kill_the_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The point of a timer: it has to still be there next interval.

    The outage that breaks one sweep is the outage that leaves jobs stuck,
    so a sweep that dies on the first exception means the recovery is
    missing exactly when it is needed.
    """
    worker = _bare_worker(monkeypatch, reclaim_interval=0)
    seen: list[int] = []

    def pass_or_stop() -> ReclaimPass | None:
        seen.append(len(seen) + 1)
        if len(seen) == 1:
            raise RuntimeError("mysql restarting")
        worker._reclaim_stop.set()
        return ReclaimPass(lock_state="acquired")

    monkeypatch.setattr(worker, "_reclaim_once", pass_or_stop)

    worker._reclaim_loop()

    assert seen == [1, 2], "the second pass must run after the first one raised"


def test_a_raising_sweep_is_counted_and_the_tick_keeps_going(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run through the real loop and the real pass, not a patched-out one.

    The counter is what an operator can alert on: a tick that swallows a
    failure silently is worse than one that dies, because every stuck job
    then looks handled. The gauge is the other half — it is the only thing
    that answers "is the sweeper still alive".
    """
    from observability.metrics import snapshot

    worker = _bare_worker(monkeypatch, reclaim_interval=0)
    calls: list[int] = []

    def sweep(**kwargs: Any) -> ReclaimPass:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("redis gone")
        worker._reclaim_stop.set()
        return ReclaimPass(lock_state="acquired")

    monkeypatch.setattr(worker_module, "run_reclaim_pass", sweep)
    before = snapshot()["counters"].get("worker_reclaim_pass_error_total", 0.0)

    worker._reclaim_loop()

    assert len(calls) == 2, "the sweep after the failure must still run"
    snap = snapshot()
    assert snap["counters"].get("worker_reclaim_pass_error_total", 0.0) == before + 1
    assert snap["gauges"]["worker_reclaim_last_ok_timestamp_seconds"] > 0


def test_start_launches_the_tick_and_stop_joins_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wiring, not just the parts: nothing swept before this patch."""
    worker = _bare_worker(monkeypatch, reclaim_interval=3600)
    never: list[Any] = []
    monkeypatch.setattr(
        worker_module,
        "run_reclaim_pass",
        lambda **kwargs: never.append(kwargs) or ReclaimPass(lock_state="acquired"),
    )

    worker.start()
    thread = worker._reclaim_thread
    assert thread is not None and thread.is_alive()
    worker.stop()

    assert worker._reclaim_thread is None
    assert not thread.is_alive()
    assert never == [], "the first sweep waits an interval, it does not race boot"


# ── the lock primitives ─────────────────────────────────────────


class RecordingClient:
    def __init__(self, *, taken: bool = True) -> None:
        self.taken = taken
        self.sets: list[tuple[str, str, dict[str, Any]]] = []
        self.evalled: list[tuple[str, list[Any]]] = []

    def set(self, key: str, value: str, **kwargs: Any) -> bool:
        self.sets.append((key, value, kwargs))
        return self.taken

    def eval(self, script: str, num: int, *args: Any) -> int:
        self.evalled.append((script, list(args)))
        return 1


def _store(client: RecordingClient) -> RedisStore:
    store = RedisStore.__new__(RedisStore)
    store._client = client
    return store


def test_scope_lock_is_named_by_purpose_and_expires() -> None:
    client = RecordingClient()

    token = _store(client).acquire_scope_lock("stale-job-sweep", ttl=120)

    key, value, kwargs = client.sets[0]
    assert key == f"{SCOPE_LOCK_PREFIX}stale-job-sweep"
    assert kwargs == {"nx": True, "ex": 120}
    assert token is not None and value == token, "the stored value IS the holder token"


def test_scope_lock_release_sends_the_token_to_compare() -> None:
    """A bare DELETE would unlock whoever took over after our TTL."""
    client = RecordingClient()
    store = _store(client)

    token = store.acquire_scope_lock("stale-job-sweep", ttl=120)
    assert token is not None
    assert store.release_scope_lock("stale-job-sweep", token) is True

    script, args = client.evalled[0]
    assert "redis.call('get', KEYS[1]) == ARGV[1]" in script
    assert args == [f"{SCOPE_LOCK_PREFIX}stale-job-sweep", token]


def test_release_without_a_token_is_a_no_op() -> None:
    client = RecordingClient()

    assert _store(client).release_scope_lock("stale-job-sweep", "") is False
    assert client.evalled == []


def test_blank_scope_is_refused_rather_than_collided() -> None:
    """An empty name would put every fleet sweep on one shared key."""
    client = RecordingClient()

    with pytest.raises(ValueError):
        _store(client).acquire_scope_lock("   ")


# ── the park-age query judges time in SQL ───────────────────────


class _Conn:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def cursor(self) -> _Cursor:
        return _Cursor(self.executed)

    def __enter__(self) -> _Conn:
        return self

    def __exit__(self, *args: Any) -> bool:
        return False


class _Cursor:
    def __init__(self, sink: list[tuple[str, tuple[Any, ...]]]) -> None:
        self.sink = sink

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        self.sink.append((sql, params))

    def fetchall(self) -> list[dict[str, Any]]:
        return [{"id": "job-parked"}]


def test_park_age_is_measured_by_the_database_clock() -> None:
    from storage.mysql import MySQLStore

    conn = _Conn()
    store = MySQLStore.__new__(MySQLStore)
    store.connection = lambda: conn  # type: ignore[method-assign]

    rows = store.list_provider_wait_parked(900)

    sql, params = conn.executed[0]
    assert "status = 'WAITING_FOR_PROVIDER'" in sql
    assert "updated_at < (NOW(3) - INTERVAL %s SECOND)" in sql
    assert params == (900,)
    assert rows == [{"id": "job-parked"}]


def test_park_age_query_rejects_a_non_positive_threshold() -> None:
    """0 means "do not release", and that belongs to the caller, not here."""
    from storage.mysql import MySQLStore

    conn = _Conn()
    store = MySQLStore.__new__(MySQLStore)
    store.connection = lambda: conn  # type: ignore[method-assign]

    with pytest.raises(ValueError):
        store.list_provider_wait_parked(0)

    with pytest.raises(ValueError):
        store.list_provider_wait_parked(-5)

    assert conn.executed == []
