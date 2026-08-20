"""Backlog #5 - stale-RUNNING reclaimer + WAITING_FOR_PROVIDER wiring.

All tests are offline: the MySQL layer is faked with an in-memory job table
whose cursor implements exactly the reclaim CAS semantics
(status='RUNNING' AND updated_at < now-ttl), the lease heartbeat is a
probe function, and the worker wiring runs against fake stores - no real
MySQL / Redis / RabbitMQ is touched.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest

import agent.worker as worker_module
from agent.worker import Worker
from storage.mysql import (
    PROVIDER_WAIT_EXHAUSTED_REASON,
    RECLAIM_STALE_RUNNING_ACTION,
    MySQLStore,
)

NOW = datetime(2026, 8, 20, 12, 0, 0)


class FakeJobTable:
    """verification_jobs rows + the exact reclaim CAS predicate semantics."""

    def __init__(self, rows: list[dict[str, Any]], now: datetime) -> None:
        self.now = now
        self.rows: dict[str, dict[str, Any]] = {
            str(row["id"]): dict(row) for row in rows
        }

    def cutoff(self, ttl_seconds: int) -> datetime:
        return self.now - timedelta(seconds=ttl_seconds)

    def stale_running_candidates(self, ttl_seconds: int) -> list[dict[str, Any]]:
        cutoff = self.cutoff(ttl_seconds)
        candidates = [
            dict(row)
            for row in self.rows.values()
            if row["status"] == "RUNNING" and row["updated_at"] < cutoff
        ]
        candidates.sort(key=lambda row: (row["updated_at"], str(row["id"])))
        return candidates

    def reclaim_cas(self, job_id: str, ttl_seconds: int, reason: str) -> int:
        """Apply the reclaim UPDATE; returns the matched row count (0 or 1)."""
        row = self.rows.get(job_id)
        if row is None:
            return 0
        if row["status"] != "RUNNING" or row["updated_at"] >= self.cutoff(
            ttl_seconds
        ):
            return 0
        row["status"] = "QUEUED"
        row["worker_id"] = None
        row["retry_count"] = int(row.get("retry_count") or 0) + 1
        row["last_error"] = reason
        row["updated_at"] = self.now
        return 1


class FakeCursor:
    """Cursor that evaluates only the two reclaimer statements."""

    def __init__(self, table: FakeJobTable) -> None:
        self.table = table
        self.sql = ""
        self.params: list[Any] = []
        self._select_rows: list[dict[str, Any]] = []
        self.rowcount = 0

    def execute(
        self, sql: str, params: tuple[Any, ...] | list[Any] | None = None,
    ) -> None:
        self.sql = sql
        self.params = list(params or [])
        self._select_rows = []
        self.rowcount = 0
        if sql.startswith("SELECT id, repo_path"):
            self._select_rows = self.table.stale_running_candidates(
                int(self.params[0])
            )
        elif sql.startswith("UPDATE verification_jobs SET status = 'QUEUED'"):
            reason = str(self.params[0])
            job_id = str(self.params[1])
            ttl = int(self.params[2])
            self.rowcount = self.table.reclaim_cas(job_id, ttl, reason)

    def fetchall(self) -> list[dict[str, Any]]:
        return self._select_rows


class FakeConn:
    """Connection whose cursor() returns a cursor over the shared table."""

    def __init__(self, table: FakeJobTable) -> None:
        self.table = table

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.table)


def _job(
    job_id: str,
    status: str,
    updated_at: datetime,
    **extra: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": job_id,
        "repo_path": "/test/repo",
        "base_ref": "base",
        "head_ref": "head-v1",
        "spec_path": "/test/spec.md",
        "depth": "FAST",
        "retry_count": 0,
        "max_retries": 3,
        "worker_id": "w-1",
        "last_error": None,
        "status": status,
        "updated_at": updated_at,
    }
    row.update(extra)
    return row


def _store_with_fake_db(
    table: FakeJobTable,
) -> tuple[MySQLStore, list[dict[str, Any]]]:
    """MySQLStore whose connection/audit run against the in-memory table."""
    store = MySQLStore()
    audits: list[dict[str, Any]] = []

    @contextmanager
    def fake_connection() -> Iterator[FakeConn]:
        yield FakeConn(table)

    def fake_audit(**kwargs: Any) -> None:
        audits.append(kwargs)

    store.connection = fake_connection  # type: ignore[method-assign]
    store.record_audit = fake_audit  # type: ignore[method-assign]
    return store, audits


def _never_alive(job_id: str) -> bool:
    return False


def test_reclaims_stale_running_job_and_audits() -> None:
    table = FakeJobTable(
        [_job("j-stale", "RUNNING", NOW - timedelta(seconds=120), worker_id="w-9")],
        NOW,
    )
    store, audits = _store_with_fake_db(table)

    reclaimed = store.reclaim_stale_running(30, lease_alive=_never_alive)

    assert [row["id"] for row in reclaimed] == ["j-stale"]
    row = table.rows["j-stale"]
    assert row["status"] == "QUEUED"
    assert row["worker_id"] is None
    assert row["retry_count"] == 1
    reason = json.loads(row["last_error"])
    assert reason["reason"] == "stale_running_reclaimed"
    assert reason["lease_ttl_seconds"] == 30
    assert reason["previous_worker"] == "w-9"
    assert len(audits) == 1
    audit = audits[0]
    assert audit["action"] == RECLAIM_STALE_RUNNING_ACTION
    assert audit["from_status"] == "RUNNING"
    assert audit["to_status"] == "QUEUED"
    assert audit["job_id"] == "j-stale"
    assert "stale_running_reclaimed" in audit["detail"]


def test_live_lease_heartbeat_skips_candidate() -> None:
    table = FakeJobTable(
        [_job("j-alive", "RUNNING", NOW - timedelta(seconds=120))], NOW
    )
    store, audits = _store_with_fake_db(table)

    def alive(job_id: str) -> bool:
        return job_id == "j-alive"

    reclaimed = store.reclaim_stale_running(30, lease_alive=alive)

    assert reclaimed == []
    assert table.rows["j-alive"]["status"] == "RUNNING"
    assert audits == []


def test_fresh_updated_at_within_ttl_is_not_reclaimed() -> None:
    table = FakeJobTable(
        [_job("j-fresh", "RUNNING", NOW - timedelta(seconds=10))], NOW
    )
    store, audits = _store_with_fake_db(table)

    reclaimed = store.reclaim_stale_running(30, lease_alive=_never_alive)

    assert reclaimed == []
    assert table.rows["j-fresh"]["status"] == "RUNNING"
    assert audits == []


def test_non_running_rows_are_untouched() -> None:
    table = FakeJobTable(
        [
            _job("j-queued", "QUEUED", NOW - timedelta(seconds=120)),
            _job("j-failed", "FAILED", NOW - timedelta(seconds=120)),
            _job("j-verified", "VERIFIED", NOW - timedelta(seconds=120)),
        ],
        NOW,
    )
    store, audits = _store_with_fake_db(table)

    reclaimed = store.reclaim_stale_running(30, lease_alive=_never_alive)

    assert reclaimed == []
    assert audits == []
    assert table.rows["j-queued"]["status"] == "QUEUED"
    assert table.rows["j-failed"]["status"] == "FAILED"
    assert table.rows["j-verified"]["status"] == "VERIFIED"


def test_reclaimer_is_idempotent() -> None:
    table = FakeJobTable(
        [_job("j-stale", "RUNNING", NOW - timedelta(seconds=120))], NOW
    )
    store, audits = _store_with_fake_db(table)

    first = store.reclaim_stale_running(30, lease_alive=_never_alive)
    second = store.reclaim_stale_running(30, lease_alive=_never_alive)

    assert [row["id"] for row in first] == ["j-stale"]
    assert second == []
    assert len(audits) == 1
    assert table.rows["j-stale"]["retry_count"] == 1


def test_reclaim_cas_lost_race_is_not_counted() -> None:
    table = FakeJobTable(
        [_job("j-stale", "RUNNING", NOW - timedelta(seconds=120))], NOW
    )
    store, audits = _store_with_fake_db(table)

    # Another reclaimer wins between our SELECT and our UPDATE: the row is
    # already QUEUED when our CAS runs, so it matches 0 rows.
    original = table.reclaim_cas

    def win_race(job_id: str, ttl_seconds: int, reason: str) -> int:
        if table.rows[job_id]["status"] == "RUNNING":
            table.rows[job_id]["status"] = "QUEUED"
        return original(job_id, ttl_seconds, reason)

    table.reclaim_cas = win_race  # type: ignore[method-assign]

    reclaimed = store.reclaim_stale_running(30, lease_alive=_never_alive)

    assert reclaimed == []
    assert audits == []
    assert table.rows["j-stale"]["retry_count"] == 0


def test_reclaimer_rejects_zero_ttl() -> None:
    store, _ = _store_with_fake_db(FakeJobTable([], NOW))
    with pytest.raises(ValueError):
        store.reclaim_stale_running(0, lease_alive=_never_alive)


def test_reclaims_every_stale_job_exactly_once() -> None:
    table = FakeJobTable(
        [
            _job("j-a", "RUNNING", NOW - timedelta(seconds=200)),
            _job("j-b", "RUNNING", NOW - timedelta(seconds=100)),
            _job("j-c", "RUNNING", NOW - timedelta(seconds=10)),
        ],
        NOW,
    )
    store, audits = _store_with_fake_db(table)

    reclaimed = store.reclaim_stale_running(30, lease_alive=_never_alive)

    assert sorted(row["id"] for row in reclaimed) == ["j-a", "j-b"]
    assert len(audits) == 2
    assert table.rows["j-c"]["status"] == "RUNNING"


class WaitState:
    """Mutable job row + transition recording for the provider-wait fakes."""

    def __init__(self, status: str, retry_count: int, max_retries: int) -> None:
        self.status = status
        self.retry_count = retry_count
        self.max_retries = max_retries
        self.calls: list[tuple[str, dict[str, Any]]] = []


def _wait_store(
    state: WaitState, *, transition_result: bool = True,
) -> MySQLStore:
    """MySQLStore whose get_job/transition run against one WaitState row."""
    store = MySQLStore()

    def fake_get_job(job_id: str) -> dict[str, Any]:
        return {
            "id": job_id,
            "status": state.status,
            "retry_count": state.retry_count,
            "max_retries": state.max_retries,
        }

    def fake_transition(job_id: str, to_status: str, **kwargs: Any) -> bool:
        if not transition_result or kwargs.get("from_status") != state.status:
            return False
        state.calls.append((to_status, kwargs))
        state.status = to_status
        if kwargs.get("increment_retry"):
            state.retry_count += 1
        return True

    def fake_audit(**kwargs: Any) -> None:
        return None

    store.get_job = fake_get_job  # type: ignore[method-assign]
    store.transition_job_status = fake_transition  # type: ignore[method-assign]
    store.record_audit = fake_audit  # type: ignore[method-assign]
    return store


def test_enter_provider_wait_records_entry() -> None:
    state = WaitState("RUNNING", 0, 3)
    store = _wait_store(state)
    audits: list[dict[str, Any]] = []

    def fake_audit(**kwargs: Any) -> None:
        audits.append(kwargs)

    store.record_audit = fake_audit  # type: ignore[method-assign]

    changed = store.enter_provider_wait("j1", worker_id="w-1", error_msg="429")

    assert changed is True
    assert state.status == "WAITING_FOR_PROVIDER"
    assert state.calls == [
        (
            "WAITING_FOR_PROVIDER",
            {
                "from_status": "RUNNING",
                "worker_id": "w-1",
                "error_msg": "429",
            },
        )
    ]
    entry = [a for a in audits if a["action"] == "job_provider_wait_entered"]
    assert len(entry) == 1
    assert entry[0]["from_status"] == "RUNNING"
    assert entry[0]["to_status"] == "WAITING_FOR_PROVIDER"
    assert entry[0]["job_id"] == "j1"


def test_enter_provider_wait_cas_failure_no_audit() -> None:
    state = WaitState("QUEUED", 0, 3)
    store = _wait_store(state, transition_result=False)
    audits: list[dict[str, Any]] = []

    def fake_audit(**kwargs: Any) -> None:
        audits.append(kwargs)

    store.record_audit = fake_audit  # type: ignore[method-assign]

    changed = store.enter_provider_wait("j1", error_msg="x")

    assert changed is False
    assert audits == []
    assert state.status == "QUEUED"


def test_recover_under_budget_requeues_with_retry_increment() -> None:
    state = WaitState("WAITING_FOR_PROVIDER", 1, 3)
    store = _wait_store(state)

    changed, new_status = store.recover_provider_wait("j1")

    assert changed is True
    assert new_status == "QUEUED"
    assert state.status == "QUEUED"
    assert state.retry_count == 2
    assert state.calls == [
        (
            "QUEUED",
            {
                "from_status": "WAITING_FOR_PROVIDER",
                "increment_retry": True,
                "error_msg": None,
            },
        )
    ]


def test_recover_budget_exhausted_fails() -> None:
    state = WaitState("WAITING_FOR_PROVIDER", 3, 3)
    store = _wait_store(state)

    changed, new_status = store.recover_provider_wait("j1")

    assert changed is True
    assert new_status == "FAILED"
    assert state.status == "FAILED"
    assert state.retry_count == 3  # the FAILED path never bumps the budget
    assert state.calls == [
        (
            "FAILED",
            {
                "from_status": "WAITING_FOR_PROVIDER",
                "error_msg": PROVIDER_WAIT_EXHAUSTED_REASON,
            },
        )
    ]


def test_recover_wrong_status_is_noop() -> None:
    state = WaitState("RUNNING", 0, 3)
    store = _wait_store(state)

    changed, new_status = store.recover_provider_wait("j1")

    assert changed is False
    assert new_status is None
    assert state.calls == []


def test_recover_missing_job_is_noop() -> None:
    store = MySQLStore()

    def no_job(job_id: str) -> None:
        return None

    store.get_job = no_job  # type: ignore[method-assign]

    changed, new_status = store.recover_provider_wait("ghost")

    assert changed is False
    assert new_status is None


class FakeWorkerMysql:
    def __init__(self, retry_count: int = 0, max_retries: int = 3) -> None:
        self.retry_count = retry_count
        self.max_retries = max_retries
        self.transitions: list[tuple[str, dict[str, Any]]] = []
        self.waits: list[tuple[str, dict[str, Any]]] = []

    def get_job(self, job_id: str) -> dict[str, Any]:
        return {
            "id": job_id,
            "status": "RUNNING",
            "tenant_id": None,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
        }

    def transition_job_status(
        self, job_id: str, to_status: str, **kwargs: Any,
    ) -> bool:
        self.transitions.append((to_status, kwargs))
        return True

    def enter_provider_wait(self, job_id: str, **kwargs: Any) -> bool:
        self.waits.append((job_id, kwargs))
        return True

    def save_job_summary(self, job_id: str, summary: dict[str, Any]) -> None:
        return None


class FakeWorkerRedis:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, str]] = []
        self.released: list[str] = []

    def acquire_lease(
        self, job_id: str, worker_id: str, ttl: int,
        max_hold_seconds: int | None = None,
    ) -> bool:
        return True

    def renew_lease(self, job_id: str, worker_id: str, ttl: int) -> bool:
        return True

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


class FakeWorkerRabbit:
    def close(self) -> None:
        return None


class ProviderDownGraph:
    """Graph stream that raises the configured provider HTTP error."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def stream(self, state: Any, config: Any, stream_mode: Any = None) -> Any:
        request = httpx.Request("POST", "http://provider.invalid/chat")
        response = httpx.Response(self.status_code, request=request)
        raise httpx.HTTPStatusError(
            "provider error", request=request, response=response
        )


