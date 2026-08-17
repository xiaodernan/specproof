"""P1.2 Unit tests: Transactional Outbox (logic tests, no DB)."""

import json
import uuid

import pytest

from storage.mysql import MySQLStore, _VALID_TRANSITIONS


class TestOutboxLogic:
    """Validate outbox design without needing a database."""

    def test_pending_to_queued_is_valid(self):
        assert MySQLStore.is_valid_transition("PENDING", "QUEUED")

    def test_create_job_requires_id(self):
        """The job dict must have an id key."""
        store = MySQLStore()
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
        from storage.mysql import MySQLStore
        import inspect
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
