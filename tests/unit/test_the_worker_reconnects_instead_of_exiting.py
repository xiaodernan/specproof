"""The worker rides out a broker restart instead of exiting on it.

A lost AMQP connection is a **normal** event — brokers restart during
upgrades, and the network hiccups. The worker used to exit on it (exit 1,
"the launcher/supervisor can restart it"), which in a container means a
restart, and outside one means nothing at all: every queued job then waits
for the reclaim sweep instead of being picked up.

The reconnect loop has to be honest about two things, and this file pins
both:

* it **reconnects** — the consumption is attempted again after the broken
  connection is dropped;
* it does **not spin** — the wait doubles and is capped, so a broker that
  stays down costs a reconnect every 30 seconds rather than a hot loop.

The number of reconnects is counted (``worker_rabbitmq_reconnects_total``):
a worker that reconnects forever is a worker whose broker is unhealthy, and
the operator has to be able to see that.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.worker import consume_forever  # noqa: E402


class _FakeRabbit:
    """Fails the first N consumptions, then stops the loop."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.attempts = 0
        self.resets = 0

    def start_consuming(self) -> None:
        self.attempts += 1
        if self.attempts <= self.failures:
            raise ConnectionError("broker went away")
        raise KeyboardInterrupt("stop the test")

    def reset_connection(self) -> None:
        self.resets += 1


class _FakeWorker:
    def __init__(self, rabbit: _FakeRabbit) -> None:
        self.rabbitmq = rabbit


def test_the_worker_reconnects_after_a_lost_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda seconds: slept.append(seconds))

    rabbit = _FakeRabbit(failures=3)
    with pytest.raises(KeyboardInterrupt):
        consume_forever(_FakeWorker(rabbit), max_backoff=30.0)

    assert rabbit.attempts == 4, "the worker must try again after each loss"
    assert rabbit.resets == 3, "each lost connection must be dropped before retrying"
    assert slept[:3] == [1.0, 2.0, 4.0], f"the backoff must double: {slept}"


def test_the_backoff_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda seconds: slept.append(seconds))

    rabbit = _FakeRabbit(failures=8)
    with pytest.raises(KeyboardInterrupt):
        consume_forever(_FakeWorker(rabbit), max_backoff=5.0)

    assert max(slept) <= 5.0, f"the backoff must be capped: {slept}"
    assert slept[-1] == 5.0, f"the cap must be reached, not approached: {slept}"
    assert len(slept) == 8, f"every reconnect waits once: {slept}"


def test_a_clean_end_of_the_loop_is_also_a_reconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    """``start_consuming`` can RETURN instead of raising — same handling."""

    class _Returns(_FakeRabbit):
        def start_consuming(self) -> None:
            self.attempts += 1
            if self.attempts >= 2:
                raise KeyboardInterrupt("stop the test")

    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda seconds: slept.append(seconds))

    rabbit = _Returns(failures=0)
    with pytest.raises(KeyboardInterrupt):
        consume_forever(_FakeWorker(rabbit))

    assert rabbit.attempts == 2
    assert rabbit.resets == 1
    assert slept == [1.0]


def test_the_reconnect_counter_is_published(monkeypatch: pytest.MonkeyPatch) -> None:
    """The flapping has to be visible, not just survived."""
    import agent.worker as worker_module

    counted: list[str] = []
    monkeypatch.setattr(time, "sleep", lambda seconds: None)

    import observability.metrics as metrics_module

    monkeypatch.setattr(
        metrics_module, "incr", lambda name, *args, **kwargs: counted.append(name)
    )

    rabbit = _FakeRabbit(failures=1)
    with pytest.raises(KeyboardInterrupt):
        consume_forever(_FakeWorker(rabbit))

    assert counted == ["worker_rabbitmq_reconnects_total"], counted
