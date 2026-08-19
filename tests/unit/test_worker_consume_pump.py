"""Regression tests for the RabbitMQ consumption wiring in agent/worker.py (W43.1).

Two live-observed regressions, now fixed in agent/worker.py:

1. main() registered the consumer but never pumped the blocking connection —
   the process exited and queued JobCreated messages never got delivered;
2. Worker.start() passed RedisStore.set_idempotent as the idempotency check,
   whose boolean is inverted relative to the consumer contract
   (True = duplicate), so a correct pump alone would still drop every
   message as a "duplicate".

No Docker and no RabbitMQ: the wiring is asserted through fakes.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

import agent.worker as worker_module
from agent.worker import Worker


class _FakeRabbitClient:
    """Records consume_with_policy wiring and start_consuming calls."""

    def __init__(self) -> None:
        self.topology_calls = 0
        self.consume_kwargs: dict[str, Any] = {}
        self.pump_calls = 0

    def ensure_topology(self) -> None:
        self.topology_calls += 1

    def consume_with_policy(self, **kwargs: Any) -> None:
        self.consume_kwargs = kwargs

    def start_consuming(self) -> None:
        self.pump_calls += 1

    def close(self) -> None:
        return None


class _FakeRedisClient:
    """SETNX semantics: True only on the FIRST set for a key (i.e. new)."""

    def __init__(self) -> None:
        self.seen: set[str] = set()

    def set(self, key: str, value: str, nx: bool, ex: int) -> bool:
        if key in self.seen:
            return False
        self.seen.add(key)
        return True


class _FakeRedisStore:
    def __init__(self) -> None:
        self.client = _FakeRedisClient()


class _FakeMysqlStore:
    def close(self) -> None:
        return None


class _FakeWorker:
    """Minimal Worker stand-in for the main() pump test."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.redis = _FakeRedisStore()
        self.mysql = _FakeMysqlStore()
        self.rabbitmq = _FakeRabbitClient()

    def start(self) -> None:
        self.calls.append("start")
        self.rabbitmq.ensure_topology()

    def stop(self) -> None:
        self.calls.append("stop")


def test_worker_start_wires_correct_idempotency_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The adapter must report False for a NEW event and True for a duplicate."""
    fake_rabbit = _FakeRabbitClient()
    fake_redis = _FakeRedisStore()
    monkeypatch.setattr(worker_module, "RabbitMQClient", lambda: fake_rabbit)
    monkeypatch.setattr(worker_module, "RedisStore", lambda: fake_redis)
    monkeypatch.setattr(worker_module, "MySQLStore", lambda: _FakeMysqlStore())

    worker = Worker()
    worker.start()

    assert fake_rabbit.consume_kwargs["queue"] == "q.p1.verify.job"
    check = fake_rabbit.consume_kwargs["idempotency_fn"]
    assert callable(check)
    assert check("event-1") is False  # new event: process it
    assert check("event-1") is True  # repeat: duplicate, drop it
    assert check("event-2") is False  # a different event is new


def test_main_pumps_the_consumption_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() must call start_consuming() right after start() (the live bug)."""
    fake_worker = _FakeWorker()
    monkeypatch.setattr(worker_module, "Worker", lambda: fake_worker)
    monkeypatch.setattr("observability.logging.configure_logging", lambda: None)
    monkeypatch.setattr(
        "observability.tracing.init_tracing", lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "observability.metrics_http.serve_metrics_in_thread",
        lambda **kwargs: None,
    )
    # main() exits non-zero after the pump loop ends; capture that instead
    # of terminating the test process.
    monkeypatch.setattr(sys, "exit", lambda code: None)

    worker_module.main()

    assert fake_worker.calls == ["start", "stop"]
    assert fake_worker.rabbitmq.pump_calls == 1
