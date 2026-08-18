"""Outbox Relay — polls MySQL outbox table and publishes to RabbitMQ.

Runs as a background thread or standalone process. Uses SELECT FOR UPDATE
SKIP LOCKED so multiple relay instances are safe.
"""

import contextlib
import json
import logging
import os
import signal
import time
from typing import Any

from contracts.events import build_envelope
from observability.logging import trace_id_var
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
                    payload=self._flatten_envelope(row),
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

    def _flatten_envelope(self, row: dict[str, Any]) -> dict[str, Any]:
        """Build the wire message for one outbox row via the §3.4 envelope.

        The consumer contract is a FLAT payload: the canonical envelope
        fields (event_id, event_type, occurred_at, tenant_id, actor_id,
        trace_id, aggregate_type, aggregate_id, schema_version,
        idempotency_key, payload_digest) are merged with the inner job
        fields (repo_path, base_ref, head_ref, spec_path, depth). The
        nested `payload` key is flattened away — the old nested-string form
        never reached the worker's flat reader, and legacy consumers keep
        reading the same flat keys while ignoring the new envelope fields.

        Backward compatibility: event_id keeps the legacy deterministic
        ``outbox-{id}`` format and created_at stays a None placeholder for
        the consumer. Envelope metadata is written AFTER the payload spread,
        so payload content can never spoof event_id/schema_version/digest.
        """
        try:
            inner = json.loads(row["payload"])
        except (TypeError, ValueError):
            inner = {}
        inner = inner if isinstance(inner, dict) else {}

        envelope = build_envelope(
            event_type=row["event_type"],
            aggregate_id=row["aggregate_id"],
            payload=inner,
            # Legacy deterministic id kept for wire compatibility with
            # existing consumers/tests; new producers default to uuid4 hex.
            event_id=f"outbox-{row['id']}",
            trace_id=trace_id_var.get(),
            idempotency_key=f"outbox:{row['id']}",
        )
        flat: dict[str, Any] = {}
        flat.update(envelope["payload"])  # inner job fields (secret-redacted)
        flat.update({
            "event_id": envelope["event_id"],
            "outbox_id": row["id"],
            "job_id": row["aggregate_id"],
            "event_type": envelope["event_type"],
            "created_at": None,  # legacy field; filled by the consumer
            "occurred_at": envelope["occurred_at"],
            "tenant_id": envelope["tenant_id"],
            "actor_id": envelope["actor_id"],
            "trace_id": envelope["trace_id"],
            "aggregate_type": envelope["aggregate_type"],
            "aggregate_id": envelope["aggregate_id"],
            "schema_version": envelope["schema_version"],
            "idempotency_key": envelope["idempotency_key"],
            "payload_digest": envelope["payload_digest"],
        })
        return flat

    def run_forever(self) -> None:
        """Run the relay loop until stopped by signal."""
        self._running = True
        self.rabbitmq.ensure_topology()

        # P6: 进程内 /metrics (Prometheus 抓取目标 outbox-relay:9101),
        # 暴露 specproof_outbox_pending 积压 gauge。
        from observability.metrics_http import serve_metrics_in_thread

        serve_metrics_in_thread(
            port=int(os.getenv("OUTBOX_RELAY_METRICS_PORT", "9101"))
        )
        logger.info(
            "OutboxRelay started (poll=%.1fs, batch=%d)",
            self.poll_interval, self.batch_size,
        )

        while self._running:
            try:
                count = self.drain_pending()
                if count > 0:
                    logger.debug("Drained %d outbox rows", count)
            except Exception:
                logger.exception("OutboxRelay drain cycle error")

            sleep_time = max(self.poll_interval, self._backoff)
            with contextlib.suppress(Exception):
                from observability.metrics import set_gauge

                set_gauge("outbox_pending", float(self.mysql.count_pending_outbox()))
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
