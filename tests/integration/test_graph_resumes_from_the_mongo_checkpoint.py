"""A crashed graph resumes from its MongoDB checkpoint — the real graph, the
real saver, the real database.

What was measured before this file existed
------------------------------------------
The crash machinery was covered in three places, none of which ran a graph:
``tests/unit/test_checkpoint_recovery.py`` (models over dicts),
``tests/integration/test_worker_crash_mid_graph.py`` (models over lists, plus
saver-level legs against a fake driver) and
``tests/integration/test_worker_checkpoint_survives_a_crash.py`` (the saver
against a real MongoDB — a checkpoint survives, an explicit checkpoint id is
honoured, pending writes come back).

What was still missing: **does a graph actually resume?** A checkpoint that
round-trips says nothing about whether LangGraph — the framework the worker
compiles its pipeline with — uses it to skip completed work. The honest proof
is a graph that crashes in the middle and is then re-invoked.

What this file does
-------------------
It compiles a small LangGraph graph with the production
``agent.mongo_saver.MongoDBSaver`` as its checkpointer:

  1. the first invocation crashes inside the middle node (the node raises);
  2. the checkpoint at that point holds the FIRST node's output — read back
     through the saver, not through the graph's own memory;
  3. the second invocation (same ``thread_id``, crash disarmed) completes the
     graph — and the first node does **not** run a second time, which is the
     whole promise of a checkpointer.

The counters are external (module-level), so "did node A run again?" is
answered by observation, not by trusting the graph's own bookkeeping.

Isolation
---------
``MONGODB_DATABASE`` points at a scratch database of this file's own
(``specproof_test_resume``), dropped afterwards. The product database is
never touched, and an unreachable MongoDB makes the legs skip with the real
reason rather than pass vacuously.
"""

from __future__ import annotations

import uuid
from contextlib import suppress
from typing import Any, TypedDict

import pytest

from agent.mongo_saver import MongoDBSaver
from storage.mongodb import MongoDBStore

#: The scratch database this file owns. It is NOT the product database.
SCRATCH_DB = "specproof_test_resume"

#: How many times each node actually executed, across both invocations.
EXECUTIONS: dict[str, int] = {}

#: Whether the middle node raises on this invocation.
CRASH = {"armed": True}


class _State(TypedDict, total=False):
    steps: list[str]


@pytest.fixture
def mongo_store(monkeypatch: pytest.MonkeyPatch) -> MongoDBStore:
    """A MongoDB store pointed at a scratch database, skipped if unreachable."""
    monkeypatch.setenv("MONGODB_DATABASE", SCRATCH_DB)
    monkeypatch.setenv("MONGODB_PASSWORD", "specproof_pass")
    store = MongoDBStore()
    try:
        store.ensure_collections()
    except Exception as exc:  # noqa: BLE001 — any connection failure means "no Mongo here"
        pytest.skip(f"MongoDB not available for the resume leg: {exc}")
    EXECUTIONS.clear()
    CRASH["armed"] = True
    try:
        yield store
    finally:
        with suppress(Exception):  # cleanup is best-effort
            store.db.client.drop_database(SCRATCH_DB)


def _build_graph(checkpointer: MongoDBSaver) -> Any:
    from langgraph.graph import END, START, StateGraph

    def first(state: _State) -> dict[str, Any]:
        EXECUTIONS["first"] = EXECUTIONS.get("first", 0) + 1
        return {"steps": [*state.get("steps", []), "first"]}

    def middle(state: _State) -> dict[str, Any]:
        EXECUTIONS["middle"] = EXECUTIONS.get("middle", 0) + 1
        if CRASH["armed"]:
            raise RuntimeError("worker killed in the middle node")
        return {"steps": [*state.get("steps", []), "middle"]}

    def last(state: _State) -> dict[str, Any]:
        EXECUTIONS["last"] = EXECUTIONS.get("last", 0) + 1
        return {"steps": [*state.get("steps", []), "last"]}

    builder = StateGraph(_State)
    builder.add_node("first", first)
    builder.add_node("middle", middle)
    builder.add_node("last", last)
    builder.add_edge(START, "first")
    builder.add_edge("first", "middle")
    builder.add_edge("middle", "last")
    builder.add_edge("last", END)
    return builder.compile(checkpointer=checkpointer)


