"""P1.6 crash semantics — **models of the semantics**, plus the code-level legs.

Read this before trusting a green run here.

What this file is, leg by leg
-----------------------------
* ``TestCrashRecoveryScenarios`` (5 legs) — **MODELS**. They assert the
  *shape* of the crash semantics against local Python lists ("the nodes
  before the crash are ``all_nodes[:crash_index]``"). They cannot fail
  unless somebody edits this file; they are a written-down model of the
  intended behaviour, not evidence that the worker behaves that way.
* ``TestWorkerRecoveryStateMachine`` (3 legs) — these now call **production
  code**: the state machine's own ``is_valid_transition`` / ``is_terminal``
  and the lease renewal in ``storage/redis.py`` (driven by a fake client,
  because Redis itself is not the subject). If master changes the state
  machine or the lease rules, these legs change with it.
* ``TestMongoDBSaverInterface`` (3 legs) — the saver's **real code** against a
  fake Mongo driver (a document in, a ``CheckpointTuple`` out).

Where the real proof of "a crash survives" lives
-------------------------------------------------
The machinery that actually carries a crash across a process is
``agent/mongo_saver.py`` (a LangGraph ``BaseCheckpointSaver`` writing to
MongoDB) plus the resume loop in ``agent/worker.py``. That pair is exercised
end to end — real saver, real MongoDB, a fresh saver standing in for the
restarted worker — in
``tests/integration/test_worker_checkpoint_survives_a_crash.py``. Before that
file existed, this one implied in its docstring that it proved the recovery
machinery itself while asserting against lists; the claim was the problem, and
it is now stated instead of implied.

Still not covered here (and not pretended to be): the whole-graph resume
(re-entering nodes, not repeating side effects) — that needs a live worker
and a live broker, and it is still open in the P1-B queue.
"""

from __future__ import annotations

import uuid


def make_job_id():
    return f"test-worker-{uuid.uuid4().hex[:12]}"


class _EmptyWritesCursor:
    """Minimal pymongo-cursor stand-in: no pending writes for the fake."""

    def sort(self, *args: object) -> list[object]:
        return []


class TestCrashRecoveryScenarios:
    """MODEL — the intended crash semantics, written down.

    These are models, not evidence: each leg asserts against a local list.
    The evidence for the machinery is in
    ``tests/integration/test_worker_checkpoint_survives_a_crash.py``.
    """

    def test_checkpoint_saved_before_crash(self):
        """MODEL: when the worker crashes at node 7 (run_differential), the
        checkpoint at node 6 (run_static_checks) should already be persisted."""
        all_nodes = [
            "intake", "compile_contracts", "prepare_base", "prepare_head",
            "collect_diff", "run_static_checks",       # ← last checkpoint
            "generate_counterexamples", "run_differential",  # ← crash here
            "review_court", "build_matrix", "create_capsule", "publish_report",
        ]

        crash_node = "run_differential"
        crash_index = all_nodes.index(crash_node)
        completed = all_nodes[:crash_index]  # nodes before crash

        assert "run_static_checks" in completed
        assert "run_differential" not in completed

        # Recovery: remaining nodes after crash
        remaining = all_nodes[crash_index:]
        assert remaining[0] == "run_differential"
        assert len(remaining) == 5

    def test_crash_after_last_node_is_noop(self):
        """MODEL: if the crash happens after publish_report, no recovery is
        needed."""
        all_nodes = [
            "intake", "compile_contracts", "prepare_base", "prepare_head",
            "collect_diff", "run_static_checks", "generate_counterexamples",
            "run_differential", "review_court", "build_matrix",
            "create_capsule", "publish_report",
        ]
        final_index = len(all_nodes) - 1
        remaining = all_nodes[final_index + 1:]
        assert remaining == []

    def test_duplicate_message_idempotent(self):
        """MODEL: a redelivered message is not processed twice."""
        processed_events = set()

        def handle(event_id):
            if event_id in processed_events:
                return "duplicate"
            processed_events.add(event_id)
            return "processed"

        assert handle("evt-001") == "processed"
        assert handle("evt-001") == "duplicate"
        assert len(processed_events) == 1

    def test_recovery_preserves_state(self):
        """MODEL: after recovery, the intermediate state of earlier nodes is
        preserved."""
        state = {
            "repo_path": "/tmp/repo",
            "contracts": [{"id": "DIFF-01", "name": "auth"}],
            "static_findings": [{"severity": "HIGH"}],
            "diff_results": [],
        }

        # Crash saves state to checkpoint
        checkpoint = dict(state)

        # Recovery loads checkpoint
        recovered = dict(checkpoint)
        assert recovered["repo_path"] == "/tmp/repo"
        assert len(recovered["contracts"]) == 1
        assert len(recovered["static_findings"]) == 1

    def test_resume_skips_completed_nodes(self):
        """MODEL: on resume, the checkpointer skips the nodes already in the
        checkpoint."""
        completed_in_checkpoint = {
            "intake", "compile_contracts", "prepare_base", "prepare_head",
            "collect_diff", "run_static_checks",
        }
        all_nodes = [
            "intake", "compile_contracts", "prepare_base", "prepare_head",
            "collect_diff", "run_static_checks", "generate_counterexamples",
            "run_differential", "review_court", "build_matrix",
            "create_capsule", "publish_report",
        ]

        to_execute = [n for n in all_nodes if n not in completed_in_checkpoint]
        assert to_execute == [
            "generate_counterexamples", "run_differential",
            "review_court", "build_matrix", "create_capsule", "publish_report",
        ]
        assert len(to_execute) == 6