def _worker_with_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
    mysql: FakeWorkerMysql,
    status_code: int,
) -> tuple[Worker, FakeWorkerRedis, list[str]]:
    redis = FakeWorkerRedis()
    monkeypatch.setattr(worker_module, "MySQLStore", lambda: mysql)
    monkeypatch.setattr(worker_module, "RedisStore", lambda: redis)
    monkeypatch.setattr(worker_module, "MongoDBSaver", lambda: None)
    monkeypatch.setattr(
        worker_module, "build_phase0_graph",
        lambda checkpointer=None: ProviderDownGraph(status_code),
    )
    monkeypatch.setattr(worker_module, "RabbitMQClient", FakeWorkerRabbit)
    worker = Worker(worker_id="w-provider", lease_ttl=30)
    worker._running = True
    published: list[str] = []

    def record_publish(
        job_id: str, verdict: str, summary: dict[str, Any],
        final_state: dict[str, Any] | None = None,
    ) -> None:
        published.append(verdict)

    worker._maybe_publish_github_check = record_publish  # type: ignore[method-assign]
    return worker, redis, published


def test_worker_parks_retryable_provider_error_in_provider_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mysql = FakeWorkerMysql(retry_count=0, max_retries=3)
    worker, redis, published = _worker_with_provider_failure(
        monkeypatch, mysql, status_code=503,
    )

    worker._handle_job_impl("job-p", {"repo_path": "/r", "spec_path": "/s"})

    assert [to for to, _ in mysql.transitions] == ["RUNNING"]  # claim only
    assert len(mysql.waits) == 1
    wait_job_id, wait_kwargs = mysql.waits[0]
    assert wait_job_id == "job-p"
    assert wait_kwargs["worker_id"] == "w-provider"
    reason = json.loads(wait_kwargs["error_msg"])
    assert reason["class"] == "provider"
    assert reason["code"] == "provider_server_error"
    assert reason["retryable"] is True
    assert published == []  # parked job keeps its in-progress Check Run
    assert redis.released == ["job-p"]


