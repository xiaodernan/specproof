"""The worker's checkpoint survives a crash — against the REAL saver and the
REAL MongoDB, not a simulation of them.

What was measured before this file existed
------------------------------------------
``tests/integration/test_worker_crash_mid_graph.py`` asserted the crash
semantics against **local Python lists** ("the nodes before the crash are
``all_nodes[:crash_index]``"). That is a statement about a list, not about the
worker: the machinery that actually carries a crash across a process is
``agent/mongo_saver.py`` (a LangGraph ``BaseCheckpointSaver`` writing to
MongoDB) plus the resume loop in ``agent/worker.py`` — and nothing exercised
it end to end. The branch this repository reconciled even listed
``test_worker_recovers_from_checkpoint`` as a permanently skipped
placeholder ("P1.6 checkpoint recovery deferred to P1-B").

What this file does
-------------------
It writes a checkpoint through the production saver, drops the saver (a new
worker process would have none of the in-memory state), reads it back through
a **fresh** saver, and asserts three properties that a resume depends on:

  1. the checkpoint survives at all — same id, same channel values, same step;
  2. an explicit ``checkpoint_id`` is honoured (a lookup that always returned
     the newest document would hide every pending write — the exact failure
     the saver's own docstring says was observed live: "a worker-kill resume
     replayed the run from the input instead of continuing from the last
     checkpoint");
  3. pending writes (a node's output that was persisted before the superstep
     ran) come back with the checkpoint, because resume replays exactly that
     superstep.

Isolation
---------
The MongoDB store defaults to the product database (``specproof_phase0``),
so this file points it at a scratch database of its own
(``specproof_test_checkpoint``) and drops it afterwards. It never writes to
the product database, and it skips (rather than fails) when MongoDB is not
reachable — a machine without Mongo has no way to run this leg, and saying
"green" without one would be a lie.
"""

from __future__ import annotations

import uuid
from contextlib import suppress
from typing import Any

import pytest

from agent.mongo_saver import MongoDBSaver
from storage.mongodb import MongoDBStore

#: The scratch database this file owns. It is NOT the product database.
SCRATCH_DB = "specproof_test_checkpoint"


@pytest.fixture
def mongo_store(monkeypatch: pytest.MonkeyPatch) -> MongoDBStore:
    """A MongoDB store pointed at a scratch database, skipped if unreachable."""
    monkeypatch.setenv("MONGODB_DATABASE", SCRATCH_DB)
    monkeypatch.setenv("MONGODB_PASSWORD", "specproof_pass")
    store = MongoDBStore()
    try:
        store.ensure_collections()
    except Exception as exc:  # noqa: BLE001 — any connection failure means "no Mongo here"
        pytest.skip(f"MongoDB not available for the checkpoint leg: {exc}")
    try:
        yield store
    finally:
        with suppress(Exception):  # cleanup is best-effort
            store.db.client.drop_database(SCRATCH_DB)


def _checkpoint(checkpoint_id: str, step: int, values: dict[str, Any]) -> dict[str, Any]:
    return {
        "v": 1,
        "id": checkpoint_id,
        "ts": "2026-11-10T00:00:00+00:00",
        "channel_values": values,
        "channel_versions": {},
        "versions_seen": {},
    }


def _metadata(step: int) -> dict[str, Any]:
    return {"source": "loop", "step": step, "writes": None, "parents": {}}


