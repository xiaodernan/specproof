"""Worker consumer — main loop for consuming verification jobs from RabbitMQ.

P1.3: Uses Manual Ack, DLQ, retry, and Redis idempotency.
"""

import logging
import signal
import sys
from pathlib import Path

# Ensure project root on path
_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from storage.rabbitmq import (
    RabbitMQClient,
    make_idempotency_check,
)
from storage.redis import RedisStore

logger = logging.getLogger(__name__)


class JobConsumer:
    """Consumes verification job messages and executes the LangGraph pipeline."""

    def __init__(
        self,
        rabbitmq: RabbitMQClient | None = None,
        redis: RedisStore | None = None,
    ) -> None:
        self.rabbitmq = rabbitmq or RabbitMQClient()
        self.redis = redis or RedisStore()
        self._running = False

    def handle_job_created(self, payload: dict) -> None:
        """Process a JobCreated event."""
        job_id = payload.get("job_id", "unknown")
        event_id = payload.get("event_id", "unknown")
        logger.info("Received job: %s (event: %s)", job_id, event_id)

        # TODO(P1.6): Execute LangGraph pipeline with checkpoint
        # For now (P1.3), validate the message flow is correct
        logger.info("Job %s processed successfully", job_id)

    def start(self) -> None:
        """Start consuming from the verify job queue."""
        self._running = True
        self.rabbitmq.ensure_topology()

        idempotency = make_idempotency_check(self.redis)

        logger.info("JobConsumer starting on queue: %s", RabbitMQClient.QUEUE_VERIFY_JOB)
        self.rabbitmq.consume_with_policy(
            queue=RabbitMQClient.QUEUE_VERIFY_JOB,
            callback=self.handle_job_created,
            idempotency_fn=idempotency,
        )

        try:
            self.rabbitmq.start_consuming()
        except KeyboardInterrupt:
            logger.info("JobConsumer interrupted")
        finally:
            self.rabbitmq.close()
            self.redis.close()

    def stop(self) -> None:
        self._running = False
        self.rabbitmq.close()
        self.redis.close()


def main() -> None:
    """Entry point: python -m storage.consumer"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    consumer = JobConsumer()
    signal.signal(signal.SIGINT, lambda sig, frame: consumer.stop())
    signal.signal(signal.SIGTERM, lambda sig, frame: consumer.stop())
    consumer.start()


if __name__ == "__main__":
    main()
