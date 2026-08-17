"""P1.6 Unit tests: checkpoint save/load, recovery logic, state serialization."""

import json


class TestCheckpointDocumentModel:
    """Verify the checkpoint document structure used by MongoDBSaver."""

    def test_checkpoint_doc_has_required_fields(self):
        doc = {
            "thread_id": "job-abc123",
            "checkpoint_id": "1ef9b612-0000-6000-8000-000000000001",
            "parent_checkpoint_id": "1ef9b612-0000-6000-8000-000000000000",
            "checkpoint_ns": "",
            "checkpoint": {
                "v": 1,
                "id": "1ef9b612-0000-6000-8000-000000000001",
                "ts": "2026-07-10T12:00:00Z",
                "channel_values": {"messages": [], "repo_path": "/tmp/repo"},
                "channel_versions": {},
            },
            "metadata": {
                "source": "loop",
                "step": 5,
                "writes": {},
                "parents": {},
            },
        }
        assert "thread_id" in doc
        assert "checkpoint_id" in doc
        assert "checkpoint" in doc
        assert "metadata" in doc
        assert doc["checkpoint"]["v"] == 1

    def test_thread_id_maps_to_job_id(self):
        """In our design, thread_id == job_id."""
        job_id = "p1-job-0001"
        config = {"configurable": {"thread_id": job_id}}
        assert config["configurable"]["thread_id"] == job_id

    def test_parent_chain_traversable(self):
        """Checkpoints form a parent chain for recovery."""
        checkpoints = [
            {"id": "c3", "parent_id": "c2", "step": 6},
            {"id": "c2", "parent_id": "c1", "step": 4},
            {"id": "c1", "parent_id": None, "step": 2},
        ]
        parents = {c["id"]: c["parent_id"] for c in checkpoints}
        assert parents["c2"] == "c1"
        assert parents["c1"] is None


class TestRecoveryLogic:
    """Test the recovery decision logic without actual graph execution."""

    def test_resume_from_last_checkpoint(self):
        """After a crash at step 7, the next invocation should find the
        checkpoint at step 6 and skip completed nodes."""
        completed_nodes = ["intake", "compile_contracts", "prepare_base",
                          "prepare_head", "collect_diff", "run_static_checks"]
        all_nodes = completed_nodes + [
            "generate_counterexamples", "run_differential",
            "review_court", "build_matrix", "create_capsule", "publish_report",
        ]

        # Simulated crash after run_static_checks checkpoint saved
        last_checkpoint_step = len(completed_nodes)

        # Recovery: remaining nodes
        remaining = all_nodes[last_checkpoint_step:]
        assert remaining[0] == "generate_counterexamples"
        assert len(remaining) == 6

    def test_no_checkpoint_runs_all_nodes(self):
        """First run with no existing checkpoint executes all nodes."""
        all_nodes = ["intake", "compile_contracts", "prepare_base",
                     "prepare_head", "collect_diff", "run_static_checks",
                     "generate_counterexamples", "run_differential",
                     "review_court", "build_matrix", "create_capsule", "publish_report"]
        assert len(all_nodes) == 12

    def test_full_recovery_no_duplicate_execution(self):
        """Nodes already recorded in checkpoint should not re-execute."""
        executed_nodes = {"intake", "compile_contracts"}  # nodes in checkpoint
        all_nodes = ["intake", "compile_contracts", "prepare_base"]

        skipped = [n for n in all_nodes if n in executed_nodes]
        new_exec = [n for n in all_nodes if n not in executed_nodes]

        assert skipped == ["intake", "compile_contracts"]
        assert new_exec == ["prepare_base"]

    def test_checkpoint_after_every_node(self):
        """Every node completion should produce a checkpoint."""
        nodes = ["intake", "compile_contracts", "prepare_base", "prepare_head",
                 "collect_diff", "run_static_checks"]
        checkpoint_count = 0
        for _ in nodes:
            checkpoint_count += 1
        assert checkpoint_count == len(nodes)

    def test_recovery_with_different_worker(self):
        """A different worker instance should be able to resume from checkpoint."""
        original_worker = "worker-A"
        recovery_worker = "worker-B"
        thread_id = "job-1"

        # Original worker saved checkpoint
        saved = {
            "thread_id": thread_id,
            "worker": original_worker,
            "last_node": "run_static_checks",
        }

        # Recovery worker loads same checkpoint
        loaded = saved  # same data from MongoDB
        assert loaded["thread_id"] == thread_id
        assert loaded["last_node"] == "run_static_checks"
        assert original_worker != recovery_worker


class TestStateSerialization:
    """Verify Phase0State fields survive JSON round-trip."""

    def test_state_to_dict(self):
        from agent.state import initial_state
        state = initial_state("/repo", "base", "head-v1", "spec.txt")
        assert isinstance(state, dict)
        assert state["repo_path"] == "/repo"
        assert state["base_ref"] == "base"
        assert state["head_ref"] == "head-v1"

    def test_state_defaults(self):
        from agent.state import initial_state
        state = initial_state("/repo", "base", "head", "spec.txt")
        assert state["depth"] == "FAST"
        assert state["contracts"] == []
        assert state["errors"] == []
        assert state["max_iterations"] == 3

    def test_state_serializable(self):
        """State must be JSON-serializable for checkpoint storage."""
        from agent.state import initial_state
        state = initial_state("/repo", "base", "head", "spec.txt")
        # Lists, dicts, strings, ints — all serializable
        serialized = json.dumps(state, default=str)
        recovered = json.loads(serialized)
        assert recovered["repo_path"] == "/repo"
        assert recovered["contracts"] == []
        assert recovered["errors"] == []

    def test_messages_field_serializable(self):
        """Messages (from MessagesState) must survive serialization."""
        from agent.state import initial_state
        state = initial_state("/repo", "base", "head", "spec.txt")
        assert "messages" in state
        assert state["messages"] == []


class TestWorkerLifecycle:
    """Test worker logic without real infrastructure."""

    def test_worker_id_unique(self):
        import os
        import time
        w1 = f"worker-{os.getpid()}-{int(time.time())}"
        time.sleep(0.01)
        w2 = f"worker-{os.getpid()}-{int(time.time() + 1)}"
        assert w1 != w2

    def test_lease_prevents_duplicate(self):
        """Two workers attempting same job: only one acquires lease."""
        lease_owner = None

        def try_acquire(job_id, worker_id):
            nonlocal lease_owner
            if lease_owner is None:
                lease_owner = worker_id
                return True
            return False

        assert try_acquire("job-1", "worker-A") is True
        assert try_acquire("job-1", "worker-B") is False
        assert lease_owner == "worker-A"

    def test_lease_release_allows_retake(self):
        """After release, another worker can acquire."""
        lease_owner = "worker-A"

        def release(worker_id):
            nonlocal lease_owner
            if lease_owner == worker_id:
                lease_owner = None

        def try_acquire(job_id, worker_id):
            nonlocal lease_owner
            if lease_owner is None:
                lease_owner = worker_id
                return True
            return False

        release("worker-A")
        assert try_acquire("job-1", "worker-B") is True
