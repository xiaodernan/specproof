"""Outbox Relay — polls MySQL outbox table and publishes to RabbitMQ.

Runs as a background thread or standalone process. Uses SELECT FOR UPDATE
SKIP LOCKED so multiple relay instances are safe.

§14.2 governance: each cycle claims one locked batch of due rows, marks a
row published only after the broker confirms, records failures with a
per-row next_retry_at deferral, and dead-letters rows that exceed
max_retries instead of retrying them forever. The six required relay
metrics (pending count, oldest event age, failure rate, retry count,
dead-letter count, last success ts) are exposed as gauges in
observability.metrics, so the process-local /metrics endpoint
(observability.metrics_http) serves them to Prometheus.
"""

import contextlib
import json
import logging
import os
import signal
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from contracts.events import build_envelope
from observability.logging import trace_id_var
from observability.metrics import incr, set_gauge
from storage.mysql import MySQLStore
from storage.rabbitmq import RabbitMQClient

logger = logging.getLogger(__name__)

#: §14.2 relay metric names — gauge/counter keys in the observability.metrics
#: registry (rendered as specproof_outbox_* by the /metrics endpoint).
METRIC_PENDING = "outbox_pending"
METRIC_OLDEST_AGE_SECONDS = "outbox_oldest_age_seconds"
METRIC_FAILURE_RATE = "outbox_failure_rate"
METRIC_RETRY_COUNT = "outbox_retry_count"
METRIC_DEAD_LETTERS = "outbox_dead_letters"
METRIC_LAST_SUCCESS_TS = "outbox_last_success_ts"
COUNTER_PUBLISHED = "outbox_published_total"
COUNTER_FAILED = "outbox_publish_failed_total"
COUNTER_DEAD_LETTERED = "outbox_dead_lettered_total"


class OutboxRelay:
    """Polls the outbox table and publishes events to RabbitMQ.

    Each cycle:
      1. SELECT ... FOR UPDATE SKIP LOCKED (due unpublished rows, oldest
         first; dead-lettered rows are excluded)
      2. For each row: publish to RabbitMQ with Publisher Confirm
      3. On success: UPDATE published_at = NOW(3) — only after confirm
      4. On failure: record last_error and a next_retry_at deferral; rows
         past max_retries are dead-lettered instead of retried
      5. Exponential backoff between cycles while RabbitMQ is unreachable

    Duplicate publication is tolerated: consumers dedupe on the
    idempotency key — the relay never assumes exactly-once (§14.2).
    """

    MAX_BACKOFF = 60  # seconds
    DEFAULT_MAX_RETRIES = 5

    def __init__(
        self,
        mysql: MySQLStore | None = None,
        rabbitmq: RabbitMQClient | None = None,
        poll_interval: float = 1.0,
        batch_size: int = 10,
        max_retries: int = DEFAULT_MAX_RETRIES,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        self.mysql = mysql or MySQLStore()
        self.rabbitmq = rabbitmq or RabbitMQClient()
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self.max_retries = max_retries
        self._now = now_fn or time.time
        self._running = False
        self._backoff = 0
        # In-process attempt accounting for the failure-rate gauge.
        self._attempts = 0
        self._failures = 0
        self._last_success_ts = 0.0

    def failure_rate(self) -> float:
        """Failed fraction of all publish attempts in this relay process."""
        if self._attempts == 0:
            return 0.0
        return self._failures / self._attempts

    def drain_pending(self) -> int:
        """Publish the current locked batch of due outbox rows. Returns count published."""
        rows = self.mysql.fetch_pending_outbox_rows(self.batch_size)
        published = 0
        for row in rows:
            try:
                self.rabbitmq.publish(
                    routing_key=row["routing_key"],
                    payload=self._flatten_envelope(row),
                )
                # §14.2: mark published only AFTER the broker confirms — a
                # crash before this UPDATE only re-publishes, and consumers
                # dedupe on the idempotency key.
                self.mysql.mark_outbox_published(row["id"])
                published += 1
                self._attempts += 1
                self._last_success_ts = self._now()
                incr(COUNTER_PUBLISHED)
                set_gauge(METRIC_LAST_SUCCESS_TS, self._last_success_ts)
                logger.info(
                    "Outbox published: id=%s job=%s event=%s",
                    row["id"], row["aggregate_id"], row["event_type"],
                )
            except Exception as exc:
                self._attempts += 1
                self._failures += 1
                incr(COUNTER_FAILED)
                self._backoff = min(self._backoff * 2 + 1, self.MAX_BACKOFF)
                retries_after = int(row.get("retry_count", 0)) + 1
                self._record_failure(row["id"], retries_after, str(exc)[:1000])
                logger.exception(
                    "Failed to publish outbox row id=%s, will retry", row["id"]
                )
                break
        else:
            self._backoff = 0  # every claimed row published successfully
        return published

    def _record_failure(self, outbox_id: int, retries_after: int, error: str) -> None:
        """Persist a failed attempt; dead-letter once past max_retries (§14.2)."""
        try:
            if retries_after > self.max_retries:
                self.mysql.dead_letter_outbox_row(outbox_id, error)
                incr(COUNTER_DEAD_LETTERED)
                logger.error(
                    "Outbox row id=%s dead-lettered after %d failed attempts: %s",
                    outbox_id, retries_after, error,
                )
            else:
                self.mysql.mark_outbox_failed(outbox_id, error, self._backoff)
        except Exception:
            logger.exception(
                "Failed to persist outbox failure state for id=%s", outbox_id
            )

    def refresh_metrics(self) -> None:
        """Compute the §14.2 relay metrics from the outbox table and publish
        them as gauges in the observability.metrics registry."""
        stats = self.mysql.outbox_stats()
        set_gauge(METRIC_PENDING, float(stats.get("pending") or 0))
        set_gauge(METRIC_DEAD_LETTERS, float(stats.get("dead_letters") or 0))
        set_gauge(METRIC_RETRY_COUNT, float(stats.get("retries") or 0))
        set_gauge(
            METRIC_OLDEST_AGE_SECONDS,
            self._oldest_age_seconds(stats.get("oldest_created_at")),
        )
        set_gauge(METRIC_FAILURE_RATE, self.failure_rate())
        last_success = self._to_epoch(stats.get("last_success"))
        set_gauge(
            METRIC_LAST_SUCCESS_TS,
            last_success if last_success is not None else self._last_success_ts,
        )

    @staticmethod
    def _to_epoch(value: Any) -> float | None:
        """Normalize a persisted timestamp (datetime or epoch float) to epoch."""
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=UTC).timestamp()
            return value.timestamp()
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
        return None

    def _oldest_age_seconds(self, created_at: Any) -> float:
        epoch = self._to_epoch(created_at)
        if epoch is None:
            return 0.0
        return max(0.0, self._now() - epoch)

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
            "OutboxRelay started (poll=%.1fs, batch=%d, max_retries=%d)",
            self.poll_interval, self.batch_size, self.max_retries,
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
                self.refresh_metrics()
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