def test_worker_budget_exhausted_fails_instead_of_parking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mysql = FakeWorkerMysql(retry_count=3, max_retries=3)
    worker, _, published = _worker_with_provider_failure(
        monkeypatch, mysql, status_code=503,
    )

    worker._handle_job_impl("job-p", {"repo_path": "/r", "spec_path": "/s"})

    assert mysql.waits == []
    assert [to for to, _ in mysql.transitions] == ["RUNNING", "FAILED"]
    assert published == ["FAILED"]


def test_worker_non_retryable_provider_error_still_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mysql = FakeWorkerMysql(retry_count=0, max_retries=3)
    worker, _, published = _worker_with_provider_failure(
        monkeypatch, mysql, status_code=401,
    )

    worker._handle_job_impl("job-p", {"repo_path": "/r", "spec_path": "/s"})

    assert mysql.waits == []
    assert [to for to, _ in mysql.transitions] == ["RUNNING", "FAILED"]
    failed = mysql.transitions[1][1]["error_msg"]
    reason = json.loads(failed)
    assert reason["class"] == "provider"
    assert reason["code"] == "provider_auth"
    assert reason["retryable"] is False
    assert published == ["FAILED"]


class FakeReclaimStore:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[int, Callable[[str], bool]]] = []

    def reclaim_stale_running(
        self, lease_ttl_seconds: int, *, lease_alive: Callable[[str], bool],
    ) -> list[dict[str, Any]]:
        self.calls.append((lease_ttl_seconds, lease_alive))
        return list(self.rows)

    def close(self) -> None:
        return None


