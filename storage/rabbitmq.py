"""RabbitMQ client — reliable task pipeline for Phase 0/1.

P1.3: Added DLQ, retry-queue with TTL backoff, Publisher Confirm retries,
and Redis-based message idempotency.
"""

import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.exceptions import (
    AMQPChannelError,
    AMQPConnectionError,
    NackError,
    UnroutableError,
)

logger = logging.getLogger(__name__)


class PublisherConfirmTimeout(Exception):
    """Raised when Publisher Confirm is not received within the timeout."""


class PermanentFailure(Exception):
    """Raised when a message should be sent to DLQ (non-retryable)."""


# ── Configuration ──────────────────────────────────────────────


@dataclass
class RabbitMQConfig:
    host: str = "localhost"
    port: int = 5672
    user: str = "specproof"
    password: str = "specproof_pass"
    vhost: str = "/"

    @classmethod
    def from_env(cls) -> "RabbitMQConfig":
        return cls(
            host=os.getenv("RABBITMQ_HOST", "localhost"),
            port=int(os.getenv("RABBITMQ_PORT", "5672")),
            user=os.getenv("RABBITMQ_USER", "specproof"),
            password=os.getenv("RABBITMQ_PASSWORD", "specproof_pass"),
            vhost="/",
        )


@dataclass
class QueuePolicy:
    """Per-queue reliability policy."""
    max_retries: int = 3
    retry_delays_ms: list[int] = field(default_factory=lambda: [1000, 5000, 30000])
    dlq_suffix: str = ".dlq"
    retry_suffix: str = ".retry"


# ── Client ─────────────────────────────────────────────────────


