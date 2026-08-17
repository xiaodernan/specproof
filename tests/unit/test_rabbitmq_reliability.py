"""P1.3 Unit tests: RabbitMQ reliability (logic tests, no broker needed)."""

import json

import pytest

from storage.rabbitmq import (
    PermanentFailure,
    PublisherConfirmTimeout,
    QueuePolicy,
    RabbitMQClient,
    RabbitMQConfig,
    _get_death_count,
    make_idempotency_check,
)


class TestQueuePolicy:
    def test_default_policy(self):
        p = QueuePolicy()
        assert p.max_retries == 3
        assert p.retry_delays_ms == [1000, 5000, 30000]
        assert p.dlq_suffix == ".dlq"
        assert p.retry_suffix == ".retry"

    def test_custom_policy(self):
        p = QueuePolicy(max_retries=5, retry_delays_ms=[500, 2000])
        assert p.max_retries == 5


class TestRabbitMQConfig:
    def test_defaults(self):
        c = RabbitMQConfig()
        assert c.host == "localhost"
        assert c.port == 5672
        assert c.user == "specproof"

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("RABBITMQ_HOST", "broker.local")
        monkeypatch.setenv("RABBITMQ_PORT", "5673")
        c = RabbitMQConfig.from_env()
        assert c.host == "broker.local"
        assert c.port == 5673


class TestIdempotency:
    def test_first_call_is_not_duplicate(self, monkeypatch):
        """SETNX returns True (new key) → is_duplicate returns False."""
        class FakeRedis:
            def set(self, key, value, nx=False, ex=None):
                return True  # new key
        class FakeStore:
            client = FakeRedis()

        check = make_idempotency_check(FakeStore())
        assert not check("event-001")

    def test_second_call_is_duplicate(self, monkeypatch):
        """SETNX returns False (key exists) → is_duplicate returns True."""
        calls = [True, False]
        class FakeRedis:
            def set(self, key, value, nx=False, ex=None):
                return calls.pop(0) if calls else False
        class FakeStore:
            client = FakeRedis()

        check = make_idempotency_check(FakeStore())
        assert not check("event-001")  # first call
        assert check("event-001")      # duplicate

    def test_different_event_ids_are_not_duplicates(self, monkeypatch):
        class FakeRedis:
            def set(self, key, value, nx=False, ex=None):
                return True  # always new
        class FakeStore:
            client = FakeRedis()

        check = make_idempotency_check(FakeStore())
        assert not check("event-001")
        assert not check("event-002")
        assert not check("event-003")


class TestDeathCount:
    def test_no_headers(self):
        class FakeProps:
            headers = None
        assert _get_death_count(FakeProps()) == 0

    def test_empty_headers(self):
        class FakeProps:
            headers = {}
        assert _get_death_count(FakeProps()) == 0

    def test_no_death_array(self):
        class FakeProps:
            headers = {"other": True}
        assert _get_death_count(FakeProps()) == 0

    def test_single_death(self):
        class FakeProps:
            headers = {"x-death": [{"count": 1, "reason": "expired"}]}
        assert _get_death_count(FakeProps()) == 1

    def test_multiple_deaths(self):
        class FakeProps:
            headers = {"x-death": [
                {"count": 1, "reason": "expired"},
                {"count": 2, "reason": "rejected"},
            ]}
        assert _get_death_count(FakeProps()) == 3


class TestMessageSchema:
    def test_valid_job_created_message(self):
        msg = {
            "event_id": "outbox-42",
            "outbox_id": 42,
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "event_type": "JobCreated",
            "payload": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "repo_path": "/test/repo",
                "base_ref": "base",
                "head_ref": "head",
                "spec_path": "/test/spec.md",
                "depth": "FAST",
            },
            "created_at": "2026-07-10T12:00:00Z",
        }
        serialized = json.dumps(msg)
        deserialized = json.loads(serialized)
        assert deserialized["event_id"] == "outbox-42"
        assert deserialized["outbox_id"] == 42
        assert "trace_context" not in deserialized  # optional in P1.3
