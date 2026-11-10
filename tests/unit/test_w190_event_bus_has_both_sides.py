"""One wire contract, two languages: the W190 bus must agree on both sides.

The Spring Cloud edge (``GatewayMqEventConsumer``) binds six routing keys on a
topic exchange; the Python agent runtime (``observability/event_vocabulary.py``
+ ``observability/mq_events.py``) publishes them. Before #1603 the Java class
claimed a producer that did not exist — a subscriber with nobody on the other
end, i.e. exactly the "fake control" this repo refuses to ship.

These legs reconcile **four** declarations of the same contract:

1. the Python vocabulary (``EVENT_KINDS`` / ``EXCHANGE_EVENTS``),
2. the Java ``KNOWN_EVENTS`` list and the ``@RabbitListener`` binding keys,
3. the gateway's ``application.yml`` (exchange / queue / default-off switch),
4. the producer's actual wiring into ``RabbitMQClient``.

A drift in any one of them is red. The Java sources are read as text with
narrow regular expressions (not by importing Java); the YAML and POM are
parsed, not grepped.
"""

from __future__ import annotations

import ast
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml

from observability.event_vocabulary import (
    ENV_BUS_ENABLED,
    EVENT_KINDS,
    EXCHANGE_EVENTS,
    GATEWAY_QUEUE,
    bus_enabled,
)

_REPO = Path(__file__).resolve().parents[2]
_GATEWAY = _REPO / "services" / "gateway"
_CONSUMER = (
    _GATEWAY / "src" / "main" / "java" / "dev" / "specproof"
    / "gateway" / "mq" / "GatewayMqEventConsumer.java"
)
_YAML = _GATEWAY / "src" / "main" / "resources" / "application.yml"
_POM = _GATEWAY / "pom.xml"
_RABBITMQ_PY = _REPO / "storage" / "rabbitmq.py"
_PRODUCER_PY = _REPO / "observability" / "mq_events.py"


def _java() -> str:
    return _CONSUMER.read_text(encoding="utf-8")


def _java_known_events(text: str) -> list[str]:
    match = re.search(r"KNOWN_EVENTS\s*=\s*List\.of\((.*?)\)\s*;", text, re.S)
    assert match, "no KNOWN_EVENTS declaration — the Java probe went blind"
    return re.findall(r'"([a-z_]+)"', match.group(1))


def _java_binding_keys(text: str) -> list[str]:
    match = re.search(r"key\s*=\s*\{(.*?)\}", text, re.S)
    assert match, "no @RabbitListener binding keys — the Java probe went blind"
    return re.findall(r'"([a-z_]+)"', match.group(1))


def _yaml_bus() -> dict[str, Any]:
    data = yaml.safe_load(_YAML.read_text(encoding="utf-8"))
    raw = data["specproof"]["gateway"]["mq-events"]
    assert isinstance(raw, dict), "specproof.gateway.mq-events is not a mapping"
    result: dict[str, Any] = {}
    for key, value in raw.items():
        result[str(key)] = value
    return result


def test_java_known_events_and_binding_keys_are_both_the_six() -> None:
    text = _java()
    known = _java_known_events(text)
    binding = _java_binding_keys(text)

    assert known == list(EVENT_KINDS), (
        f"Java KNOWN_EVENTS drifted from the Python vocabulary: {known}"
    )
    assert binding == list(EVENT_KINDS), (
        f"the @RabbitListener binds {binding}, but the producer publishes "
        f"{list(EVENT_KINDS)} — a key that is declared but never bound, or "
        "vice versa, is a silently dropped event"
    )


def test_the_exchange_and_queue_are_the_same_on_all_three_sides() -> None:
    text = _java()
    exchange_defaults = set(re.findall(
        r"specproof\.gateway\.mq-events\.exchange:([A-Za-z0-9._-]+)", text
    ))
    assert exchange_defaults == {EXCHANGE_EVENTS}, (
        f"Java @Value exchange default(s) {exchange_defaults} != {EXCHANGE_EVENTS!r}"
    )

    bus = _yaml_bus()
    assert bus["exchange"] == EXCHANGE_EVENTS
    assert bus["queue"] == GATEWAY_QUEUE

    queue_defaults = set(re.findall(
        r"specproof\.gateway\.mq-events\.queue:([A-Za-z0-9._-]+)", text
    ))
    assert queue_defaults == {GATEWAY_QUEUE}, (
        f"Java queue default(s) {queue_defaults} != {GATEWAY_QUEUE!r}"
    )


def test_both_sides_are_switched_off_by_default() -> None:
    bus = _yaml_bus()
    assert bus["enabled"] is False, (
        "the edge must not open a broker connection in the shipped default"
    )
    assert bus_enabled({}) is False, (
        "the producer must be off unless the exact-value switch is set"
    )
    assert bus_enabled({ENV_BUS_ENABLED: "1"}) is True

    text = _java()
    assert "@ConditionalOnProperty(" in text, (
        "the subscriber must be conditional; a bean that always starts a "
        "listener container would make 'default off' a lie"
    )
    having = re.search(r'havingValue\s*=\s*"([^"]+)"', text)
    assert having and having.group(1) == "true", (
        "only havingValue=\"true\" keeps the bean inert for every other value"
    )


def test_the_producer_really_exists_and_is_wired_into_the_client() -> None:
    """A subscriber without a publisher is a fake control — refuse it."""
    producer = _PRODUCER_PY.read_text(encoding="utf-8")
    emitter = _RABBITMQ_PY.read_text(encoding="utf-8")

    # #1603 shipped the one real publisher; #1605 wires it behind the switch.
    assert "class RabbitMQBusSink" in emitter
    assert "basic_publish(" in emitter, "the bus sink must really publish bytes"
    assert "def event_sink_from_env(" in producer
    assert "RabbitMQBusSink" in producer, (
        "the wiring must delegate to the ONE existing publisher, not grow a "
        "second publishing implementation"
    )

    tree = ast.parse(emitter)
    wired = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "event_sink_from_env"
        for node in ast.walk(tree)
    )
    assert wired, (
        "the broker sink exists but RabbitMQClient never installs it: the six "
        "events would still go only to the logger and the edge would hear nothing"
    )


def test_the_python_side_has_one_vocabulary_owner() -> None:
    import storage.rabbitmq as module

    assert tuple(module.MQ_EVENTS) == EVENT_KINDS
    assert module.EXCHANGE_EVENTS == EXCHANGE_EVENTS
    assert module.QUEUE_GATEWAY_MQ_EVENTS == GATEWAY_QUEUE


def test_the_gateway_pulls_the_amqp_starter_from_its_boot_parent() -> None:
    ns = {"m": "http://maven.apache.org/POM/4.0.0"}
    root = ET.parse(_POM).getroot()
    deps = root.findall("m:dependencies/m:dependency", ns)
    amqp = [
        dep for dep in deps
        if (dep.findtext("m:artifactId", default="", namespaces=ns)
            == "spring-boot-starter-amqp")
    ]

    assert len(amqp) == 1, (
        "the listener needs spring-boot-starter-amqp; without it the Java "
        "class cannot compile, and a doc claiming it works would be false"
    )
    assert amqp[0].find("m:version", ns) is None, (
        "the starter must be version-managed by the Boot parent (3.4.3), "
        "not pinned independently — the two would drift on the next upgrade"
    )


def test_routing_keys_are_the_event_names_not_a_translation() -> None:
    """A prefix or mapping table would silently break both sides at once."""
    from observability.event_vocabulary import routing_key_for

    assert [routing_key_for(kind) for kind in EVENT_KINDS] == list(EVENT_KINDS)