class FakeLeaseRedis:
    def __init__(self, owner: str | None = None) -> None:
        self.owner = owner

    def get_lease_owner(self, job_id: str) -> str | None:
        return self.owner

    def close(self) -> None:
        return None


class FakeRabbit:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    def publish(
        self, routing_key: str, payload: dict[str, Any],
        exchange: str | None = None,
    ) -> None:
        self.published.append((routing_key, payload))

    def close(self) -> None:
        return None


_RECLAIMED_ROW = {
    "id": "j1",
    "repo_path": "/r",
    "base_ref": "base",
    "head_ref": "head",
    "spec_path": "/s",
    "depth": "FAST",
    "retry_count": 1,
}


def test_standalone_reclaimer_wires_lease_probe_and_redelivers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeReclaimStore([dict(_RECLAIMED_ROW)])
    redis = FakeLeaseRedis(owner=None)
    rabbit = FakeRabbit()
    monkeypatch.setattr(worker_module, "MySQLStore", lambda: store)
    monkeypatch.setattr(worker_module, "RedisStore", lambda: redis)
    monkeypatch.setattr(worker_module, "RabbitMQClient", lambda: rabbit)

    result = worker_module.reclaim_stale_running_jobs(lease_ttl_seconds=30)

    assert result == [dict(_RECLAIMED_ROW)]
    assert store.calls[0][0] == 30
    probe = store.calls[0][1]
    assert probe("j1") is False  # lease key absent -> heartbeat dead
    redis.owner = "w-live"
    assert probe("j1") is True  # lease key held -> heartbeat alive
    assert rabbit.published == [
        (
            "q.p1.verify.job",
            {
                "job_id": "j1",
                "repo_path": "/r",
                "base_ref": "base",
                "head_ref": "head",
                "spec_path": "/s",
                "depth": "FAST",
                "event_id": "retry-j1-1",
            },
        )
    ]