class TestWorkerRecoveryStateMachine:
    """The interaction of checkpoint recovery with the job state machine.

    MIXED, and stated so: two legs call the **PRODUCTION CODE** (the state
    machine's own ``is_valid_transition`` / ``is_terminal`` and the lease
    renewal in ``storage/redis.py``), one leg is a MODEL of the intended
    head-change shape. A change in the state machine or the lease rules moves
    the production legs — which is the whole point.
    """

    def test_stale_job_not_executed(self):
        """A STALE job cannot be moved on: the state machine says so.

        This is the production table (``storage/mysql.py``), not a local
        set — the earlier version of this leg asserted a literal against a
        literal, which could not fail.
        """
        from storage.mysql import ALL_STATUSES, MySQLStore

        assert MySQLStore.is_terminal("STALE") is True
        # From STALE there is no exit at all, so the worker cannot put a
        # superseded job back into an executable state.
        for status in ALL_STATUSES:
            assert MySQLStore.is_valid_transition("STALE", status) is False, (
                f"STALE became transitionable to {status!r}: a superseded job "
                "could be picked up again"
            )

    def test_running_job_lease_renewal(self):
        """A lease is renewed by its owner and by nobody else.

        Driven through ``storage/redis.py::renew_lease`` with a fake client
        (Redis is not the subject; the renewal rules are).
        """
        from storage.redis import RedisStore

        class _FakeRedis:
            def __init__(self) -> None:
                self.store: dict[str, str] = {}
                self.expired: list[tuple[str, int]] = []

            def get(self, key: str):
                return self.store.get(key)

            def exists(self, key: str) -> bool:
                return key in self.store

            def expire(self, key: str, ttl: int) -> bool:
                self.expired.append((key, ttl))
                return True

        store = RedisStore.__new__(RedisStore)  # skip __init__ (no Redis here)
        fake = _FakeRedis()
        store._client = fake  # noqa: SLF001 — the property has no setter

        job_id = "lease-job"
        key = store.lease_key(job_id)
        fake.store[key] = "worker-a"

        # The owner renews.
        assert store.renew_lease(job_id, "worker-a", ttl=30) is True
        assert fake.expired and fake.expired[-1][1] == 30

        # A stranger does not, and does not even touch the TTL.
        fake.expired.clear()
        assert store.renew_lease(job_id, "worker-b", ttl=30) is False
        assert fake.expired == []

    def test_worker_marks_stale_on_new_head(self):
        """MODEL: when a new Head SHA arrives, the in-flight jobs of the old
        head are the ones that go STALE.

        The production side of this is ``mark_stale_for_head`` (exercised
        against MySQL in the integration suite); this leg keeps the
        intended shape written down.
        """
        jobs = [
            {"id": "j-1", "head_ref": "head-v1", "status": "RUNNING"},
            {"id": "j-2", "head_ref": "head-v1", "status": "QUEUED"},
            {"id": "j-3", "head_ref": "head-v2", "status": "RUNNING"},
        ]
        new_head = "head-v2"

        stale = [
            j for j in jobs
            if j["head_ref"] != new_head and j["status"] in ("RUNNING", "QUEUED")
        ]
        assert len(stale) == 2
        assert {j["id"] for j in stale} == {"j-1", "j-2"}


