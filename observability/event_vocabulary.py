"""The single owner of the W190 six-event RabbitMQ bus vocabulary (#1603).

`storage/rabbitmq.py` emits one structured event per reliable-delivery step.
The Spring Cloud edge (``GatewayMqEventConsumer``) consumes them. Two processes
that never import each other's code can only agree on a wire contract if that
contract has **one** definition, so this leaf module (no project imports) is
it:

* the exchange name and the edge's queue name,
* the six event names,
* the fact that a routing key IS the event name (no prefix, no translation),
* the exact-value env switch that turns the producer on.

The Java consumer declares the same six strings in
``services/gateway/src/main/java/dev/specproof/gateway/mq/GatewayMqEventConsumer.java``
and ``tests/unit/test_w190_event_bus_has_both_sides.py`` refuses to let the two
copies drift. A *new* event must be added here first, then to the emitter, then
to the edge — the gate makes that order visible.

#1605: `storage/rabbitmq.py` used to keep a second copy of the tuple and the
exchange/queue strings. It now re-exports these names as aliases so the seven
existing bus-sink tests keep importing them, but there is only one definition.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

#: Topic exchange. Declared idempotently by both sides (AMQP declaration is
#: idempotent): the producer declares it before publishing, the edge declares
#: it as part of its ``@QueueBinding``. Neither side assumes the other booted
#: first.
EXCHANGE_EVENTS = "specproof.observability.events"

#: Exact-value switch: only the literal ``1`` enables the producer. Anything
#: else (unset, empty, "0", "true") leaves the legacy no-op sink in place, so
#: an unconfigured deployment is byte-identical to the pre-#1603 behavior.
ENV_BUS_ENABLED = "SPECPROOF_MQ_EVENTS_ENABLED"
# Tied on purpose: `bus_enabled` spells the literal below so the shipped
# bytes carry the name an operator sets (the knob census counts literal
# reads; a switch read through a constant is invisible to it — #L06).
assert ENV_BUS_ENABLED == "SPECPROOF_MQ_EVENTS_ENABLED"

#: The durable queue owned by the Spring Cloud edge. The producer may declare
#: and bind it (``RabbitMQClient.declare_events_bus``) but never consumes it.
GATEWAY_QUEUE = "q.gateway.mq-events"


class MqEvent:
    """The six names. Order is the order the reliable-delivery pipeline uses."""

    PUBLISHED = "published"
    PUBLISH_CONFIRM_TIMEOUT = "publish_confirm_timeout"
    CONSUMED = "consumed"
    DUPLICATE_ACKED = "duplicate_acked"
    RETRY_SCHEDULED = "retry_scheduled"
    DEAD_LETTERED = "dead_lettered"


EVENT_KINDS: tuple[str, ...] = (
    MqEvent.PUBLISHED,
    MqEvent.PUBLISH_CONFIRM_TIMEOUT,
    MqEvent.CONSUMED,
    MqEvent.DUPLICATE_ACKED,
    MqEvent.RETRY_SCHEDULED,
    MqEvent.DEAD_LETTERED,
)


def bus_enabled(env: Mapping[str, str] | None = None) -> bool:
    """True only for the literal ``1``; every other value keeps the bus off."""
    if env is not None:
        return env.get("SPECPROOF_MQ_EVENTS_ENABLED", "").strip() == "1"
    # Spelled as ``os.environ.get(...)`` with the literal name so the shipped
    # bytes carry the read an operator performs (the knob census counts this
    # shape); ``env=`` keeps the test seam.
    return os.environ.get("SPECPROOF_MQ_EVENTS_ENABLED", "").strip() == "1"


def routing_key_for(kind: str) -> str:
    """A routing key is the event name itself — no prefix, no mapping table.

    The edge binds exactly these six keys. A seventh key would be a message
    nobody consumes, so the wired producer refuses unknown kinds instead of
    inventing a routing key for them.
    """
    return kind
