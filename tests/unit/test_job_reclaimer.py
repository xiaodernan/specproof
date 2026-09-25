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
    RECLAIM_STALE_RUNNING_EXHAUSTED_ACTION,
    STALE_RUNNING_EXHAUSTED_REASON,
    MySQLStore,
    ReclaimOutcome,
)

NOW = datetime(2026, 8, 20, 12, 0, 0)


class FakeJobTable:
    """verification_jobs rows + the exact reclaim CAS predicate semantics."""

    def __init__(self, rows: list[dict[str, Any]], now: datetime) -> None:
        self.now = now
        # The SQL strings the production code actually sent. The in-memory
        # semantics below cannot catch a wrong clause in the statement text,
        # and MySQL runs that text verbatim, so the text is asserted too.
        self.statements: list[str] = []
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

    def _stale_match(self, job_id: str, ttl_seconds: int) -> dict[str, Any] | None:
        row = self.rows.get(job_id)
        if row is None:
            return None
        if row["status"] != "RUNNING" or row["updated_at"] >= self.cutoff(
            ttl_seconds
        ):
            return None
        return row

    def reclaim_cas(self, job_id: str, ttl_seconds: int, reason: str) -> int:
        """Apply the reclaim UPDATE; returns the matched row count (0 or 1)."""
        row = self._stale_match(job_id, ttl_seconds)
        if row is None:
            return 0
        row["status"] = "QUEUED"
        row["worker_id"] = None
        row["retry_count"] = int(row.get("retry_count") or 0) + 1
        row["last_error"] = reason
        row["updated_at"] = self.now
        return 1

    def fail_cas(self, job_id: str, ttl_seconds: int, reason: str) -> int:
        """Apply the budget-exhausted UPDATE (no retry_count bump)."""
        row = self._stale_match(job_id, ttl_seconds)
        if row is None:
            return 0
        row["status"] = "FAILED"
        row["worker_id"] = None
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
        self.table.statements.append(sql)
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
        elif sql.startswith("UPDATE verification_jobs SET status = 'FAILED'"):
            reason = str(self.params[0])
            job_id = str(self.params[1])
            ttl = int(self.params[2])
            self.rowcount = self.table.fail_cas(job_id, ttl, reason)

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

    reclaimed = store.reclaim_stale_running(30, lease_alive=_never_alive).reclaimed

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

    reclaimed = store.reclaim_stale_running(30, lease_alive=alive).reclaimed

    assert reclaimed == []
    assert table.rows["j-alive"]["status"] == "RUNNING"
    assert audits == []


def test_fresh_updated_at_within_ttl_is_not_reclaimed() -> None:
    table = FakeJobTable(
        [_job("j-fresh", "RUNNING", NOW - timedelta(seconds=10))], NOW
    )
    store, audits = _store_with_fake_db(table)

    reclaimed = store.reclaim_stale_running(30, lease_alive=_never_alive).reclaimed

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

    reclaimed = store.reclaim_stale_running(30, lease_alive=_never_alive).reclaimed

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

    first = store.reclaim_stale_running(30, lease_alive=_never_alive).reclaimed
    second = store.reclaim_stale_running(30, lease_alive=_never_alive).reclaimed

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

    reclaimed = store.reclaim_stale_running(30, lease_alive=_never_alive).reclaimed

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

    reclaimed = store.reclaim_stale_running(30, lease_alive=_never_alive).reclaimed

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
    def __init__(
        self,
        rows: list[dict[str, Any]],
        *,
        lease_probe_error: str | None = None,
        exhausted: list[dict[str, Any]] | None = None,
    ) -> None:
        self.rows = rows
        self.exhausted = exhausted or []
        self.calls: list[tuple[int, Callable[[str], bool]]] = []
        self.lease_probe_error = lease_probe_error

    def reclaim_stale_running(
        self, lease_ttl_seconds: int, *, lease_alive: Callable[[str], bool],
    ) -> ReclaimOutcome:
        self.calls.append((lease_ttl_seconds, lease_alive))
        return ReclaimOutcome(
            reclaimed=list(self.rows),
            exhausted=list(self.exhausted),
            candidates=len(self.rows) + len(self.exhausted),
            probed=len(self.rows) + len(self.exhausted),
            lease_probe_error=self.lease_probe_error,
        )

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

    assert result.reclaimed == [dict(_RECLAIMED_ROW)]
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

    assert result.reclaimed == [dict(_RECLAIMED_ROW)]  # the audited MySQL reclaim stands


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


