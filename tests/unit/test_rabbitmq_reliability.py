"""Unit tests for P1.3 RabbitMQ reliability patterns."""

import pytest

from storage.rabbitmq import (
    PermanentFailureError,
    QueueSpec,
    TemporaryFailureError,
)


class TestQueueSpec:
    def test_defaults(self) -> None:
        spec = QueueSpec(name="q.test")
        assert spec.name == "q.test"
        assert spec.dlq_name == ""
        assert spec.max_retries == 3
        assert spec.retry_delays_ms == [1000, 5000, 30000]

    def test_full_spec(self) -> None:
        spec = QueueSpec(
            name="q.p1.verify.job",
            dlq_name="q.p1.verify.job.dlq",
            retry_name="q.p1.verify.job.retry",
            max_retries=5,
            retry_delays_ms=[500, 2000, 10000, 30000, 60000],
        )
        assert spec.dlq_name == "q.p1.verify.job.dlq"
        assert spec.retry_name == "q.p1.verify.job.retry"
        assert spec.max_retries == 5
        assert len(spec.retry_delays_ms) == 5


class TestReliabilityExceptions:
    def test_temporary_failure_chain(self) -> None:
        with pytest.raises(TemporaryFailureError):
            raise TemporaryFailureError("transient connection loss")

    def test_permanent_failure_chain(self) -> None:
        with pytest.raises(PermanentFailureError):
            raise PermanentFailureError("invalid payload schema")

    def test_exceptions_are_distinct(self) -> None:
        te = TemporaryFailureError("retry")
        pe = PermanentFailureError("dead")
        assert not isinstance(te, PermanentFailureError)
        assert not isinstance(pe, TemporaryFailureError)
