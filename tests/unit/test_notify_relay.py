"""Notify outbox relay — at-least-once webhook delivery (#16.6-1).

The relay owns delivery once the worker enqueued the intent. Governance
mirrors the job-event outbox (§14.2): delivered only after the endpoint
accepted, deferred on failure, dead-lettered past max_retries — and one
honest extra: a DISABLED connector means nobody configured a receiver,
so the row is dead-lettered immediately instead of being retried into
the void.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from integrations.notify.protocol import Notification, SendStatus
from storage.notify_relay import NotifyOutboxRelay

PAYLOAD = {
    "event_type": "verification.verified",
    "title": "SpecProof verification passed",
    "text": "Verdict: VERIFIED",
    "blocks": [],
    "job_id": "job-r",
}


class RecordingNotifyStore:
    """Serves canned rows; records every governance write."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.delivered: list[int] = []
        self.failed: list[tuple[int, str, float]] = []
        self.dead_lettered: list[tuple[int, str]] = []

    def fetch_due_notify_intents(self, limit: int = 10) -> list[dict[str, Any]]:
        return self.rows[:limit]

    def mark_notify_delivered(self, notify_id: int) -> None:
        self.delivered.append(notify_id)

    def mark_notify_failed(
        self, notify_id: int, error: str, retry_after_seconds: float
    ) -> None:
        self.failed.append((notify_id, error, retry_after_seconds))

    def dead_letter_notify_intent(self, notify_id: int, error: str) -> None:
        self.dead_lettered.append((notify_id, error))

    def notify_outbox_stats(self) -> dict[str, Any]:
        return {
            "pending": 0,
            "dead_letters": 0,
            "retries": 0,
            "oldest_created_at": None,
            "last_success": None,
        }


class RelayConnector:
    def __init__(self, status: SendStatus, exc: BaseException | None = None):
        self.name = "relay-test"
        self.capabilities = frozenset()
        self.sent: list[Notification] = []
        self.closed = 0
        self._status = status
        self._exc = exc

    def send(self, notification: Notification) -> SendStatus:
        if self._exc is not None:
            raise self._exc
        self.sent.append(notification)
        return self._status

    def close(self) -> None:
        self.closed += 1


def _row(
    notify_id: int = 1, payload: Any = None, attempts: int = 0
) -> dict[str, Any]:
    return {
        "id": notify_id,
        "job_id": "job-r",
        "verdict": "VERIFIED",
        "payload": json.dumps(PAYLOAD) if payload is None else payload,
        "attempts": attempts,
    }


def _relay(
    store: RecordingNotifyStore, connector: RelayConnector, max_retries: int = 5,
) -> NotifyOutboxRelay:
    return NotifyOutboxRelay(
        mysql=store,  # type: ignore[arg-type]
        connector_factory=lambda: connector,
        max_retries=max_retries,
        now_fn=lambda: 1000.0,
    )


def test_sent_payload_is_delivered_and_marked() -> None:
    store = RecordingNotifyStore([_row()])
    connector = RelayConnector(SendStatus.SENT)

    delivered = _relay(store, connector).drain_pending()

    assert delivered == 1
    assert store.delivered == [1]
    assert store.failed == [] and store.dead_lettered == []
    # The notification is REBUILT from the stored payload, not re-derived
    # from current templates. (blocks round-trips as a tuple — the frozen
    # dataclass's own type.)
    assert connector.sent == [Notification(**{**PAYLOAD, "blocks": ()})]
    assert connector.closed == 1, "the connector owns an HTTP client"


def test_failed_delivery_is_deferred_not_dead_lettered() -> None:
    store = RecordingNotifyStore([_row()])
    connector = RelayConnector(SendStatus.FAILED)

    _relay(store, connector).drain_pending()

    assert store.delivered == []
    assert store.dead_lettered == []
    (notify_id, error, retry_after) = store.failed[0]
    assert notify_id == 1
    assert "delivery failed" in error
    assert retry_after >= 2, "exponential backoff starts at 2s"


def test_retry_exhaustion_dead_letters() -> None:
    store = RecordingNotifyStore([_row(attempts=5)])
    connector = RelayConnector(SendStatus.FAILED)

    _relay(store, connector, max_retries=5).drain_pending()

    assert store.delivered == [] and store.failed == []
    assert store.dead_lettered == [(1, "delivery failed: failed")]


def test_disabled_connector_dead_letters_immediately() -> None:
    """No receiver configured cannot be fixed by retrying — the row waits
    for an operator to configure one and replay it."""
    store = RecordingNotifyStore([_row()])
    connector = RelayConnector(SendStatus.DISABLED)

    _relay(store, connector).drain_pending()

    assert store.delivered == [] and store.failed == []
    assert store.dead_lettered == [(1, "no webhook configured (connector disabled)")]


def test_connector_raise_is_hard_dead_lettered() -> None:
    """The connector contract says delivery-level failures come back as a
    status; a raise means configuration is broken, and retrying cannot fix
    a bad configuration."""
    store = RecordingNotifyStore([_row()])
    connector = RelayConnector(SendStatus.FAILED, exc=RuntimeError("bad url"))

    _relay(store, connector).drain_pending()

    assert store.delivered == [] and store.failed == []
    assert store.dead_lettered and "bad url" in store.dead_lettered[0][1]


def test_payload_json_string_is_parsed() -> None:
    store = RecordingNotifyStore([_row(payload=json.dumps(PAYLOAD))])
    connector = RelayConnector(SendStatus.SENT)

    _relay(store, connector).drain_pending()

    assert connector.sent == [Notification(**{**PAYLOAD, "blocks": ()})]
