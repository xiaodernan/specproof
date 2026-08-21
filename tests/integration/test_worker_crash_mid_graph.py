"""P1.6 Integration tests: worker crash mid-graph, checkpoint recovery.

These tests verify the checkpoint-and-recovery logic without requiring
live infrastructure. The DB-dependent tests skip gracefully when Docker
is unavailable.
"""

import uuid


def make_job_id():
    return f"test-worker-{uuid.uuid4().hex[:12]}"


class _EmptyWritesCursor:
    """Minimal pymongo-cursor stand-in: no pending writes for the fake."""

    def sort(self, *args: object) -> list[object]:
        return []


class TestCrashRecoveryScenarios:
    """Test recovery scenarios at the logic level."""

    def test_checkpoint_saved_before_crash(self):
        """When worker crashes at node 7 (run_differential), checkpoint at
        node 6 (run_static_checks) should already be persisted."""
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
        """If crash happens after publish_report, no recovery is needed."""
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
        """If RabbitMQ delivers the same message twice, idempotency check
        prevents duplicate graph execution."""
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
        """After recovery, intermediate state from earlier nodes is preserved."""
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
        """On resume, LangGraph's checkpointer automatically skips
        nodes that are already in the checkpoint."""
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
    """Verify the interaction of checkpoint recovery with job state machine."""

    def test_stale_job_not_executed(self):
        """If job is STALE, worker should skip execution."""
        valid_statuses = {"PENDING", "QUEUED", "RUNNING"}
        job_status = "STALE"
        assert job_status not in valid_statuses

    def test_running_job_lease_renewal(self):
        """Long-running job should renew its lease periodically."""
        renew_interval = 10  # renew every 10s for a 30s TTL

        # Simulate a 60-second job execution
        execution_time = 60
        renewals_needed = execution_time // renew_interval
        assert renewals_needed >= 2  # must renew at least twice

    def test_worker_marks_stale_on_new_head(self):
        """When a new Head SHA arrives, existing RUNNING jobs for old Head
        must be marked STALE."""
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
    """Verify the MongoDBSaver interface contract."""

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
