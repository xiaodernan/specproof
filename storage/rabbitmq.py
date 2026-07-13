"""RabbitMQ client — P1.3 reliable pipeline with DLQ, retry, and idempotency.

P0.5: exchange + 4 queues with Publisher Confirm, Manual Ack
P1.3: DLQ topology, retry-queue with TTL delays, Nack routing,
      idempotency via MySQL processed_events, trace context propagation
"""

import json
import logging
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.exceptions import (
    ChannelClosedByBroker,
    ConnectionClosedByBroker,
    UnroutableError,
)

logger = logging.getLogger(__name__)


@dataclass
class RabbitMQConfig:
    host: str = "localhost"
    port: int = 5672
    user: str = "specproof"
    password: str = "specproof_pass"
    vhost: str = "/"
    publisher_retries: int = 3
    publisher_retry_delay_ms: int = 500

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
class QueueSpec:
    """P1.3 queue definition with DLQ and retry topology."""

    name: str
    dlq_name: str = ""
    retry_name: str = ""
    max_retries: int = 3
    retry_delays_ms: list[int] = field(default_factory=lambda: [1000, 5000, 30000])


class RabbitMQClient:
    """Reliable task pipeline with DLQ, retry-queue, and manual idempotency."""

    EXCHANGE = "specproof.phase0.commands"
    P1_EXCHANGE = "specproof.p1.commands"

    P0_QUEUES = [
        "q.phase0.contract.compile",
        "q.phase0.static.scan",
        "q.phase0.differential.run",
        "q.phase0.finding.replay",
    ]

    P1_QUEUES: list[QueueSpec] = [
        QueueSpec(
            name="q.p1.verify.job",
            dlq_name="q.p1.verify.job.dlq",
            retry_name="q.p1.verify.job.retry",
        ),
        QueueSpec(
            name="q.p1.verify.outbox",
            dlq_name="q.p1.verify.outbox.dlq",
            retry_name="q.p1.verify.outbox.retry",
        ),
    ]

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
        )
        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()
        self._channel.confirm_delivery()

    # ── P0.5 topology (backward-compatible) ───────────────────────

    def ensure_topology(self) -> None:
        if not self._channel:
            self._connect()
        ch = self._channel
        assert ch is not None
        ch.exchange_declare(exchange=self.EXCHANGE, exchange_type="direct", durable=True)
        for queue in self.P0_QUEUES:
            ch.queue_declare(queue=queue, durable=True)
            ch.queue_bind(exchange=self.EXCHANGE, queue=queue, routing_key=queue)

    # ── P1.3 topology with DLQ ────────────────────────────────────

    def ensure_p1_topology(self) -> None:
        """Declare P1 exchange + queues with DLQ and retry-queue topology."""
        if not self._channel:
            self._connect()
        ch = self._channel
        assert ch is not None

        ch.exchange_declare(exchange=self.P1_EXCHANGE, exchange_type="direct", durable=True)

        for spec in self.P1_QUEUES:
            dlq_args: dict[str, Any] = {}
            if spec.dlq_name:
                ch.queue_declare(queue=spec.dlq_name, durable=True)
                dlq_args["x-dead-letter-exchange"] = ""
                dlq_args["x-dead-letter-routing-key"] = spec.dlq_name

            ch.queue_declare(queue=spec.name, durable=True, arguments=dlq_args)
            ch.queue_bind(exchange=self.P1_EXCHANGE, queue=spec.name, routing_key=spec.name)

            if spec.dlq_name:
                ch.queue_bind(
                    exchange=self.P1_EXCHANGE,
                    queue=spec.dlq_name,
                    routing_key=spec.dlq_name,
                )

            if spec.retry_name:
                retry_args: dict[str, Any] = {
                    "x-dead-letter-exchange": self.P1_EXCHANGE,
                    "x-dead-letter-routing-key": spec.name,
                    "x-message-ttl": spec.retry_delays_ms[0],
                }
                ch.queue_declare(queue=spec.retry_name, durable=True, arguments=retry_args)
                ch.queue_bind(
                    exchange=self.P1_EXCHANGE,
                    queue=spec.retry_name,
                    routing_key=spec.retry_name,
                )

    # ── Publish ───────────────────────────────────────────────────

    def publish(self, routing_key: str, payload: dict[str, Any]) -> None:
        """P0.5 publish: basic persistent publish with confirm."""
        if not self._channel:
            self._connect()
        assert self._channel is not None
        self._channel.basic_publish(
            exchange=self.EXCHANGE,
            routing_key=routing_key,
            body=json.dumps(payload),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
            ),
        )

    def publish_with_confirm(
        self,
        routing_key: str,
        payload: dict[str, Any],
        *,
        exchange: str | None = None,
    ) -> bool:
        """Publish and wait for broker confirm. Retries on failure.

        Returns True if confirmed, raises on permanent failure.
        """
        if not self._channel:
            self._connect()
        assert self._channel is not None

        ex = exchange or self.P1_EXCHANGE

        for attempt in range(1, self.config.publisher_retries + 1):
            try:
                self._channel.basic_publish(
                    exchange=ex,
                    routing_key=routing_key,
                    body=json.dumps(payload),
                    properties=pika.BasicProperties(
                        delivery_mode=2,
                        content_type="application/json",
                        message_id=payload.get("event_id", str(uuid.uuid4())),
                    ),
                    mandatory=True,
                )
                return True
            except (UnroutableError, ConnectionClosedByBroker, ChannelClosedByBroker):
                logger.warning(
                    "Publish attempt %d/%d failed for %s",
                    attempt, self.config.publisher_retries, routing_key,
                )
                if attempt == self.config.publisher_retries:
                    raise
                import time
                time.sleep(self.config.publisher_retry_delay_ms / 1000 * attempt)
                self._connect()
        return False

    # ── Consume (P0.5 backward-compatible) ────────────────────────

    def consume(self, queue: str, callback: Callable[[dict[str, Any]], None]) -> None:
        if not self._channel:
            self._connect()

        def _on_message(
            ch: BlockingChannel,
            method: Any,
            properties: Any,
            body: bytes,
        ) -> None:
            try:
                payload = json.loads(body)
                callback(payload)
                ch.basic_ack(delivery_tag=method.delivery_tag)
            except Exception:
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

        assert self._channel is not None
        self._channel.basic_qos(prefetch_count=1)
        self._channel.basic_consume(queue=queue, on_message_callback=_on_message)

    # ── P1.3 consume with DLQ and idempotency ─────────────────────

    def consume_with_dlq(
        self,
        queue_spec: QueueSpec,
        callback: Callable[[dict[str, Any]], None],
        *,
        idempotency_check: Callable[[str, str], bool] | None = None,
        idempotency_mark: Callable[[str, str], None] | None = None,
        consumer_name: str = "worker-1",
    ) -> None:
        """Consume with DLQ routing, retry, and idempotency.

        Flow:
        - Check idempotency → duplicate → Ack (discard)
        - callback success → Ack
        - callback temporary failure → Nack → retry-queue (TTL delay)
        - callback permanent failure → Nack → DLQ

        idempotency_check(consumer_name, event_id) → bool
        idempotency_mark(consumer_name, event_id) → None
        """
        if not self._channel:
            self._connect()

        def _on_message(
            ch: BlockingChannel,
            method: Any,
            properties: Any,
            body: bytes,
        ) -> None:
            delivery_tag = method.delivery_tag
            try:
                payload = json.loads(body)
                event_id = payload.get("event_id", "")

                if idempotency_check and idempotency_check(consumer_name, event_id):
                    logger.debug("Duplicate event %s, discarding", event_id)
                    ch.basic_ack(delivery_tag=delivery_tag)
                    return

                # Read retry count from headers
                headers = properties.headers or {}
                retry_count = headers.get("x-retry-count", 0)

                try:
                    callback(payload)
                    if idempotency_mark:
                        idempotency_mark(consumer_name, event_id)
                    ch.basic_ack(delivery_tag=delivery_tag)
                except TemporaryFailureError:
                    if retry_count < queue_spec.max_retries:
                        delay = queue_spec.retry_delays_ms[
                            min(retry_count, len(queue_spec.retry_delays_ms) - 1)
                        ]
                        logger.info(
                            "Retry %d/%d for event %s, delay=%dms",
                            retry_count + 1, queue_spec.max_retries, event_id, delay,
                        )
                        ch.basic_publish(
                            exchange="",
                            routing_key=queue_spec.retry_name,
                            body=body,
                            properties=pika.BasicProperties(
                                delivery_mode=2,
                                content_type="application/json",
                                headers={"x-retry-count": retry_count + 1},
                                expiration=str(delay),
                            ),
                        )
                        ch.basic_ack(delivery_tag=delivery_tag)
                    else:
                        logger.error(
                            "Max retries (%d) exceeded for event %s, sending to DLQ",
                            queue_spec.max_retries, event_id,
                        )
                        if queue_spec.dlq_name:
                            ch.basic_publish(
                                exchange="",
                                routing_key=queue_spec.dlq_name,
                                body=body,
                                properties=pika.BasicProperties(
                                    delivery_mode=2,
                                    content_type="application/json",
                                    headers={
                                        "x-retry-count": retry_count,
                                        "x-original-queue": queue_spec.name,
                                        "x-failed-reason": "max_retries_exceeded",
                                    },
                                ),
                            )
                        ch.basic_ack(delivery_tag=delivery_tag)
                except PermanentFailureError as e:
                    logger.error(
                        "Permanent failure for event %s: %s, sending to DLQ", event_id, e,
                    )
                    if queue_spec.dlq_name:
                        ch.basic_publish(
                            exchange="",
                            routing_key=queue_spec.dlq_name,
                            body=body,
                            properties=pika.BasicProperties(
                                delivery_mode=2,
                                content_type="application/json",
                                headers={
                                    "x-original-queue": queue_spec.name,
                                    "x-failed-reason": str(e)[:255],
                                },
                            ),
                        )
                    ch.basic_ack(delivery_tag=delivery_tag)
            except Exception:
                ch.basic_nack(delivery_tag=delivery_tag, requeue=False)

        assert self._channel is not None
        self._channel.basic_qos(prefetch_count=1)
        self._channel.basic_consume(
            queue=queue_spec.name, on_message_callback=_on_message,
        )

    def start_consuming(self) -> None:
        if self._channel:
            self._channel.start_consuming()

    def is_ready(self) -> bool:
        try:
            if not self._connection or self._connection.is_closed:
                self._connect()
            return self._connection is not None and self._connection.is_open
        except Exception:
            return False

    def close(self) -> None:
        if self._channel and self._channel.is_open:
            self._channel.close()
        if self._connection and self._connection.is_open:
            self._connection.close()


class TemporaryFailureError(Exception):
    """Retryable error — Nack with retry-queue routing."""


class PermanentFailureError(Exception):
    """Non-retryable error — Nack with DLQ routing."""