def test_the_newest_checkpoint_wins_when_no_id_is_given(mongo_store: MongoDBStore) -> None:
    """The lookup without an explicit id must answer with the NEWEST document.

    This is the defect the resume leg above found (2026-11-10): the lookup
    did not sort, so Mongo's natural order answered with the OLDEST document
    of the thread — the ``__start__`` one — and a resume replayed the whole
    job from the input. The saver's own ``list()`` already sorted newest
    first; this lookup did not, and now both do.
    """
    job_id = f"order-{uuid.uuid4().hex[:12]}"
    base: dict[str, Any] = {"configurable": {"thread_id": job_id, "checkpoint_ns": ""}}
    saver = MongoDBSaver(mongo_store)

    ids = ("1a0000000000000000000000000000", "1b0000000000000000000000000000",
           "1c0000000000000000000000000000")
    for index, checkpoint_id in enumerate(ids):
        saver.put(
            {**base, "configurable": {**base["configurable"], "checkpoint_id": checkpoint_id}},
            _checkpoint(checkpoint_id, index, {"steps": [f"node-{index}"]}),
            {"source": "loop", "step": index, "writes": None, "parents": {}},
            {},
        )

    found = saver.get_tuple({"configurable": {"thread_id": job_id, "checkpoint_ns": ""}})
    assert found is not None
    assert found.checkpoint["id"] == ids[-1], (
        f"the lookup answered with {found.checkpoint['id']!r}, not the newest "
        f"({ids[-1]!r}) — a resume would start from the wrong point"
    )


def _checkpoint(checkpoint_id: str, step: int, values: dict[str, Any]) -> dict[str, Any]:
    return {
        "v": 1,
        "id": checkpoint_id,
        "ts": "2026-11-10T00:00:00+00:00",
        "channel_values": values,
        "channel_versions": {},
        "versions_seen": {},
    }


def test_a_crashed_graph_resumes_and_does_not_rerun_the_finished_node(
    mongo_store: MongoDBStore,
) -> None:
    saver = MongoDBSaver(mongo_store)
    graph = _build_graph(saver)
    job_id = f"resume-{uuid.uuid4().hex[:12]}"
    config = {"configurable": {"thread_id": job_id}}

    # 1. the crash: the middle node raises.
    with pytest.raises(RuntimeError):
        graph.invoke({"steps": []}, config)

    assert EXECUTIONS.get("first") == 1, "the first node did not run before the crash"
    assert EXECUTIONS.get("middle") == 1, "the middle node did not run before the crash"
    assert "last" not in EXECUTIONS, "the graph ran past the crash"

    # 2. the checkpoint holds the first node's output — read through the saver.
    found = saver.get_tuple({"configurable": {"thread_id": job_id, "checkpoint_ns": ""}})
    assert found is not None, "no checkpoint survived the crash"
    assert found.checkpoint["channel_values"].get("steps") == ["first"], (
        f"the checkpoint does not hold the finished node's output: "
        f"{found.checkpoint['channel_values']!r}"
    )

    # 3. the resume: same thread id, and — this is LangGraph's resume contract
    #    — the input is None. Passing the original input again would start a
    #    NEW run from START; a resume continues the interrupted one.
    CRASH["armed"] = False
    result = graph.invoke(None, config)

    assert result["steps"] == ["first", "middle", "last"], (
        f"the resumed graph produced {result['steps']!r}"
    )
    assert EXECUTIONS.get("first") == 1, (
        "the first node ran a second time after the resume — the checkpointer "
        "did not make the graph skip the finished work"
    )
    assert EXECUTIONS.get("middle") == 2, (
        "the crashed node should have run again on resume (once before the "
        "crash, once after)"
    )
    assert EXECUTIONS.get("last") == 1