def test_standalone_reclaimer_tolerates_redelivery_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeReclaimStore([dict(_RECLAIMED_ROW)])
    redis = FakeLeaseRedis(owner=None)

    class BrokenRabbit(FakeRabbit):
        def publish(
            self, routing_key: str, payload: dict[str, Any],
            exchange: str | None = None,
        ) -> None:
            raise ConnectionError("broker down")

    monkeypatch.setattr(worker_module, "MySQLStore", lambda: store)
    monkeypatch.setattr(worker_module, "RedisStore", lambda: redis)
    monkeypatch.setattr(worker_module, "RabbitMQClient", BrokenRabbit)

    result = worker_module.reclaim_stale_running_jobs(lease_ttl_seconds=30)

    assert result == [dict(_RECLAIMED_ROW)]  # the audited MySQL reclaim stands


class FakeRecoverStore:
    def __init__(
        self,
        waiting_rows: list[dict[str, Any]],
        outcomes: list[tuple[bool, str | None]],
    ) -> None:
        self.waiting_rows = waiting_rows
        self.outcomes = outcomes
        self.recovered: list[str] = []
        self.scanned = False

    def get_jobs_by_status(self, status: str) -> list[dict[str, Any]]:
        assert status == "WAITING_FOR_PROVIDER"
        self.scanned = True
        return list(self.waiting_rows)

    def recover_provider_wait(
        self, job_id: str, **kwargs: Any,
    ) -> tuple[bool, str | None]:
        self.recovered.append(job_id)
        return self.outcomes.pop(0)

    def close(self) -> None:
        return None