def test_unknown_lease_stops_pass_and_keeps_reclaimed_rows() -> None:
    """Redis cannot answer != the lease expired: stop, and report the partial pass.

    Before this contract, a Redis outage looked exactly like "every heartbeat is
    dead" on the first candidate, or aborted the caller with a raw traceback that
    hid the jobs already requeued. Neither may happen: the pass stops at the
    unknown probe and the rows already reclaimed come back with it.
    """
    table = FakeJobTable(
        [
            _job("j-first", "RUNNING", NOW - timedelta(seconds=200)),
            _job("j-second", "RUNNING", NOW - timedelta(seconds=190)),
            _job("j-third", "RUNNING", NOW - timedelta(seconds=180)),
        ],
        NOW,
    )
    store, audits = _store_with_fake_db(table)
    probed: list[str] = []

    def probe(job_id: str) -> bool:
        probed.append(job_id)
        if job_id == "j-second":
            raise ConnectionError("redis unreachable")
        return False

    outcome = store.reclaim_stale_running(30, lease_alive=probe)

    assert [row["id"] for row in outcome.reclaimed] == ["j-first"]
    assert outcome.candidates == 3
    assert outcome.probed == 1
    assert outcome.lease_probe_error is not None
    assert "ConnectionError" in outcome.lease_probe_error
    # the unknown candidate and everything after it are untouched
    assert table.rows["j-second"]["status"] == "RUNNING"
    assert table.rows["j-third"]["status"] == "RUNNING"
    assert probed == ["j-first", "j-second"]
    assert [a["job_id"] for a in audits] == ["j-first"]


def test_answering_probe_leaves_no_error_marker() -> None:
    table = FakeJobTable(
        [_job("j-stale", "RUNNING", NOW - timedelta(seconds=120))], NOW
    )
    store, _audits = _store_with_fake_db(table)

    outcome = store.reclaim_stale_running(30, lease_alive=_never_alive)

    assert outcome.lease_probe_error is None
    assert outcome.probed == outcome.candidates == 1


