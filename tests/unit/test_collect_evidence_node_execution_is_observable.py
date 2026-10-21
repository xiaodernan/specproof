"""collect_evidence node execution tests — honest counters at the node boundary.

The node runs the dynamic collectors and persists an evidence pack. Three
things must be true, and none of them may be assumed:

- the counters say what actually happened (attempt / saved / failed /
  no-fragments), not what was intended;
- a store that is unreachable degrades to "nothing observed" and the node
  still finishes — evidence collection must never break the pipeline;
- a pack that reaches MongoDB carries the fragments the collectors
  produced, with their honest status (NO_EVIDENCE for an absent
  observation, not a fabricated COMPLIANT).

Only the external stores are stubbed; the collectors and the pack
assembly are the real code.
"""

from __future__ import annotations

from typing import Any

import pytest

from agent.nodes.collect_evidence import collect_evidence_node
from observability.metrics import snapshot


def _counter(name: str) -> float:
    # The registry stores BARE names — the specproof_ prefix is added by
    # render_text only.
    return snapshot()["counters"].get(name, 0.0)


class _FakeRedis:
    """A Redis double: one key present with a value, one absent."""

    def __init__(self) -> None:
        self.keys = {"user:cache:1": ("alice", 42)}

    def get(self, name: str) -> Any:
        entry = self.keys.get(name)
        return entry[0] if entry else None

    def ttl(self, name: str) -> int:
        entry = self.keys.get(name)
        return entry[1] if entry else -2

    def ping(self) -> bool:
        return True


class _FakeObjectStore:
    """An object-store double: one object present, one absent."""

    def __init__(self) -> None:
        self.objects = {
            "specproof/jobs/j-1/capsule.zip": {
                "size_bytes": 42,
                "content_type": "application/zip",
                "sha256": "a" * 64,
            }
        }

    def object_exists(self, bucket: str, object_name: str) -> bool:
        return f"{bucket}/{object_name}" in self.objects

    def object_stat(self, bucket: str, object_name: str) -> dict[str, Any]:
        return dict(self.objects[f"{bucket}/{object_name}"])


class _RecordingMongo:
    """A MongoDB double: records the packs it was asked to save."""

    def __init__(self) -> None:
        self.packs: list[dict[str, Any]] = []

    def save_evidence_pack(self, pack: dict[str, Any]) -> str:
        self.packs.append(pack)
        return "pack-id"


def _state(job_id: str = "job-338-0001") -> dict[str, Any]:
    return {
        "job_id": job_id,
        "repo_path": "repo",
        "base_ref": "base",
        "head_ref": "head",
        "capsules": [],
    }


def _stub_stores(
    monkeypatch: pytest.MonkeyPatch,
    *,
    redis: Any | None = None,
    objects: Any | None = None,
    mongo: Any | None = None,
) -> _RecordingMongo:
    """Replace the three external stores; everything else is the real code."""
    recorder = mongo if isinstance(mongo, _RecordingMongo) else _RecordingMongo()
    monkeypatch.setattr(
        "agent.nodes.collect_evidence._build_redis_client",
        lambda: redis,
    )
    monkeypatch.setattr(
        "agent.nodes.collect_evidence._build_object_store",
        lambda: objects,
    )

    class _MongoFactory:
        def __init__(self) -> None:
            self.save_evidence_pack = recorder.save_evidence_pack

    monkeypatch.setattr(
        "storage.mongodb.MongoDBStore", lambda *a, **k: _MongoFactory()
    )
    return recorder


# ── the counters ────────────────────────────────────────────────────────────


def test_a_successful_collection_counts_runs_and_saved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mongo = _stub_stores(
        monkeypatch, redis=_FakeRedis(), objects=_FakeObjectStore()
    )
    before_runs = _counter("collect_evidence_runs_total")
    before_saved = _counter("collect_evidence_pack_saved_total")

    result = collect_evidence_node(_state())

    assert _counter("collect_evidence_runs_total") == before_runs + 1
    assert _counter("collect_evidence_pack_saved_total") == before_saved + 1
    assert result["evidence_pack_saved"] is True
    assert result["evidence_pack_error"] is None
    assert result["fragments_collected"] >= 1
    assert len(mongo.packs) == 1