def test_a_checkpoint_written_before_a_crash_is_readable_by_a_fresh_worker(
    mongo_store: MongoDBStore,
) -> None:
    """The crash case: a worker dies after persisting a checkpoint; the next
    worker (a new saver, no shared memory) must find that checkpoint."""
    job_id = f"ckpt-{uuid.uuid4().hex[:12]}"
    checkpoint_id = "1f0000000000000000000000000000"
    values = {
        "completed_nodes": ["intake", "compile_contracts", "run_static_checks"],
        "repo_path": "/test/repo",
    }
    config: dict[str, Any] = {
        "configurable": {"thread_id": job_id, "checkpoint_ns": "", "checkpoint_id": checkpoint_id}
    }

    saver = MongoDBSaver(mongo_store)
    saver.put(config, _checkpoint(checkpoint_id, 6, values), _metadata(6), {})

    # A different saver instance stands in for the restarted worker.
    fresh = MongoDBSaver(mongo_store)
    found = fresh.get_tuple({
        "configurable": {"thread_id": job_id, "checkpoint_ns": ""}
    })

    assert found is not None, (
        "the checkpoint the crashed worker wrote is not readable by a fresh "
        "saver — a resume would start from the input and redo the whole job"
    )
    assert found.checkpoint["id"] == checkpoint_id
    assert found.checkpoint["channel_values"]["completed_nodes"] == values["completed_nodes"]
    assert found.checkpoint["channel_values"]["repo_path"] == "/test/repo"
    assert found.metadata.get("step") == 6


def test_an_explicit_checkpoint_id_is_honoured(mongo_store: MongoDBStore) -> None:
    """The resume loop asks for a SPECIFIC checkpoint id. A lookup that always
    returned the newest document would answer with the wrong one and the
    pending writes of the interrupted superstep would be invisible."""
    job_id = f"ckpt-{uuid.uuid4().hex[:12]}"
    older_id = "1a0000000000000000000000000000"
    newer_id = "1b0000000000000000000000000000"

    saver = MongoDBSaver(mongo_store)
    base: dict[str, Any] = {"configurable": {"thread_id": job_id, "checkpoint_ns": ""}}
    saver.put(
        {**base, "configurable": {**base["configurable"], "checkpoint_id": older_id}},
        _checkpoint(older_id, 3, {"completed_nodes": ["intake"]}),
        _metadata(3),
        {},
    )
    saver.put(
        {**base, "configurable": {**base["configurable"], "checkpoint_id": newer_id}},
        _checkpoint(newer_id, 4, {"completed_nodes": ["intake", "compile_contracts"]}),
        _metadata(4),
        {},
    )

    found = saver.get_tuple({
        "configurable": {"thread_id": job_id, "checkpoint_ns": "", "checkpoint_id": older_id}
    })
    assert found is not None
    assert found.checkpoint["id"] == older_id, (
        "the saver answered with the newest checkpoint instead of the one the "
        "resume asked for — the interrupted superstep's writes would be lost"
    )
    assert found.checkpoint["channel_values"]["completed_nodes"] == ["intake"]


def test_pending_writes_come_back_with_the_checkpoint(mongo_store: MongoDBStore) -> None:
    """A hard kill mid-superstep leaves the task's writes behind; resume must
    replay exactly that superstep, so the writes have to travel with the
    checkpoint."""
    job_id = f"ckpt-{uuid.uuid4().hex[:12]}"
    checkpoint_id = "1c0000000000000000000000000000"
    config: dict[str, Any] = {
        "configurable": {"thread_id": job_id, "checkpoint_ns": "", "checkpoint_id": checkpoint_id}
    }

    saver = MongoDBSaver(mongo_store)
    saver.put(
        config,
        _checkpoint(checkpoint_id, 9, {"completed_nodes": ["intake"]}),
        _metadata(9),
        {},
    )
    saver.put_writes(
        config,
        [("static_findings", [{"id": "S-1", "severity": "HIGH"}])],
        task_id="t1",
    )

    found = saver.get_tuple({
        "configurable": {"thread_id": job_id, "checkpoint_ns": ""}
    })
    assert found is not None
    assert found.pending_writes, (
        "the pending write of the interrupted superstep is gone — a resume "
        "would re-run the node without the output it had already produced"
    )
    channels = [channel for _task_id, channel, _value in found.pending_writes]
    assert "static_findings" in channels
