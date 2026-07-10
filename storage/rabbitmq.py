"""RabbitMQ client — reliable task pipeline for Phase 0."""

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pika
from pika.adapters.blocking_connection import BlockingChannel


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


class RabbitMQClient:
    """Reliable task pipeline with Publisher Confirm and Manual Ack."""

    EXCHANGE = "specproof.phase0.commands"
    QUEUES = [
        "q.phase0.contract.compile",
        "q.phase0.static.scan",
        "q.phase0.differential.run",
        "q.phase0.finding.replay",
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

    def ensure_topology(self) -> None:
        if not self._channel:
            self._connect()
        ch = self._channel
        ch.exchange_declare(exchange=self.EXCHANGE, exchange_type="direct", durable=True)
        for queue in self.QUEUES:
            ch.queue_declare(queue=queue, durable=True)
            ch.queue_bind(exchange=self.EXCHANGE, queue=queue, routing_key=queue)

    def publish(self, routing_key: str, payload: dict[str, Any]) -> None:
        if not self._channel:
            self._connect()
        self._channel.basic_publish(
            exchange=self.EXCHANGE,
            routing_key=routing_key,
            body=json.dumps(payload),
            properties=pika.BasicProperties(
                delivery_mode=2,  # persistent
                content_type="application/json",
            ),
        )

    def consume(self, queue: str, callback: Callable[[dict[str, Any]], None]) -> None:
        if not self._channel:
            self._connect()

        def _on_message(ch, method, properties, body):
            try:
                payload = json.loads(body)
                callback(payload)
                ch.basic_ack(delivery_tag=method.delivery_tag)
            except Exception:
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

        self._channel.basic_qos(prefetch_count=1)
        self._channel.basic_consume(queue=queue, on_message_callback=_on_message)

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