def test_a_missing_job_id_is_skipped_not_guessed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mongo = _stub_stores(
        monkeypatch, redis=_FakeRedis(), objects=_FakeObjectStore()
    )
    before_skipped = _counter("collect_evidence_skipped_no_job_id_total")

    result = collect_evidence_node({"job_id": ""})

    assert _counter("collect_evidence_skipped_no_job_id_total") == before_skipped + 1
    assert result["evidence_pack_saved"] is False
    assert result["evidence_pack_error"] == "no job_id"
    # Nothing was written — a pack with no job id cannot be found later.
    assert mongo.packs == []


def test_no_collectors_means_no_pack_and_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No store answered ⇒ no fragments ⇒ NO pack, and the reason is named.

    An empty pack would be worse than none: it would look like a
    collection that found nothing, when in fact nothing was looked at.
    """
    mongo = _stub_stores(monkeypatch, redis=None, objects=None)
    before_runs = _counter("collect_evidence_runs_total")
    before_none = _counter("collect_evidence_no_fragments_total")

    result = collect_evidence_node(_state())

    assert _counter("collect_evidence_runs_total") == before_runs + 1
    assert _counter("collect_evidence_no_fragments_total") == before_none + 1
    assert result["evidence_pack_saved"] is False
    assert result["evidence_pack_error"] == "no fragments collected"
    assert mongo.packs == []


def test_a_failing_mongo_reports_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pack that cannot be stored must not take the pipeline down.

    The fragments were observed; losing the store does not un-observe
    them. The node reports the failure so the run is visibly degraded.
    """
    _stub_stores(monkeypatch, redis=_FakeRedis(), objects=_FakeObjectStore())

    class _BrokenMongo:
        def save_evidence_pack(self, pack: dict[str, Any]) -> str:
            raise RuntimeError("mongo unreachable")

    monkeypatch.setattr(
        "storage.mongodb.MongoDBStore", lambda *a, **k: _BrokenMongo()
    )
    before_failed = _counter("collect_evidence_pack_failed_total")

    result = collect_evidence_node(_state())

    assert _counter("collect_evidence_pack_failed_total") == before_failed + 1
    assert result["evidence_pack_saved"] is False
    assert "mongo unreachable" in str(result["evidence_pack_error"])
    # The fragments were still observed — the count says so.
    assert result["fragments_collected"] >= 1


def test_an_unreachable_store_degrades_and_still_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A store that throws must not abort the node.

    Two DIFFERENT failures live here and they get different counters:

    - the CLIENT could not be built (the store is unreachable) ⇒ the
      node could not look ⇒ "unavailable";
    - the collector ran and every read failed ⇒ the collector absorbed
      it as absence, and the fragment-level status is what keeps that
      from being read as a deletion: nothing was observed, so the
      fragment says NO_EVIDENCE — not COMPLIANT (which would claim the
      keys were checked and found absent) and not a REGRESSION (which
      would claim they were deleted).
    """
    class _BrokenRedis:
        def get(self, name: str) -> Any:
            raise RuntimeError("redis down")

        def ttl(self, name: str) -> int:
            raise RuntimeError("redis down")

        def ping(self) -> bool:
            raise RuntimeError("redis down")

    mongo = _stub_stores(
        monkeypatch, redis=_BrokenRedis(), objects=_FakeObjectStore()
    )
    before_failed = _counter("collect_evidence_redis_failed_total")

    result = collect_evidence_node(_state())

    # The collector absorbed the read failures, so the NODE's failure
    # counter did not fire — that counter means "the collector could not
    # be run at all", which is a different failure.
    assert _counter("collect_evidence_redis_failed_total") == before_failed
    # The object collector still produced a fragment — one broken store
    # must not silence the others.
    assert result["fragments_collected"] >= 1
    assert len(mongo.packs) == 1

    redis_fragments = [
        f for f in mongo.packs[0]["fragments"] if f["fragment_type"] == "redis"
    ]
    assert redis_fragments, "the redis collector still produced a fragment"
    # The honest status: nothing was observed, so nothing is claimed.
    assert redis_fragments[0]["status"] == "NO_EVIDENCE"
    assert redis_fragments[0]["extension"]["observed_any_key"] is False


def test_an_unreachable_store_is_counted_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A store the node could not even connect to gets its own counter.

    "The store was unreachable" and "the collector ran and found
    nothing" must not share a counter: otherwise a degraded run looks
    exactly like a clean one.
    """
    _stub_stores(monkeypatch, redis=None, objects=None)
    before_unavailable = _counter("collect_evidence_redis_unavailable_total")
    before_object_unavailable = _counter(
        "collect_evidence_object_unavailable_total"
    )

    collect_evidence_node(_state())

    assert (
        _counter("collect_evidence_redis_unavailable_total")
        == before_unavailable + 1
    )
    assert (
        _counter("collect_evidence_object_unavailable_total")
        == before_object_unavailable + 1
    )


