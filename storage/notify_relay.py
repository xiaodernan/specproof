"""Notify Outbox Relay — polls MySQL notify_outbox and POSTs webhooks.

Runs as a background thread or standalone process; multiple instances are
safe via SELECT ... FOR UPDATE SKIP LOCKED. Same governance the job-event
outbox relay got in §14.2 (§16.6-1 closed the "best-effort ≠ delivered" gap
for webhooks):

  - a row is marked delivered only AFTER the connector reports SENT;
  - a FAILED delivery defers the row (exponential backoff) instead of
    busy-retrying, and dead-letters it past max_retries;
  - DISABLED means nobody configured a receiver: the row cannot ever be
    delivered, so it is dead-lettered immediately (operator replay after
    configuring) instead of being retried into the void;
  - the payload is the notification AS BUILT at enqueue time — the relay
    reproduces the exact announcement the terminal verdict earned, immune
    to later template edits.

Metrics mirror the outbox family: specproof_notify_outbox_*.
"""

import contextlib
import logging
import os
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from observability.metrics import incr, set_gauge
from storage.mysql import MySQLStore

logger = logging.getLogger(__name__)

#: Relay metric names — gauge/counter keys in the observability.metrics
#: registry (rendered as specproof_notify_outbox_* by /metrics).
METRIC_PENDING = "notify_outbox_pending"
METRIC_OLDEST_AGE_SECONDS = "notify_outbox_oldest_age_seconds"
METRIC_RETRY_COUNT = "notify_outbox_retry_count"
METRIC_DEAD_LETTERS = "notify_outbox_dead_letters"
METRIC_LAST_SUCCESS_TS = "notify_outbox_last_success_ts"
COUNTER_DELIVERED = "notify_outbox_delivered_total"
COUNTER_FAILED = "notify_outbox_failed_total"
COUNTER_DEAD_LETTERED = "notify_outbox_dead_lettered_total"

#: How the worker spells the lane switch (SPECPROOF_NOTIFY_OUTBOX=1).
NOTIFY_OUTBOX_ENV = "SPECPROOF_NOTIFY_OUTBOX"


def notify_outbox_lane_enabled() -> bool:
    """True when the worker should ENQUEUE instead of sending directly."""
    return os.getenv(NOTIFY_OUTBOX_ENV, "").strip().lower() in (
        "1", "true", "yes", "on",
    )


@dataclass(frozen=True)
class _Delivered:
    """One delivery the relay can reproduce byte-for-byte from the row."""

    event_type: str
    title: str
    text: str
    blocks: tuple[dict[str, Any], ...]
    job_id: str


def _notification_from_payload(payload: dict[str, Any]) -> Any:
    """Rebuild the frozen Notification from the stored JSON payload."""
    from integrations.notify.protocol import Notification

    return Notification(
        event_type=str(payload.get("event_type", "")),
        title=str(payload.get("title", "")),
        text=str(payload.get("text", "")),
        blocks=tuple(payload.get("blocks") or ()),
        job_id=str(payload.get("job_id", "")),
    )