def test_worker_reclaimer_passes_probe_error_through_without_redelivering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The requeued job is the reclaimed one only — an unknown lease is not stolen."""
    store = FakeReclaimStore(
        [dict(_RECLAIMED_ROW)], lease_probe_error="ConnectionError: redis unreachable"
    )
    redis = FakeLeaseRedis(owner=None)
    rabbit = FakeRabbit()
    monkeypatch.setattr(worker_module, "MySQLStore", lambda: store)
    monkeypatch.setattr(worker_module, "RedisStore", lambda: redis)
    monkeypatch.setattr(worker_module, "RabbitMQClient", lambda: rabbit)

    from observability import metrics

    before = metrics.snapshot()["counters"].get(
        "worker_reclaim_lease_probe_unknown_total", 0.0
    )
    outcome = worker_module.reclaim_stale_running_jobs(lease_ttl_seconds=30)

    assert outcome.lease_probe_error == "ConnectionError: redis unreachable"
    assert [row["id"] for row in outcome.reclaimed] == ["j1"]
    assert len(rabbit.published) == 1  # only the actually reclaimed job
    after = metrics.snapshot()["counters"].get(
        "worker_reclaim_lease_probe_unknown_total", 0.0
    )
    assert after - before == 1.0


# ── #71: the reclaim itself is capped by the job's own retry budget ──


def test_budget_exhausted_candidate_goes_to_failed_not_queued() -> None:
    table = FakeJobTable(
        [
            _job(
                "j-broke",
                "RUNNING",
                NOW - timedelta(seconds=120),
                retry_count=3,
                max_retries=3,
                worker_id="w-9",
            )
        ],
        NOW,
    )
    store, audits = _store_with_fake_db(table)

    outcome = store.reclaim_stale_running(30, lease_alive=_never_alive)

    assert outcome.reclaimed == []
    assert [row["id"] for row in outcome.exhausted] == ["j-broke"]
    row = table.rows["j-broke"]
    assert row["status"] == "FAILED"
    assert row["worker_id"] is None
    assert row["retry_count"] == 3  # the FAILED branch never bumps the budget
    reason = json.loads(row["last_error"])
    assert reason["reason"] == STALE_RUNNING_EXHAUSTED_REASON
    assert reason["retry_count"] == 3
    assert reason["max_retries"] == 3
    assert reason["previous_worker"] == "w-9"
    assert len(audits) == 1
    assert audits[0]["action"] == RECLAIM_STALE_RUNNING_EXHAUSTED_ACTION
    assert audits[0]["from_status"] == "RUNNING"
    assert audits[0]["to_status"] == "FAILED"


def test_budget_is_read_per_row_not_from_a_global_constant() -> None:
    """max_retries=1 is spent at once; max_retries=5 still has room."""
    table = FakeJobTable(
        [
            _job(
                "j-tight",
                "RUNNING",
                NOW - timedelta(seconds=200),
                retry_count=1,
                max_retries=1,
            ),
            _job(
                "j-loose",
                "RUNNING",
                NOW - timedelta(seconds=190),
                retry_count=1,
                max_retries=5,
            ),
        ],
        NOW,
    )
    store, audits = _store_with_fake_db(table)

    outcome = store.reclaim_stale_running(30, lease_alive=_never_alive)

    assert [row["id"] for row in outcome.reclaimed] == ["j-loose"]
    assert [row["id"] for row in outcome.exhausted] == ["j-tight"]
    assert table.rows["j-tight"]["status"] == "FAILED"
    assert table.rows["j-tight"]["retry_count"] == 1
    assert table.rows["j-loose"]["status"] == "QUEUED"
    assert table.rows["j-loose"]["retry_count"] == 2
    assert [a["to_status"] for a in audits] == ["FAILED", "QUEUED"]


def test_repeated_reclaim_of_a_crashing_job_converges_and_stops() -> None:
    """The harm the cap prevents: a periodic tick must not requeue forever."""
    table = FakeJobTable(
        [
            _job(
                "j-crash",
                "RUNNING",
                NOW - timedelta(seconds=120),
                retry_count=2,
                max_retries=3,
            )
        ],
        NOW,
    )
    store, audits = _store_with_fake_db(table)

    statuses: list[str] = []
    for _ in range(6):
        row = table.rows["j-crash"]
        if row["status"] == "QUEUED":
            # A worker claims the requeued job and dies on it again, which is
            # what makes the row a stale-RUNNING candidate for the next tick.
            row["status"] = "RUNNING"
            row["worker_id"] = "w-loop"
        row["updated_at"] = NOW - timedelta(seconds=120)
        store.reclaim_stale_running(30, lease_alive=_never_alive)
        statuses.append(str(row["status"]))

    assert statuses == ["QUEUED", "FAILED", "FAILED", "FAILED", "FAILED", "FAILED"]
    assert len(audits) == 2  # one QUEUED, one FAILED; nothing after that


def test_failed_cas_lost_race_is_not_reported_as_exhausted() -> None:
    table = FakeJobTable(
        [
            _job(
                "j-race",
                "RUNNING",
                NOW - timedelta(seconds=120),
                retry_count=5,
                max_retries=5,
            )
        ],
        NOW,
    )
    store, audits = _store_with_fake_db(table)

    original = table.fail_cas

    def win_race(job_id: str, ttl_seconds: int, reason: str) -> int:
        if table.rows[job_id]["status"] == "RUNNING":
            table.rows[job_id]["status"] = "CANCELLED"
        return original(job_id, ttl_seconds, reason)

    table.fail_cas = win_race  # type: ignore[method-assign]

    outcome = store.reclaim_stale_running(30, lease_alive=_never_alive)

    assert outcome.exhausted == []
    assert outcome.reclaimed == []
    assert audits == []
    assert table.rows["j-race"]["status"] == "CANCELLED"


def test_unknown_lease_never_reaches_the_budget_check() -> None:
    """A probe that cannot answer stops the pass before any status is written."""
    table = FakeJobTable(
        [
            _job(
                "j-unknown",
                "RUNNING",
                NOW - timedelta(seconds=120),
                retry_count=9,
                max_retries=1,
            )
        ],
        NOW,
    )
    store, audits = _store_with_fake_db(table)

    def probe(job_id: str) -> bool:
        raise ConnectionError("redis unreachable")

    outcome = store.reclaim_stale_running(30, lease_alive=probe)

    assert outcome.exhausted == []
    assert outcome.lease_probe_error is not None
    assert table.rows["j-unknown"]["status"] == "RUNNING"
    assert audits == []


def test_worker_does_not_redeliver_budget_exhausted_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-delivering a FAILED job would restart exactly the crash loop the cap ends."""
    from observability import metrics

    dead_row = dict(_RECLAIMED_ROW)
    dead_row.update({"id": "j-dead", "retry_count": 3, "max_retries": 3})
    store = FakeReclaimStore([dict(_RECLAIMED_ROW)], exhausted=[dead_row])
    redis = FakeLeaseRedis(owner=None)
    rabbit = FakeRabbit()
    monkeypatch.setattr(worker_module, "MySQLStore", lambda: store)
    monkeypatch.setattr(worker_module, "RedisStore", lambda: redis)
    monkeypatch.setattr(worker_module, "RabbitMQClient", lambda: rabbit)

    before = metrics.snapshot()["counters"].get(
        "worker_reclaim_retry_budget_exhausted_total", 0.0
    )
    outcome = worker_module.reclaim_stale_running_jobs(lease_ttl_seconds=30)
    after = metrics.snapshot()["counters"].get(
        "worker_reclaim_retry_budget_exhausted_total", 0.0
    )

    assert [row["id"] for row in outcome.reclaimed] == ["j1"]
    assert [p[1]["job_id"] for p in rabbit.published] == ["j1"]
    assert after - before == 1.0