def test_a_collector_that_cannot_run_is_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The node-level failure counter means "the collector could not run".

    That is a different failure from "the collector ran and found
    nothing", and the two must not share a counter — otherwise a
    degraded run looks like a clean one.
    """
    class _ExplodingCollector:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("collector cannot be constructed")

    _stub_stores(monkeypatch, redis=_FakeRedis(), objects=_FakeObjectStore())
    monkeypatch.setattr(
        "agent.nodes.collect_evidence._get_collectors",
        lambda: (_ExplodingCollector, _ExplodingCollector, _ExplodingCollector),
    )
    before_failed = _counter("collect_evidence_redis_failed_total")
    before_object_failed = _counter("collect_evidence_object_failed_total")

    result = collect_evidence_node(_state())

    assert _counter("collect_evidence_redis_failed_total") == before_failed + 1
    assert (
        _counter("collect_evidence_object_failed_total")
        == before_object_failed + 1
    )
    # Both collectors failed ⇒ no fragments ⇒ no pack (and the reason).
    assert result["evidence_pack_saved"] is False
    assert result["evidence_pack_error"] == "no fragments collected"


# ── what the pack actually carries ──────────────────────────────────────────


def test_the_pack_carries_the_fragments_with_their_honest_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mongo = _stub_stores(
        monkeypatch, redis=_FakeRedis(), objects=_FakeObjectStore()
    )
    collect_evidence_node(_state())

    assert len(mongo.packs) == 1
    pack = mongo.packs[0]
    assert pack["job_id"] == "job-338-0001"
    assert pack["created_at"]
    fragments = pack["fragments"]
    assert fragments
    types = {f["fragment_type"] for f in fragments}
    assert "redis" in types
    # Every fragment carries the honest status vocabulary — no invented
    # "COMPLIANT" for something nobody looked at.
    allowed = {
        "COMPLIANT", "REGRESSION", "AMBIGUOUS",
        "NON_REPRODUCIBLE", "NO_EVIDENCE",
    }
    for fragment in fragments:
        assert fragment["status"] in allowed
        assert fragment["experiment_id"] == "job-338-0001"


def test_the_graph_runs_the_node_between_deep_and_court() -> None:
    """The node must be IN the pipeline, not merely importable.

    A collector that no graph edge reaches is a library, and the evidence
    pack would never be produced by a real run.
    """
    from agent.graph import build_phase0_graph

    graph = build_phase0_graph()
    nodes = set(graph.get_graph().nodes)
    assert "collect_evidence" in nodes

    edges = {
        (e.source, e.target)
        for e in graph.get_graph().edges
    }
    assert ("run_deep_experiments", "collect_evidence") in edges
    assert ("collect_evidence", "review_court") in edges