class NotifyOutboxRelay:
    """Polls notify_outbox and POSTs the stored notifications.

    Each cycle:
      1. SELECT ... FOR UPDATE SKIP LOCKED (due undelivered rows, oldest
         first; dead-lettered rows are excluded)
      2. For each row: rebuild the Notification and hand it to the
         connector (the same factory the direct lane uses)
      3. On SENT: mark delivered — only after the endpoint accepted
      4. On FAILED: record last_error and defer; rows past max_retries
         are dead-lettered instead of retried forever
      5. On DISABLED: dead-letter immediately (no receiver configured;
         retrying would be noise, configuring one is an operator action)

    At-least-once semantics: a crash between the POST and the delivered
    UPDATE re-delivers on the next cycle. Receivers dedupe on job_id +
    event_type if they need exactly-once presentation.
    """

    MAX_BACKOFF = 60  # seconds
    DEFAULT_MAX_RETRIES = 5

    def __init__(
        self,
        mysql: MySQLStore | None = None,
        connector_factory: Callable[[], Any] | None = None,
        poll_interval: float = 1.0,
        batch_size: int = 10,
        max_retries: int = DEFAULT_MAX_RETRIES,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        self.mysql = mysql or MySQLStore()
        # Lazily resolved so tests and relays without a webhook config get a
        # DisabledConnector from the same factory the direct lane uses.
        self._connector_factory = connector_factory
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self.max_retries = max_retries
        self._now = now_fn or time.time
        self._stop = False
        self._delivered = 0
        self._failures = 0
        self._last_success_ts: float | None = None

    def _connector(self) -> Any:
        if self._connector_factory is not None:
            return self._connector_factory()
        from integrations.notify import webhook_connector_from_env

        return webhook_connector_from_env()

    def drain_pending(self) -> int:
        """Deliver the current locked batch of due rows. Returns count delivered."""
        rows = self.mysql.fetch_due_notify_intents(self.batch_size)
        delivered = 0
        for row in rows:
            raw_payload = row.get("payload")
            if isinstance(raw_payload, str):
                import json

                payload: dict[str, Any] = json.loads(raw_payload)
            else:
                payload = dict(raw_payload or {})
            connector = self._connector()
            try:
                status = connector.send(_notification_from_payload(payload))
            except Exception as exc:  # noqa: BLE001 - connector misconfig
                status = None
                error = str(exc)[:1000]
            else:
                error = ""
            with contextlib.suppress(Exception):
                connector.close()
            if status is not None and str(status).lower().endswith("sent"):
                self.mysql.mark_notify_delivered(row["id"])
                delivered += 1
                self._delivered += 1
                self._last_success_ts = self._now()
                incr(COUNTER_DELIVERED)
                set_gauge(METRIC_LAST_SUCCESS_TS, self._last_success_ts)
                logger.info(
                    "Notify outbox delivered: id=%s job=%s verdict=%s",
                    row["id"], row["job_id"], row["verdict"],
                )
                continue
            attempts = int(row.get("attempts", 0)) + 1
            if status is None:
                reason = error or "connector raised"
                self._dead_letter_or_defer(row, attempts, reason, hard=True)
                continue
            # DISABLED: no receiver configured — retrying cannot help.
            if str(status).upper() == "DISABLED":
                self.mysql.dead_letter_notify_intent(
                    row["id"], "no webhook configured (connector disabled)"
                )
                incr(COUNTER_DEAD_LETTERED)
                logger.warning(
                    "Notify outbox dead-lettered (no receiver): id=%s job=%s",
                    row["id"], row["job_id"],
                )
                continue
            # FAILED: the endpoint did not accept it — defer and retry.
            self._dead_letter_or_defer(
                row, attempts, f"delivery failed: {status}", hard=False,
            )
        return delivered

    def _dead_letter_or_defer(
        self, row: dict[str, Any], attempts: int, error: str, *, hard: bool
    ) -> None:
        self._failures += 1
        incr(COUNTER_FAILED)
        if hard or attempts > self.max_retries:
            self.mysql.dead_letter_notify_intent(row["id"], error)
            incr(COUNTER_DEAD_LETTERED)
            logger.error(
                "Notify outbox dead-lettered: id=%s job=%s attempts=%s error=%s",
                row["id"], row["job_id"], attempts, error,
            )
            return
        retry_after = min(2 ** attempts, self.MAX_BACKOFF)
        self.mysql.mark_notify_failed(row["id"], error, retry_after)
        logger.warning(
            "Notify delivery failed, deferred %ss: id=%s job=%s error=%s",
            retry_after, row["id"], row["job_id"], error,
        )

    def refresh_metrics(self) -> None:
        """Push the governance snapshot into the metrics gauges."""
        stats = self.mysql.notify_outbox_stats()
        set_gauge(METRIC_PENDING, stats["pending"])
        set_gauge(METRIC_DEAD_LETTERS, stats["dead_letters"])
        set_gauge(METRIC_RETRY_COUNT, stats["retries"])
        oldest = stats.get("oldest_created_at")
        if oldest is not None:
            age = max(0.0, self._now() - _to_epoch(oldest))
            set_gauge(METRIC_OLDEST_AGE_SECONDS, age)
        if self._last_success_ts is not None:
            set_gauge(METRIC_LAST_SUCCESS_TS, self._last_success_ts)

    def run_forever(self) -> None:
        """Poll until stopped; back off while there is nothing to deliver."""
        logger.info("Notify outbox relay started (pid=%s)", os.getpid())

        def _stop(*_: Any) -> None:
            self._stop = True

        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(Exception):
                signal.signal(sig, _stop)
        while not self._stop:
            try:
                self.drain_pending()
                self.refresh_metrics()
                time.sleep(self.poll_interval)
            except Exception:
                logger.exception("notify relay cycle failed; backing off")
                time.sleep(self.MAX_BACKOFF)
        logger.info("Notify outbox relay stopped")

    def stop(self) -> None:
        self._stop = True


def _to_epoch(value: Any) -> float:
    """Best-effort conversion of a MySQL timestamp to epoch seconds."""
    if isinstance(value, (int, float)):
        return float(value)
    try:
        from datetime import datetime

        if isinstance(value, datetime):
            return value.timestamp()
        return datetime.fromisoformat(str(value)).timestamp()
    except Exception:
        return 0.0


def run_as_process() -> None:
    """Entry point for `python -m storage.notify_relay` (standalone relay)."""
    NotifyOutboxRelay().run_forever()


if __name__ == "__main__":
    run_as_process()