def test_both_cas_statement_shapes_are_what_the_budget_branch_needs() -> None:
    """A wrong clause in the SQL text is invisible to the in-memory fake.

    RUNNING→QUEUED must carry the increment (that is how the budget is spent);
    RUNNING→FAILED must not touch retry_count or the last_error reason of a
    row nobody will run again.
    """
    table = FakeJobTable(
        [
            _job(
                "j-ok",
                "RUNNING",
                NOW - timedelta(seconds=200),
                retry_count=0,
                max_retries=3,
            ),
            _job(
                "j-dead",
                "RUNNING",
                NOW - timedelta(seconds=190),
                retry_count=3,
                max_retries=3,
            ),
        ],
        NOW,
    )
    store, _ = _store_with_fake_db(table)

    store.reclaim_stale_running(30, lease_alive=_never_alive)

    queued = [s for s in table.statements if "SET status = 'QUEUED'" in s]
    failed = [s for s in table.statements if "SET status = 'FAILED'" in s]
    assert len(queued) == 1
    assert len(failed) == 1
    assert "retry_count = retry_count + 1" in queued[0]
    assert "retry_count" not in failed[0]
    # Both branches keep the same double guard, or a pass could move a row that
    # a live worker just refreshed.
    for stmt in (queued[0], failed[0]):
        assert "status = 'RUNNING'" in stmt
        assert "updated_at < (NOW(3) - INTERVAL %s SECOND)" in stmt
