"""The W190 bus has ONE producer, and the opt-in wiring cannot break delivery.

#1603 shipped ``RabbitMQBusSink`` in ``storage/rabbitmq.py`` (7 tests in
``test_rabbitmq_bus_sink.py``) but left it unwired: an operator had to
construct and inject it by hand, and nothing caught a broker outage. #1605
adds the exact-value switch, the vocabulary guard and the failure guard in
``observability/mq_events.py`` — without adding a second publishing class.

These legs pin that wiring. The cross-language reconciliation (six names,
exchange, queue, default-off, POM dependency) lives in
``test_w190_event_bus_has_both_sides.py``.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from observability.event_vocabulary import (
    ENV_BUS_ENABLED,
    EVENT_KINDS,
    EXCHANGE_EVENTS,
    GATEWAY_QUEUE,
    MqEvent,
    bus_enabled,
    routing_key_for,
)
from observability.metrics import snapshot as metrics_snapshot
from observability.mq_events import (
    METRIC_FAILED,
    METRIC_PUBLISHED,
    METRIC_UNKNOWN,
    GuardedBusSink,
    event_sink_from_env,
)

_REPO = Path(__file__).resolve().parents[2]
_RABBITMQ_PY = _REPO / "storage" / "rabbitmq.py"


class _FakeChannel:
    is_open = True
    is_closed = False

    def __init__(self, fail_once: bool = False) -> None:
        self.publishes: list[dict[str, Any]] = []
        self.declares: list[dict[str, Any]] = []
        self.binds: list[dict[str, Any]] = []
        self._fail_once = fail_once

    def exchange_declare(self, exchange: str, exchange_type: str,
                         durable: bool) -> None:
        self.declares.append({"exchange": exchange, "type": exchange_type,
                              "durable": durable})

    def queue_declare(self, queue: str, durable: bool) -> None:
        self.declares.append({"queue": queue, "durable": durable})

    def queue_bind(self, exchange: str, queue: str, routing_key: str) -> None:
        self.binds.append({"exchange": exchange, "queue": queue,
                           "routing_key": routing_key})

    def basic_publish(self, *, exchange: str, routing_key: str,
                      body: bytes, properties: Any) -> None:
        if self._fail_once:
            self._fail_once = False
            raise OSError("broker unreachable")
        self.publishes.append({
            "exchange": exchange,
            "routing_key": routing_key,
            "body": body,
            "delivery_mode": properties.delivery_mode,
            "content_type": properties.content_type,
        })


def _counter(name: str) -> float:
    value: object = metrics_snapshot()["counters"].get(name, 0.0)
    return float(value) if isinstance(value, (int, float)) else 0.0


def _wired_client(monkeypatch: pytest.MonkeyPatch, channel: _FakeChannel) -> Any:
    """A client whose channel property returns ``channel`` without a broker."""
    import storage.rabbitmq as module
    from storage.rabbitmq import RabbitMQClient

    client = RabbitMQClient()
    client._channel = channel
    client._connection = None
    monkeypatch.setattr(
        module.RabbitMQClient, "channel", property(lambda _self: channel)
    )
    return client


def _enabled_sink(monkeypatch: pytest.MonkeyPatch,
                  channel: _FakeChannel) -> tuple[Any, Any]:
    monkeypatch.setenv(ENV_BUS_ENABLED, "1")
    client = _wired_client(monkeypatch, channel)
    sink = event_sink_from_env(client=client)
    assert sink is not None
    return client, sink


def _emitted_event_names() -> list[str]:
    tree = ast.parse(_RABBITMQ_PY.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values, strict=False):
            if not (isinstance(key, ast.Constant) and key.value == "event"):
                continue
            if isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name):
                if value.value.id == "MqEvent":
                    names.append(str(getattr(MqEvent, value.attr)))
            elif isinstance(value, ast.Constant) and isinstance(value.value, str):
                names.append(value.value)
    return names


def test_the_emitter_uses_only_the_canonical_six_names() -> None:
    emitted = _emitted_event_names()

    assert emitted, "no 'event' emit sites found — the AST probe went blind"
    assert set(emitted) == set(EVENT_KINDS), (
        "storage/rabbitmq.py emits a name the bus does not declare, or a "
        "declared event has no emit site (dead vocabulary)"
    )
    assert len(EVENT_KINDS) == len(set(EVENT_KINDS)) == 6


def test_the_python_constants_are_aliases_not_a_second_copy() -> None:
    import storage.rabbitmq as module

    assert module.MQ_EVENTS is EVENT_KINDS
    assert module.EXCHANGE_EVENTS == EXCHANGE_EVENTS
    assert module.QUEUE_GATEWAY_MQ_EVENTS == GATEWAY_QUEUE


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, False), ("", False), ("0", False), ("true", False),
     ("TRUE", False), (" 1 ", True), ("1", True)],
)
def test_the_switch_accepts_only_literal_one(value: str | None, expected: bool) -> None:
    env = {} if value is None else {ENV_BUS_ENABLED: value}
    assert bus_enabled(env) is expected


def test_switch_off_installs_the_original_noop_sink(monkeypatch: pytest.MonkeyPatch) -> None:
    from storage.rabbitmq import RabbitMQClient, _noop_sink

    monkeypatch.delenv(ENV_BUS_ENABLED, raising=False)
    client = RabbitMQClient()

    assert client._events is _noop_sink, (
        "an unconfigured deployment must keep byte-identical legacy behavior"
    )
    assert event_sink_from_env(client=client) is None


def test_switch_on_installs_a_lazy_sink(monkeypatch: pytest.MonkeyPatch) -> None:
    from storage.rabbitmq import RabbitMQClient

    monkeypatch.setenv(ENV_BUS_ENABLED, "1")
    client = RabbitMQClient()

    from storage.rabbitmq import CompositeEventSink, RabbitMQEventLog

    assert client._channel is None, (
        "constructing a client must not open a broker connection"
    )
    assert isinstance(client._events, CompositeEventSink)
    sinks = client._events._sinks
    assert len(sinks) == 2
    assert isinstance(sinks[0], RabbitMQEventLog), "logging must survive the bus"
    assert isinstance(sinks[1], GuardedBusSink), "the guarded bus sink is wired"


def test_a_known_event_reaches_the_exchange_with_the_wire_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel = _FakeChannel()
    _, sink = _enabled_sink(monkeypatch, channel)
    payload = {"event": MqEvent.PUBLISHED, "routing_key": "q.p1.verify.job"}
    before = _counter(METRIC_PUBLISHED)

    sink(payload)

    assert len(channel.publishes) == 1
    sent = channel.publishes[0]
    assert sent["exchange"] == EXCHANGE_EVENTS
    assert sent["routing_key"] == MqEvent.PUBLISHED
    assert json.loads(sent["body"]) == payload
    assert sent["delivery_mode"] == 2
    assert sent["content_type"] == "application/json"
    assert _counter(METRIC_PUBLISHED) == before + 1


def test_the_six_events_are_forwarded_under_their_own_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel = _FakeChannel()
    _, sink = _enabled_sink(monkeypatch, channel)

    for kind in EVENT_KINDS:
        sink({"event": kind})

    assert [p["routing_key"] for p in channel.publishes] == list(EVENT_KINDS)
    assert [b["routing_key"] for b in channel.binds] == list(EVENT_KINDS)
    assert all(b["exchange"] == EXCHANGE_EVENTS and b["queue"] == GATEWAY_QUEUE
               for b in channel.binds)
    # topology is declared once, not once per event
    assert len([d for d in channel.declares if "exchange" in d]) == 1


def test_an_unknown_kind_is_not_published_but_is_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel = _FakeChannel()
    _, sink = _enabled_sink(monkeypatch, channel)
    before = _counter(METRIC_UNKNOWN)

    sink({"event": "invented_kind"})

    assert channel.publishes == [], (
        "an invented routing key would be a message nobody binds — fail closed"
    )
    assert _counter(METRIC_UNKNOWN) == before + 1


def test_a_broker_failure_is_counted_and_never_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel = _FakeChannel(fail_once=True)
    client, sink = _enabled_sink(monkeypatch, channel)
    before = _counter(METRIC_FAILED)

    sink({"event": MqEvent.DEAD_LETTERED})  # must not raise

    assert _counter(METRIC_FAILED) == before + 1
    assert client._channel is None, "a dead channel must be dropped for reconnect"

    sink({"event": MqEvent.RETRY_SCHEDULED})
    assert len(channel.publishes) == 1, "the next event reconnects and succeeds"


def test_the_guard_is_a_wrapper_not_a_second_publisher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from storage.rabbitmq import RabbitMQBusSink

    channel = _FakeChannel()
    client = _wired_client(monkeypatch, channel)
    guard = GuardedBusSink(RabbitMQBusSink(client=client), client)

    guard({"event": MqEvent.CONSUMED})

    assert len(channel.publishes) == 1, (
        "one emitted event must produce exactly one forwarded event — no "
        "recursion and no duplicate publishing implementation"
    )
    assert [routing_key_for(kind) for kind in EVENT_KINDS] == list(EVENT_KINDS)