class RabbitMQClient:
    """Reliable task pipeline with Publisher Confirm, Manual Ack, DLQ, and retry."""

    EXCHANGE_P0 = "specproof.phase0.commands"
    EXCHANGE_P1 = "specproof.p1.commands"

    # Primary queue with its DLQ and retry-queue
    QUEUE_VERIFY_JOB = "q.p1.verify.job"

    def __init__(self, config: RabbitMQConfig | None = None) -> None:
        self.config = config or RabbitMQConfig.from_env()
        self._connection: pika.BlockingConnection | None = None
        self._channel: BlockingChannel | None = None

    def _connect(self) -> None:
        credentials = pika.PlainCredentials(self.config.user, self.config.password)
        params = pika.ConnectionParameters(
            host=self.config.host,
            port=self.config.port,
            virtual_host=self.config.vhost,
            credentials=credentials,
            heartbeat=30,
            blocked_connection_timeout=30,
            connection_attempts=3,
            retry_delay=2,
        )
        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()
        self._channel.confirm_delivery()

    @property
    def channel(self) -> BlockingChannel:
        if self._channel is None or self._channel.is_closed:
            self._connect()
        return self._channel

    # ── topology ──────────────────────────────────────────────

    def ensure_topology(self) -> None:
        """Declare exchanges, queues, DLQs, and retry-queues with bindings."""
        ch = self.channel

        # P1 exchange
        ch.exchange_declare(exchange=self.EXCHANGE_P1, exchange_type="direct", durable=True)

        for base_queue, policy in [
            (self.QUEUE_VERIFY_JOB, QueuePolicy()),
        ]:
            dlq = base_queue + policy.dlq_suffix
            retry_q = base_queue + policy.retry_suffix

            # DLQ: no TTL, holds permanently failed messages
            ch.queue_declare(queue=dlq, durable=True)
            ch.queue_bind(exchange=self.EXCHANGE_P1, queue=dlq, routing_key=dlq)

            # Retry queue: per-message TTL, dead-letter back to primary
            retry_args = {
                "x-dead-letter-exchange": self.EXCHANGE_P1,
                "x-dead-letter-routing-key": base_queue,
            }
            ch.queue_declare(queue=retry_q, durable=True, arguments=retry_args)
            ch.queue_bind(exchange=self.EXCHANGE_P1, queue=retry_q, routing_key=retry_q)

            # Primary queue: dead-letter to DLQ on rejection
            primary_args = {
                "x-dead-letter-exchange": self.EXCHANGE_P1,
                "x-dead-letter-routing-key": dlq,
            }
            ch.queue_declare(queue=base_queue, durable=True, arguments=primary_args)
            ch.queue_bind(exchange=self.EXCHANGE_P1, queue=base_queue, routing_key=base_queue)

        # Also ensure Phase 0 topology for backward compatibility
        ch.exchange_declare(exchange=self.EXCHANGE_P0, exchange_type="direct", durable=True)
        for q in ["q.phase0.contract.compile", "q.phase0.static.scan",
                   "q.phase0.differential.run", "q.phase0.finding.replay"]:
            ch.queue_declare(queue=q, durable=True)
            ch.queue_bind(exchange=self.EXCHANGE_P0, queue=q, routing_key=q)

    # ── publish ───────────────────────────────────────────────

    def publish_with_confirm(
        self,
        routing_key: str,
        payload: dict[str, Any],
        exchange: str | None = None,
        timeout: float = 10.0,
    ) -> bool:
        """Publish a persistent message and wait for broker confirm.

        Returns True on confirm, raises PublisherConfirmTimeout otherwise.
        """
        if exchange is None:
            exchange = self.EXCHANGE_P1
        ch = self.channel
        try:
            ch.basic_publish(
                exchange=exchange,
                routing_key=routing_key,
                body=json.dumps(payload),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type="application/json",
                ),
            )
            return True
        except (NackError, UnroutableError) as e:
            raise PublisherConfirmTimeout(
                f"Publisher confirm failed for {routing_key}: {e}"
            ) from e

    def publish(self, routing_key: str, payload: dict[str, Any],
                exchange: str | None = None) -> None:
        """Publish with confirm (backward-compatible signature)."""
        self.publish_with_confirm(routing_key, payload, exchange)

    # ── consume ───────────────────────────────────────────────

    def consume_with_policy(
        self,
        queue: str,
        callback: Callable[[dict[str, Any]], None],
        policy: QueuePolicy | None = None,
        idempotency_fn: Callable[[str], bool] | None = None,
    ) -> None:
        """Start consuming with Manual Ack, DLQ, retry, and idempotency.

        Args:
            queue: Queue name to consume from.
            callback: Called with the deserialized message payload.
            policy: Retry/DLQ policy for this queue.
            idempotency_fn: Called with event_id; returns True if duplicate.
        """
        if policy is None:
            policy = QueuePolicy()
        ch = self.channel
        dlq = queue + policy.dlq_suffix
        retry_q = queue + policy.retry_suffix

        def _on_message(ch, method, properties, body):
            delivery_tag = method.delivery_tag
            try:
                payload = json.loads(body)
                event_id = payload.get("event_id", "")

                # Idempotency check
                if idempotency_fn and event_id:
                    if idempotency_fn(event_id):
                        logger.debug("Duplicate message %s, acking", event_id)
                        ch.basic_ack(delivery_tag=delivery_tag)
                        return

                # Process the message
                callback(payload)
                ch.basic_ack(delivery_tag=delivery_tag)

            except PermanentFailure:
                logger.warning("Permanent failure for %s, sending to DLQ", delivery_tag)
                ch.basic_reject(delivery_tag=delivery_tag, requeue=False)

            except Exception:
                # Determine retry count from death header
                death_count = _get_death_count(properties)
                if death_count < policy.max_retries:
                    delay = policy.retry_delays_ms[min(death_count, len(policy.retry_delays_ms) - 1)]
                    logger.info(
                        "Temporary failure, retry %d/%d in %dms",
                        death_count + 1, policy.max_retries, delay,
                    )
                    # Publish to retry queue with per-message TTL
                    ch.basic_publish(
                        exchange=self.EXCHANGE_P1,
                        routing_key=retry_q,
                        body=body,
                        properties=pika.BasicProperties(
                            delivery_mode=2,
                            content_type="application/json",
                            expiration=str(delay),
                        ),
                    )
                    ch.basic_ack(delivery_tag=delivery_tag)
                else:
                    logger.error("Max retries (%d) exceeded, sending to DLQ", policy.max_retries)
                    ch.basic_reject(delivery_tag=delivery_tag, requeue=False)

        ch.basic_qos(prefetch_count=1)
        ch.basic_consume(queue=queue, on_message_callback=_on_message)

    def consume(self, queue: str, callback: Callable[[dict[str, Any]], None]) -> None:
        """Basic consume (backward-compatible, no DLQ/retry)."""
        ch = self.channel

        def _on_message(ch, method, properties, body):
            try:
                payload = json.loads(body)
                callback(payload)
                ch.basic_ack(delivery_tag=method.delivery_tag)
            except Exception:
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

        ch.basic_qos(prefetch_count=1)
        ch.basic_consume(queue=queue, on_message_callback=_on_message)

    def start_consuming(self) -> None:
        """Block and consume messages until interrupted."""
        try:
            self.channel.start_consuming()
        except (AMQPConnectionError, AMQPChannelError):
            logger.exception("Connection lost during consume")
        except KeyboardInterrupt:
            logger.info("Consumer interrupted")

    # ── health ────────────────────────────────────────────────

    def is_ready(self) -> bool:
        try:
            if self._connection is None or self._connection.is_closed:
                self._connect()
            return self._connection is not None and self._connection.is_open
        except Exception:
            return False

    def close(self) -> None:
        if self._channel and self._channel.is_open:
            self._channel.close()
        if self._connection and self._connection.is_open:
            self._connection.close()


# ── Redis idempotency helper ────────────────────────────────────


def make_idempotency_check(redis_store: Any) -> Callable[[str], bool]:
    """Create an idempotency check function backed by Redis SETNX.

    Args:
        redis_store: A RedisStore instance.

    Returns:
        A callable that takes an event_id and returns True if duplicate.
    """
    def check(event_id: str) -> bool:
        key = f"specproof:idempotent:{event_id}"
        # SETNX returns False if key already exists (duplicate)
        is_new = redis_store.client.set(key, "1", nx=True, ex=86400)
        return not is_new
    return check


# ── internal helpers ─────────────────────────────────────────────


def _get_death_count(properties: pika.BasicProperties) -> int:
    """Extract death count from message headers (x-death)."""
    if properties.headers is None:
        return 0
    deaths = properties.headers.get("x-death", [])
    if not deaths:
        return 0
    return sum(d.get("count", 1) for d in deaths)
