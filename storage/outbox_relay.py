"""Outbox Relay — poll-based MySQL→RabbitMQ relay with claim-and-publish.

P1.2: Polls outbox_events table every 1s, claims PENDING rows with
SELECT FOR UPDATE SKIP LOCKED, publishes to RabbitMQ with confirm,
marks PUBLISHED on success, resets stale CLAIMED rows after timeout.
"""

import json
import logging
import time
from typing import Any

import pika
from pika.exceptions import AMQPConnectionError

from storage.mysql import MySQLStore
from storage.rabbitmq import RabbitMQClient

logger = logging.getLogger(__name__)


class OutboxRelay:
    """Polls outbox_events and publishes to RabbitMQ with at-least-once delivery."""

    def __init__(
        self,
        mysql: MySQLStore | None = None,
        rabbitmq: RabbitMQClient | None = None,
        *,
        poll_interval_seconds: float = 1.0,
        batch_size: int = 10,
        claim_timeout_seconds: int = 60,
        claimed_by: str = "relay-1",
    ) -> None:
        self.mysql = mysql or MySQLStore()
        self.rabbitmq = rabbitmq or RabbitMQClient()
        self.poll_interval = poll_interval_seconds
        self.batch_size = batch_size
        self.claim_timeout = claim_timeout_seconds
        self.claimed_by = claimed_by
        self._running = False

    def _ensure_topology(self) -> None:
        try:
            self.rabbitmq.ensure_p1_topology()
        except (AMQPConnectionError, pika.exceptions.ChannelError) as e:
            logger.warning("Cannot ensure RabbitMQ topology: %s", e)

    def drain_pending(self) -> int:
        """Claim and publish all pending events. Returns count published."""
        published = 0
        events = self.mysql.claim_pending_events(
            limit=self.batch_size,
            claimed_by=self.claimed_by,
        )
        for event in events:
            event_id = event.get("event_id", "")
            try:
                payload = self._build_message(event)
                routing_key = event.get("routing_key", "q.verification.run")
                self.rabbitmq.publish_with_confirm(routing_key, payload)
                self.mysql.mark_event_published(event_id)
                published += 1
                logger.info("Published event %s type=%s", event_id, event.get("event_type"))
            except Exception as e:
                logger.exception("Failed to publish event %s: %s", event_id, e)
                self.mysql.mark_event_failed(event_id, str(e)[:2000])
        return published

    @staticmethod
    def _build_message(event: dict[str, Any]) -> dict[str, Any]:
        payload = event.get("payload", {})
        if isinstance(payload, str):
            payload = json.loads(payload)
        return {
            "event_id": event.get("event_id", ""),
            "event_type": event.get("event_type", ""),
            "outbox_id": event.get("id"),
            "job_id": event.get("aggregate_id", ""),
            "trace_id": event.get("trace_id", ""),
            "payload": payload,
            "created_at": str(event.get("occurred_at", "")),
        }

    def run_once(self) -> int:
        """Recover stale claims, then drain pending. Returns total published."""
        recovered = self.mysql.recover_stale_claims(older_than_seconds=self.claim_timeout)
        if recovered:
            logger.info("Recovered %d stale outbox claims", recovered)
        self._ensure_topology()
        return self.drain_pending()

    def run_forever(self) -> None:
        """Blocking relay loop. Call from a dedicated thread/process."""
        self._running = True
        self._ensure_topology()
        logger.info(
            "OutboxRelay started (interval=%.1fs, batch=%d, claim_by=%s)",
            self.poll_interval,
            self.batch_size,
            self.claimed_by,
        )
        while self._running:
            try:
                self.mysql.recover_stale_claims(older_than_seconds=self.claim_timeout)
                published = self.drain_pending()
                if published:
                    logger.debug("Published %d outbox events", published)
            except Exception:
                logger.exception("OutboxRelay cycle failed, will retry")
            time.sleep(self.poll_interval)

    def stop(self) -> None:
        self._running = False
