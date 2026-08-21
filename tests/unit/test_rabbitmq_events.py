"""Unit tests for RabbitMQ observable events (§14.2)."""

from __future__ import annotations

import json
from typing import Any

import pytest

import storage.rabbitmq as module
from storage.rabbitmq import (
    PermanentFailure,
    QueuePolicy,
    RabbitMQClient,
    RabbitMQEventLog,
)


class _FakeChannel:
    def __init__(self) -> None:
        self.acks: list[int] = []
        self.rejects: list[int] = []
        self.publishes: list[dict[str, Any]] = []
        self.is_closed = False
        self.is_open = True

    def basic_publish(self, exchange, routing_key, body, properties) -> None:
        self.publishes.append({
            "exchange": exchange,
            "routing_key": routing_key,
            "body": body,
        })

    def basic_ack(self, delivery_tag) -> None:
        self.acks.append(delivery_tag)

    def basic_reject(self, delivery_tag, requeue) -> None:
        self.rejects.append(delivery_tag)

    def basic_qos(self, prefetch_count) -> None:
        pass

    def basic_consume(self, queue, on_message_callback) -> None:
        self.on_message = on_message_callback

    def close(self) -> None:
        self.is_open = False


class _FakeProps:
    def __init__(self, headers: dict[str, Any] | None = None) -> None:
        self.headers = headers


class _FakeMethod:
    delivery_tag = 7


@pytest.fixture()
def fake_client(monkeypatch) -> tuple[RabbitMQClient, _FakeChannel, list[dict[str, Any]]]:
    channel = _FakeChannel()
    events: list[dict[str, Any]] = []
    client = RabbitMQClient(events=events.append)
    client._channel = channel  # bypass real connection entirely
    client._connection = None
    monkeypatch.setattr(module.RabbitMQClient, "channel", property(lambda s: channel))
    return client, channel, events


def test_publish_emits_event(fake_client) -> None:
    client, channel, events = fake_client
    assert client.publish_with_confirm("q.routing", {"k": "v"}) is True
    assert events[-1]["event"] == "published"
    assert events[-1]["routing_key"] == "q.routing"
    assert events[-1]["body_bytes"] > 0
    assert channel.publishes


def test_publish_failure_emits_timeout_event(fake_client, monkeypatch) -> None:
    client, channel, events = fake_client
    from pika.exceptions import NackError

    def failing_publish(**kwargs):
        raise NackError([None])  # type: ignore[arg-type]

    channel.basic_publish = failing_publish  # type: ignore[method-assign]
    with pytest.raises(module.PublisherConfirmTimeout):
        client.publish_with_confirm("q.routing", {"k": "v"})
    assert events[-1]["event"] == "publish_confirm_timeout"


def test_consumed_and_duplicate_events(fake_client) -> None:
    client, channel, events = fake_client

    def callback(payload):
        pass

    client.consume_with_policy(
        "q.work", callback,
        idempotency_fn=lambda event_id: False,
    )
    channel.on_message(
        channel, _FakeMethod(), _FakeProps(),
        json.dumps({"event_id": "evt-1"}),
    )
    assert events[-1]["event"] == "consumed"
    assert events[-1]["event_id"] == "evt-1"

    channel.on_message(
        channel, _FakeMethod(), _FakeProps(),
        json.dumps({"event_id": "evt-2"}),
    )
    # Second message duplicates evt-1? The fake idempotency check answers
    # False for everything; re-consume with a True check for one event.
    client.consume_with_policy(
        "q.work", callback,
        idempotency_fn=lambda event_id: event_id == "evt-3",
    )
    channel.on_message(
        channel, _FakeMethod(), _FakeProps(),
        json.dumps({"event_id": "evt-3"}),
    )
    assert events[-1]["event"] == "duplicate_acked"
    assert events[-1]["event_id"] == "evt-3"


def test_retry_and_dlq_events(fake_client) -> None:
    client, channel, events = fake_client

    def boom(payload):
        raise RuntimeError("boom")

    client.consume_with_policy(
        "q.work", boom, policy=QueuePolicy(max_retries=1),
    )
    channel.on_message(
        channel, _FakeMethod(), _FakeProps(), json.dumps({"event_id": "e1"}),
    )
    assert events[-1]["event"] == "retry_scheduled"
    assert events[-1]["retry_count"] == 1

    # Death count at max -> DLQ
    deaths = [{"count": 1, "reason": "rejected", "queue": "q.work"}]
    channel.on_message(
        channel, _FakeMethod(), _FakeProps({"x-death": deaths}),
        json.dumps({"event_id": "e2"}),
    )
    assert events[-1]["event"] == "dead_lettered"
    assert events[-1]["reason"] == "max_retries_exceeded"


def test_permanent_failure_emits_dlq(fake_client) -> None:
    client, channel, events = fake_client

    def permanent(payload):
        raise PermanentFailure("bad")

    client.consume_with_policy("q.work", permanent)
    channel.on_message(
        channel, _FakeMethod(), _FakeProps(), json.dumps({"event_id": "e1"}),
    )
    assert events[-1]["event"] == "dead_lettered"
    assert events[-1]["reason"] == "permanent_failure"


def test_no_sink_keeps_legacy_silence() -> None:
    client = RabbitMQClient()
    assert client._events is not None  # no-op sink installed
    # Calling the no-op must not raise and must not log.
    client._emit({"event": "published"})


def test_event_log_sink_logs_json(caplog) -> None:
    import logging

    sink = RabbitMQEventLog(logging.getLogger("test.events"))
    with caplog.at_level(logging.INFO, logger="test.events"):
        sink({"event": "published", "routing_key": "q.x"})
    assert "rabbitmq_event" in caplog.text
    assert "published" in caplog.text
    assert "q.x" in caplog.text
