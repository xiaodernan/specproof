"""§14 任务 8 — classify_job_error matrix and terminal reason/events.

The unified envelope {class: system|repo|provider|policy|unknown, code,
retryable, note} is unit-tested across the required matrix
(TimeoutError->system / BuildFailure->repo / ProviderAuthError->provider)
plus storage/subprocess/policy/unknown fallbacks, and the worker writes the
same envelope into the terminal reason (last_error) and progress events.
"""
from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

import agent.worker as worker_module
from agent.job_control import (
    BuildFailure,
    ProviderAuthError,
    classify_job_error,
)
from agent.worker import Worker
from storage.mysql import InvalidStateTransition


def _assert_class(
    exc: BaseException, cls: str, code: str, retryable: bool,
) -> None:
    result = classify_job_error(exc)
    assert result.cls == cls
    assert result.code == code
    assert result.retryable is retryable
    assert result.as_dict() == {
        "class": cls,
        "code": code,
        "retryable": retryable,
        "note": result.note,
    }
    assert cls in ("system", "repo", "provider", "policy", "unknown")


def test_timeout_error_is_system() -> None:
    _assert_class(TimeoutError("timed out"), "system", "timeout", True)


def test_build_failure_is_repo() -> None:
    _assert_class(BuildFailure("mvnw exit 1"), "repo", "build_failure", False)


def test_provider_auth_error_is_provider() -> None:
    _assert_class(ProviderAuthError("401"), "provider", "provider_auth", False)


def test_connection_error_is_system_retryable() -> None:
    _assert_class(ConnectionError("refused"), "system", "connection", True)


def test_subprocess_timeout_is_system() -> None:
    _assert_class(
        subprocess.TimeoutExpired(cmd="mvnw", timeout=30),
        "system", "subprocess_timeout", True,
    )


def test_subprocess_failure_is_repo() -> None:
    _assert_class(
        subprocess.CalledProcessError(1, ["git", "checkout"]),
        "repo", "command_failed", False,
    )


def test_mysql_operational_error_is_system() -> None:
    from pymysql.err import OperationalError

    _assert_class(
        OperationalError(2003, "connection refused"),
        "system", "mysql_unavailable", True,
    )


def test_redis_connection_error_is_system() -> None:
    from redis.exceptions import ConnectionError as RedisConnectionError

    _assert_class(
        RedisConnectionError("down"), "system", "redis_unavailable", True,
    )


def test_invalid_state_transition_is_policy() -> None:
    _assert_class(
        InvalidStateTransition("CANCELLED -> VERIFIED"),
        "policy", "invalid_state_transition", False,
    )


def test_unknown_fallback() -> None:
    _assert_class(ValueError("whatever"), "unknown", "unclassified", False)


# ── worker writes the classification into terminal reason/events ───────────


class _FakeMysql:
    def __init__(self) -> None:
        self.transitions: list[tuple[str, dict[str, Any]]] = []

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return {"id": job_id, "status": "RUNNING", "tenant_id": None}

    def transition_job_status(
        self, job_id: str, to_status: str, **kwargs: Any,
    ) -> bool:
        self.transitions.append((to_status, kwargs))
        return True

    def save_job_summary(self, job_id: str, summary: dict[str, Any]) -> None:
        return None


class _FakeRedis:
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


class _FailingGraph:
    """Stream fake that fails after the first stage (system timeout)."""

    def stream(self, state: Any, config: Any, stream_mode: Any = None) -> Any:
        yield ("updates", {"intake": {"_done": "intake"}})
        raise TimeoutError("mvnw timed out")


def test_worker_writes_classification_into_terminal_reason_and_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mysql = _FakeMysql()
    redis = _FakeRedis()
    monkeypatch.setattr(worker_module, "MySQLStore", lambda: mysql)
    monkeypatch.setattr(worker_module, "RedisStore", lambda: redis)
    monkeypatch.setattr(worker_module, "MongoDBSaver", lambda: None)
    monkeypatch.setattr(
        worker_module, "build_phase0_graph",
        lambda checkpointer=None: _FailingGraph(),
    )

    class _FakeRabbit:
        def close(self) -> None:
            return None

    monkeypatch.setattr(worker_module, "RabbitMQClient", _FakeRabbit)
    worker = Worker(worker_id="w-classify", lease_ttl=30)
    worker._running = True

    worker._handle_job_impl("job-t", {"repo_path": "/r", "spec_path": "/s"})

    failed = [kw for t, kw in mysql.transitions if t == "FAILED"]
    assert len(failed) == 1
    reason = json.loads(failed[0]["error_msg"])
    assert reason["class"] == "system"
    assert reason["code"] == "timeout"
    assert reason["retryable"] is True
    assert "mvnw timed out" in reason["error"]
    assert any(
        json.loads(m)["class"] == "system"
        for _, _, m in redis.events
        if m.startswith("{")
    )
    assert redis.released == ["job-t"]
