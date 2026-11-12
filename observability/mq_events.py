"""Wiring and safety guard for the W190 event bus producer (#1603 / #1605).

There is exactly ONE publishing implementation: ``RabbitMQBusSink`` in
``storage/rabbitmq.py`` (7 tests in ``test_rabbitmq_bus_sink.py``). This module
does not publish anything itself. It answers the two questions that class
deliberately leaves to its caller:

1. **When** is the bus on? ``bus_enabled()`` — the exact-value switch.
2. **What if the broker is down?** ``GuardedBusSink`` wraps the delegate so an
   observability failure is counted and logged but can never change the
   delivery pipeline's verdict. It also refuses event names outside the six
   (publishing one would create a routing key the edge does not bind) and
   provisions the topic exchange / queue / six bindings lazily on the first
   event.

``event_sink_from_env()`` composes the log sink and the bus sink when the
switch is on, and returns ``None`` when it is off — the caller's fallback to
the historical ``_noop_sink`` then stays byte-identical to the pre-#1603
behavior. Constructing a client never opens a connection.

The ``storage.rabbitmq`` import is deliberately INSIDE the factory function:
``storage/rabbitmq.py`` imports this module at module scope, so a module-level
import back would be a cycle.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from observability.event_vocabulary import (
    ENV_BUS_ENABLED,
    EVENT_KINDS,
    bus_enabled,
)
from observability.metrics import incr

LOGGER = logging.getLogger(__name__)

# Emission names are BARE; observability/metrics.py prepends
# ``specproof_`` only at exposition time. Writing the prefix here
# would render ``/metrics`` as ``specproof_specproof_*`` and break
# every reader-facing comparison the docs make against this module.
METRIC_PUBLISHED = "w190_events_published_total"
METRIC_FAILED = "w190_events_publish_failures_total"
METRIC_UNKNOWN = "w190_events_unknown_total"


class GuardedBusSink:
    """Fail-safe wrapper around the one real ``RabbitMQBusSink``."""

    def __init__(self, delegate: Any, client: Any) -> None:
        self._delegate = delegate
        self._client = client
        self._declared = False

    def __call__(self, event: dict[str, Any]) -> None:
        kind = event.get("event") if isinstance(event, Mapping) else None
        if not isinstance(kind, str) or kind not in EVENT_KINDS:
            # Fail closed on the vocabulary: never invent a routing key for a
            # word the edge does not bind. Count it so the omission is visible.
            incr(METRIC_UNKNOWN)
            LOGGER.warning(
                "W190 event bus dropped an unrecognised event kind: %r", kind
            )
            return

        try:
            if not self._declared:
                self._client.declare_events_bus()
                self._declared = True
            self._delegate(event)
            incr(METRIC_PUBLISHED)
        except Exception as exc:  # noqa: BLE001 — observability is best effort: a broker outage must not change the delivery pipeline's verdict; count it, log it, force a reconnect on the next event
            incr(METRIC_FAILED)
            LOGGER.warning(
                "W190 event bus publish failed for %s: %s: %s",
                kind, type(exc).__name__, exc,
            )
            self._client._channel = None
            self._declared = False


def event_sink_from_env(
    client: Any,
    env: Mapping[str, str] | None = None,
) -> Any:
    """Build the opt-in composite sink, or ``None`` when the bus is off.

    ``None`` (rather than a no-op object) is deliberate: the caller's fallback
    to ``_noop_sink`` stays exactly the object it used before #1603.
    """
    if not bus_enabled(env):
        return None

    # Imported here, not at module scope: storage.rabbitmq imports this module.
    from storage.rabbitmq import (  # noqa: PLC0415 — cycle break, see docstring
        CompositeEventSink,
        RabbitMQBusSink,
        RabbitMQEventLog,
    )

    bus = GuardedBusSink(RabbitMQBusSink(client=client), client)
    return CompositeEventSink([RabbitMQEventLog(), bus])


__all__ = [
    "ENV_BUS_ENABLED",
    "METRIC_FAILED",
    "METRIC_PUBLISHED",
    "METRIC_UNKNOWN",
    "GuardedBusSink",
    "event_sink_from_env",
]
