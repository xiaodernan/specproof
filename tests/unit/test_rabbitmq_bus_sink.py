"""Unit tests for the W190 event bus sink and composite sink (#1603).

These run with no broker: the client's channel is replaced by a fake, and the
sink can also take an injected publisher. The key honesty check is that wiring
the bus sink into a client's events sink does NOT recurse — exactly one
forwarded event per emitted event.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

import storage.rabbitmq as module
from storage.rabbitmq import (
    EXCHANGE_EVENTS,
    MQ_EVENTS,
    QUEUE_GATEWAY_MQ_EVENTS,
    CompositeEventSink,
    RabbitMQBusSink,
    RabbitMQClient,
)


class _FakeChannel:
    def __init__(self) -> None:
        self.publishes: list[dict[str, Any]] = []
        self.declares: list[dict[str, Any]] = []
        self.binds: list[dict[str, Any]] = []
        self.is_closed = False
        self.is_open = True

    def basic_publish(self, exchange, routing_key, body, properties) -> None:
        self.publishes.append({
            "exchange": exchange,
            "routing_key": routing_key,
            "body": body,
        })

    def exchange_declare(self, exchange, exchange_type="direct", durable=False, **kw) -> None:
        self.declares.append({
            "exchange": exchange, "type": exchange_type, "durable": durable})

    def queue_declare(self, queue, durable=False, arguments=None) -> None:
        self.declares.append({"queue": queue, "durable": durable})

    def queue_bind(self, exchange, queue, routing_key, **kw) -> None:
        self.binds.append({
            "exchange": exchange, "queue": queue, "routing_key": routing_key})

    def close(self) -> None:
        self.is_open = False


@pytest.fixture()
def fake_client(monkeypatch) -> tuple[RabbitMQClient, _FakeChannel]:
    channel = _FakeChannel()
    client = RabbitMQClient()
    client._channel = channel
    client._connection = None
    monkeypatch.setattr(module.RabbitMQClient, "channel", property(lambda s: channel))
    return client, channel


def test_bus_sink_forwards_event_with_name_as_routing_key(fake_client) -> None:
    client, channel = fake_client
    sink = RabbitMQBusSink(client)
    sink({"event": "consumed", "queue": "q.work", "event_id": "e1"})

    assert len(channel.publishes) == 1
    pub = channel.publishes[0]
    assert pub["exchange"] == EXCHANGE_EVENTS
    assert pub["routing_key"] == "consumed"
    assert json.loads(pub["body"])["event"] == "consumed"


def test_bus_sink_missing_event_name_routes_to_unknown(fake_client) -> None:
    client, channel = fake_client
    sink = RabbitMQBusSink(client)
    sink({"queue": "q.work"})

    assert channel.publishes[0]["routing_key"] == "unknown"


def test_bus_sink_non_string_event_name_routes_to_unknown(fake_client) -> None:
    client, channel = fake_client
    sink = RabbitMQBusSink(client)
    sink({"event": 123})

    assert channel.publishes[0]["routing_key"] == "unknown"


def test_bus_sink_uses_injected_publisher() -> None:
    recorded: list[tuple[str, dict[str, Any]]] = []
    sink = RabbitMQBusSink(publisher=lambda rk, payload: recorded.append((rk, payload)))
    sink({"event": "dead_lettered"})

    assert recorded == [("dead_lettered", {"event": "dead_lettered"})]


def test_composite_sink_fans_out() -> None:
    a: list[dict[str, Any]] = []
    b: list[dict[str, Any]] = []
    sink = CompositeEventSink([lambda e: a.append(e), lambda e: b.append(e)])
    sink({"event": "published"})

    assert len(a) == 1
    assert len(b) == 1


def test_wiring_bus_sink_into_client_emits_no_recursion(fake_client) -> None:
    client, channel = fake_client
    # Compose log + bus so the bus sink is actually driven by the client.
    client._events = CompositeEventSink([RabbitMQBusSink(client)])

    assert client.publish_with_confirm("q.other", {"x": 1}) is True

    exchanges = [p["exchange"] for p in channel.publishes]
    # Exactly one forwarded event, plus the original command publish — no loop.
    assert exchanges.count(EXCHANGE_EVENTS) == 1
    assert RabbitMQClient.EXCHANGE_P1 in exchanges
    assert len(channel.publishes) == 2


def test_declare_events_bus_provisions_topology(fake_client) -> None:
    client, channel = fake_client
    client.declare_events_bus()

    assert any(
        d.get("exchange") == EXCHANGE_EVENTS and d.get("type") == "topic"
        for d in channel.declares)
    assert any(d.get("queue") == QUEUE_GATEWAY_MQ_EVENTS for d in channel.declares)

    bound_keys = {b["routing_key"] for b in channel.binds}
    assert bound_keys == set(MQ_EVENTS)
