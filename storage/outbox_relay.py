"""Outbox Relay — polls MySQL outbox table and publishes to RabbitMQ.

Runs as a background thread or standalone process. Uses SELECT FOR UPDATE
SKIP LOCKED so multiple relay instances are safe.
"""

import logging
import signal
import time
from typing import Any

from storage.mysql import MySQLStore
from storage.rabbitmq import RabbitMQClient

logger = logging.getLogger(__name__)


class OutboxRelay:
    """Polls the outbox table and publishes events to RabbitMQ.

    Each cycle:
      1. SELECT ... FOR UPDATE SKIP LOCKED (unpublished rows, oldest first)
      2. For each row: publish to RabbitMQ with Publisher Confirm
      3. On success: UPDATE published_at = NOW()
      4. On failure: leave published_at NULL for next retry

    Uses exponential backoff when RabbitMQ is unreachable.
    """

    MAX_BACKOFF = 60  # seconds

    def __init__(
        self,
        mysql: MySQLStore | None = None,
        rabbitmq: RabbitMQClient | None = None,
        poll_interval: float = 1.0,
        batch_size: int = 10,
    ) -> None:
        self.mysql = mysql or MySQLStore()
        self.rabbitmq = rabbitmq or RabbitMQClient()
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self._running = False
        self._backoff = 0

    def drain_pending(self) -> int:
        """Publish all currently pending outbox rows. Returns count published."""
        rows = self.mysql.fetch_pending_outbox_rows(self.batch_size)
        published = 0
        for row in rows:
            try:
                self.rabbitmq.publish(
                    routing_key=row["routing_key"],
                    payload={
                        "event_id": f"outbox-{row['id']}",
                        "outbox_id": row["id"],
                        "job_id": row["aggregate_id"],
                        "event_type": row["event_type"],
                        "payload": row["payload"],
                        "created_at": None,  # filled by consumer
                    },
                )
                self.mysql.mark_outbox_published(row["id"])
                published += 1
                logger.info(
                    "Outbox published: id=%s job=%s event=%s",
                    row["id"], row["aggregate_id"], row["event_type"],
                )
            except Exception:
                logger.exception(
                    "Failed to publish outbox row id=%s, will retry", row["id"]
                )
                self._backoff = min(self._backoff * 2 + 1, self.MAX_BACKOFF)
                break
        else:
            self._backoff = 0  # all published successfully
        return published

    def run_forever(self) -> None:
        """Run the relay loop until stopped by signal."""
        self._running = True
        self.rabbitmq.ensure_topology()
        logger.info("OutboxRelay started (poll=%.1fs, batch=%d)", self.poll_interval, self.batch_size)

        while self._running:
            try:
                count = self.drain_pending()
                if count > 0:
                    logger.debug("Drained %d outbox rows", count)
            except Exception:
                logger.exception("OutboxRelay drain cycle error")

            sleep_time = max(self.poll_interval, self._backoff)
            time.sleep(sleep_time)

        logger.info("OutboxRelay stopped")

    def stop(self) -> None:
        """Signal the relay loop to stop after the current cycle."""
        self._running = False

    @classmethod
    def run_as_process(cls) -> None:
        """Entry point for running as a standalone process (python -m storage.outbox_relay)."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        )
        relay = cls()
        signal.signal(signal.SIGINT, lambda sig, frame: relay.stop())
        signal.signal(signal.SIGTERM, lambda sig, frame: relay.stop())
        relay.run_forever()


if __name__ == "__main__":
    OutboxRelay.run_as_process()