class TestMongoDBSaverInterface:
    """PRODUCTION CODE — the saver's real code against a fake Mongo driver."""

    def test_get_tuple_returns_none_for_unknown_thread(self, monkeypatch):
        """get_tuple should return None when no checkpoint exists."""
        from agent.mongo_saver import MongoDBSaver

        class FakeStore:
            def ensure_collections(self):
                pass
            class db:
                class agent_checkpoints:
                    @staticmethod
                    def find_one(query, sort=None):
                        return None
                class checkpoint_writes:
                    @staticmethod
                    def find(query):
                        return _EmptyWritesCursor()

        saver = MongoDBSaver.__new__(MongoDBSaver)  # skip __init__
        saver._store = FakeStore()

        result = saver.get_tuple({"configurable": {"thread_id": "no-such-job"}})
        assert result is None

    def test_get_tuple_returns_checkpoint(self, monkeypatch):
        """get_tuple should return a CheckpointTuple when checkpoint exists."""
        from langgraph.checkpoint.base import CheckpointTuple

        from agent.mongo_saver import MongoDBSaver

        doc = {
            "thread_id": "job-1",
            "checkpoint_id": "cp-001",
            "parent_checkpoint_id": None,
            "checkpoint": {
                "v": 1, "id": "cp-001", "ts": "2026-07-10T12:00:00Z",
                "channel_values": {}, "channel_versions": {},
                "versions_seen": {},
            },
            "metadata": {"source": "loop", "step": 3, "writes": {}, "parents": {}},
        }

        class FakeStore:
            def ensure_collections(self):
                pass
            class db:
                class agent_checkpoints:
                    @staticmethod
                    def find_one(query, sort=None):
                        return doc
                class checkpoint_writes:
                    @staticmethod
                    def find(query):
                        return _EmptyWritesCursor()

        saver = MongoDBSaver.__new__(MongoDBSaver)
        saver._store = FakeStore()

        result = saver.get_tuple({"configurable": {"thread_id": "job-1"}})
        assert result is not None
        assert isinstance(result, CheckpointTuple)
        assert result.checkpoint["id"] == "cp-001"
        assert result.metadata["step"] == 3

    def test_put_upserts_checkpoint(self, monkeypatch):
        """put should upsert the checkpoint document."""
        from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata

        from agent.mongo_saver import MongoDBSaver

        last_doc = {}

        def _replace_one(filter, replacement, upsert=False):
            last_doc["doc"] = replacement
            return type("Result", (), {"upserted_id": "new-1"})

        class FakeStore:
            def ensure_collections(self):
                pass
            class db:
                class agent_checkpoints:
                    @staticmethod
                    def replace_one(filter, replacement, upsert=False):
                        return _replace_one(filter, replacement, upsert)

        saver = MongoDBSaver.__new__(MongoDBSaver)
        saver._store = FakeStore()

        checkpoint = Checkpoint(
            v=1, id="cp-002", ts="2026-07-10T12:00:01Z",
            channel_values={}, channel_versions={}, versions_seen={},
        )
        metadata = CheckpointMetadata(source="loop", step=4, writes={}, parents={})

        result = saver.put(
            {"configurable": {"thread_id": "job-1", "checkpoint_id": "cp-001"}},
            checkpoint, metadata, {},
        )
        assert result is not None
        assert last_doc["doc"]["thread_id"] == "job-1"
        assert last_doc["doc"]["checkpoint_id"] == "cp-002"
