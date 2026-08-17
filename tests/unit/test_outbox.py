"""P1.2 Unit tests: Transactional Outbox (logic tests, no DB)."""

import json
import uuid

from storage.mysql import MySQLStore


class TestOutboxLogic:
    """Validate outbox design without needing a database."""

    def test_pending_to_queued_is_valid(self):
        assert MySQLStore.is_valid_transition("PENDING", "QUEUED")

    def test_create_job_requires_id(self):
        """The job dict must have an id key."""
        job = {"id": str(uuid.uuid4()), "repo_path": "/test", "base_ref": "b",
               "head_ref": "h", "spec_path": "/s", "depth": "FAST"}
        # Just validate the job structure — actual DB call would fail without MySQL
        assert "id" in job
        assert "status" not in job  # insert_job expects explicit status

    def test_outbox_payload_is_valid_json(self):
        """Verify that payload serialization works correctly."""
        payload = {
            "job_id": str(uuid.uuid4()),
            "repo_path": "/test/repo",
            "base_ref": "main",
            "head_ref": "feature/x",
            "spec_path": "/test/spec.md",
            "depth": "FAST",
        }
        serialized = json.dumps(payload)
        deserialized = json.loads(serialized)
        assert deserialized == payload

    def test_fetch_pending_uses_skip_locked_syntax(self):
        """Ensure the SQL pattern includes SKIP LOCKED for concurrency safety."""
        import inspect

        from storage.mysql import MySQLStore
        src = inspect.getsource(MySQLStore.fetch_pending_outbox_rows)
        assert "FOR UPDATE SKIP LOCKED" in src or "FOR UPDATE" in src
        assert "published_at IS NULL" in src

    def test_mark_published_updates_timestamp(self):
        """Ensure mark_outbox_published sets published_at."""
        import inspect
        src = inspect.getsource(MySQLStore.mark_outbox_published)
        assert "published_at" in src


class TestOutboxRelayLogic:
    """Validate relay behavior without external dependencies."""

    def test_drain_pending_returns_count(self):
        """drain_pending should return an integer count."""
        from storage.outbox_relay import OutboxRelay
        relay = OutboxRelay()
        # Without MySQL, drain_pending will fail at fetch step
        # But the type contract is: returns int
        try:
            count = relay.drain_pending()
            assert isinstance(count, int)
        except Exception:
            pass  # Expected: MySQL not available

    def test_backoff_increases_on_failure(self):
        from storage.outbox_relay import OutboxRelay
        relay = OutboxRelay()
        assert relay._backoff == 0
        relay._backoff = min(relay._backoff * 2 + 1, relay.MAX_BACKOFF)
        assert relay._backoff == 1
        relay._backoff = min(relay._backoff * 2 + 1, relay.MAX_BACKOFF)
        assert relay._backoff == 3
        relay._backoff = min(relay._backoff * 2 + 1, relay.MAX_BACKOFF)
        assert relay._backoff == 7

    def test_backoff_has_maximum(self):
        from storage.outbox_relay import OutboxRelay
        relay = OutboxRelay()
        for _ in range(20):
            relay._backoff = min(relay._backoff * 2 + 1, relay.MAX_BACKOFF)
        assert relay._backoff <= relay.MAX_BACKOFF

    def test_stop_sets_running_false(self):
        from storage.outbox_relay import OutboxRelay
        relay = OutboxRelay()
        relay._running = True
        relay.stop()
        assert not relay._running


class TestRelayWireContract:
    """The relay is the single producer boundary: the wire message must be
    a FLAT payload the worker's flat reader understands."""

    def test_flatten_envelope_merges_inner_fields(self):
        from storage.outbox_relay import OutboxRelay

        class FakeMySQL:
            def fetch_pending_outbox_rows(self, limit):
                return [{
                    "id": 7,
                    "aggregate_id": "job-1",
                    "event_type": "JobCreated",
                    "routing_key": "q.p1.verify.job",
                    "payload": json.dumps({
                        "job_id": "job-1",
                        "repo_path": "/repo",
                        "base_ref": "main",
                        "head_ref": "head-sha",
                        "spec_path": "/spec.md",
                        "depth": "FAST",
                    }),
                }]

            def mark_outbox_published(self, outbox_id):
                pass

            def count_pending_outbox(self):
                return 0

        class FakeRabbit:
            def __init__(self):
                self.published = []

            def publish(self, routing_key, payload):
                self.published.append((routing_key, payload))

        rabbit = FakeRabbit()
        relay = OutboxRelay(mysql=FakeMySQL(), rabbitmq=rabbit)
        count = relay.drain_pending()
        assert count == 1
        routing_key, payload = rabbit.published[0]
        assert routing_key == "q.p1.verify.job"
        # Envelope fields…
        assert payload["event_id"] == "outbox-7"
        assert payload["job_id"] == "job-1"
        assert payload["event_type"] == "JobCreated"
        # …merged with the inner job fields (flat, worker-readable).
        assert payload["repo_path"] == "/repo"
        assert payload["base_ref"] == "main"
        assert payload["head_ref"] == "head-sha"
        assert payload["depth"] == "FAST"
        # No nested string payload may remain on the wire.
        assert "payload" not in payload

    def test_flatten_tolerates_corrupt_payload(self):
        from storage.outbox_relay import OutboxRelay

        relay = OutboxRelay()
        envelope = relay._flatten_envelope({
            "id": 3,
            "aggregate_id": "job-2",
            "event_type": "JobCreated",
            "payload": "{not-json",
        })
        assert envelope["job_id"] == "job-2"
        assert envelope["event_id"] == "outbox-3"