_WAITING_ROW = {
    "id": "j1",
    "repo_path": "/r",
    "base_ref": "base",
    "head_ref": "head",
    "spec_path": "/s",
    "depth": "FAST",
    "retry_count": 1,
    "status": "WAITING_FOR_PROVIDER",
}


def test_standalone_recover_requeues_under_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeRecoverStore([dict(_WAITING_ROW)], [(True, "QUEUED")])
    rabbit = FakeRabbit()
    monkeypatch.setattr(worker_module, "MySQLStore", lambda: store)
    monkeypatch.setattr(worker_module, "RabbitMQClient", lambda: rabbit)

    results = worker_module.recover_waiting_for_provider_jobs()

    assert results == [("j1", "QUEUED")]
    assert store.recovered == ["j1"]
    assert rabbit.published[0][0] == "q.p1.verify.job"
    payload = rabbit.published[0][1]
    assert payload["job_id"] == "j1"
    assert payload["event_id"] == "retry-j1-2"  # attempt = retry_count + 1


def test_standalone_recover_fails_over_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeRecoverStore([dict(_WAITING_ROW)], [(True, "FAILED")])
    rabbit = FakeRabbit()
    monkeypatch.setattr(worker_module, "MySQLStore", lambda: store)
    monkeypatch.setattr(worker_module, "RabbitMQClient", lambda: rabbit)

    results = worker_module.recover_waiting_for_provider_jobs()

    assert results == [("j1", "FAILED")]
    assert rabbit.published == []  # FAILED jobs are not re-delivered


def test_standalone_recover_stays_parked_when_provider_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeRecoverStore([], [(True, "QUEUED")])
    monkeypatch.setattr(worker_module, "MySQLStore", lambda: store)
    monkeypatch.setattr(worker_module, "RabbitMQClient", lambda: FakeRabbit())

    results = worker_module.recover_waiting_for_provider_jobs(
        provider_ready=lambda: False,
    )

    assert results == []
    assert store.scanned is False  # nothing even read while parked


def test_standalone_recover_skips_cas_lost_races(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeRecoverStore([dict(_WAITING_ROW)], [(False, None)])
    rabbit = FakeRabbit()
    monkeypatch.setattr(worker_module, "MySQLStore", lambda: store)
    monkeypatch.setattr(worker_module, "RabbitMQClient", lambda: rabbit)

    results = worker_module.recover_waiting_for_provider_jobs()

    assert results == []
    assert rabbit.published == []

