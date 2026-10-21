"""collect_evidence node execution tests — honest counters at the node boundary.

The node takes the TWO external-state snapshots the differential run
captured (after the Base run and after the Head run), builds the
fragments from them, and persists an evidence pack.

Three things must be true, and none of them may be assumed:

- the counters say what actually happened (attempt / saved / failed /
  no-fragments), not what was intended;
- a missing snapshot is NO_EVIDENCE — the node never compares a
  snapshot with itself and calls it "unchanged";
- a pack that reaches MongoDB carries the fragments with their honest
  status.

Only MongoDB is stubbed; the collectors and the pack assembly are the
real code, and the snapshots are the real shape the differential run
produces.
"""

from __future__ import annotations

from typing import Any

import pytest

from agent.nodes.collect_evidence import collect_evidence_node
from observability.metrics import snapshot

BUCKET = "specproof"
KEY = "user:cache:1"
REF = f"{BUCKET}/jobs/j-1/capsule.zip"


def _counter(name: str) -> float:
    # The registry stores BARE names — the specproof_ prefix is added by
    # render_text only.
    return snapshot()["counters"].get(name, 0.0)


class _RecordingMongo:
    """A MongoDB double: records the packs it was asked to save."""

    def __init__(self) -> None:
        self.packs: list[dict[str, Any]] = []

    def save_evidence_pack(self, pack: dict[str, Any]) -> str:
        self.packs.append(pack)
        return "pack-id"


def _moment(*, key_present: bool, object_present: bool) -> dict[str, Any]:
    """One captured moment of the external world."""
    return {
        "redis": {
            KEY: {
                "key": KEY,
                "present": key_present,
                "value": "alice" if key_present else None,
                "ttl_seconds": 60 if key_present else None,
            },
        },
        "objects": {
            REF: {
                "bucket": BUCKET,
                "object_name": "jobs/j-1/capsule.zip",
                "present": object_present,
                "size_bytes": 42 if object_present else 0,
                "content_type": "application/zip" if object_present else "",
                "sha256": "a" * 64 if object_present else "",
                "version": "",
            },
        },
    }


def _state(
    *,
    base: dict[str, Any] | None = None,
    head: dict[str, Any] | None = None,
    job_id: str = "job-339-0001",
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "job_id": job_id,
        "repo_path": "repo",
        "base_ref": "base",
        "head_ref": "head",
        "capsules": [],
        # The contract NAMES its key family in its own text — that is
        # where the family comes from (the profile says what the family
        # is called in this domain).
        "contracts": [{
            "id": "CACHE-01",
            "checker_type": "redis",
            "requirement": "the cached user entry must be evicted on write",
        }],
    }
    if base is not None:
        state["external_state_base"] = base
    if head is not None:
        state["external_state_head"] = head
    return state


def _stub_mongo(monkeypatch: pytest.MonkeyPatch) -> _RecordingMongo:
    recorder = _RecordingMongo()

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
    mongo = _stub_mongo(monkeypatch)
    before_runs = _counter("collect_evidence_runs_total")
    before_saved = _counter("collect_evidence_pack_saved_total")

    result = collect_evidence_node(_state(
        base=_moment(key_present=False, object_present=False),
        head=_moment(key_present=True, object_present=True),
    ))

    assert _counter("collect_evidence_runs_total") == before_runs + 1
    assert _counter("collect_evidence_pack_saved_total") == before_saved + 1
    assert result["evidence_pack_saved"] is True
    assert result["evidence_pack_error"] is None
    assert result["fragments_collected"] == 2
    assert len(mongo.packs) == 1


def test_a_missing_job_id_is_skipped_not_guessed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mongo = _stub_mongo(monkeypatch)
    before_skipped = _counter("collect_evidence_skipped_no_job_id_total")

    result = collect_evidence_node({"job_id": ""})

    assert _counter("collect_evidence_skipped_no_job_id_total") == before_skipped + 1
    assert result["evidence_pack_saved"] is False
    assert result["evidence_pack_error"] == "no job_id"
    # Nothing was written — a pack with no job id cannot be found later.
    assert mongo.packs == []


def test_no_snapshots_means_no_pack_and_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No captured moment ⇒ no fragments ⇒ NO pack, and the reason is named.

    An empty pack would be worse than none: it would look like a
    collection that found nothing, when in fact nothing was looked at.
    """
    mongo = _stub_mongo(monkeypatch)
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
    _stub_mongo(monkeypatch)

    class _BrokenMongo:
        def save_evidence_pack(self, pack: dict[str, Any]) -> str:
            raise RuntimeError("mongo unreachable")

    monkeypatch.setattr(
        "storage.mongodb.MongoDBStore", lambda *a, **k: _BrokenMongo()
    )
    before_failed = _counter("collect_evidence_pack_failed_total")

    result = collect_evidence_node(_state(
        base=_moment(key_present=False, object_present=False),
        head=_moment(key_present=True, object_present=True),
    ))

    assert _counter("collect_evidence_pack_failed_total") == before_failed + 1
    assert result["evidence_pack_saved"] is False
    assert "mongo unreachable" in str(result["evidence_pack_error"])
    # The fragments were still observed — the count says so.
    assert result["fragments_collected"] == 2


# ── what the pack actually carries ──────────────────────────────────────────


def test_the_pack_compares_the_two_moments_not_one_moment_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The difference between the moments is what the fragment reports.

    A snapshot compared with ITSELF would say "nothing changed" and
    still look like a successful observation. The Head run left the
    cache key behind; the fragment must say so.
    """
    mongo = _stub_mongo(monkeypatch)
    state = _state(
        base=_moment(key_present=False, object_present=False),
        head=_moment(key_present=True, object_present=True),
    )
    # A redis-checked contract: its pack is the one that carries the
    # redis observation.
    state["contracts"] = [{
        "id": "CACHE-01",
        "checker_type": "redis",
        "requirement": "the cached user entry must be evicted on write",
    }]

    result = collect_evidence_node(state)

    assert result["evidence_pack_saved"] is True
    fragments = mongo.packs[0]["fragments"]
    redis = next(f for f in fragments if f["fragment_type"] == "redis")
    objects = next(f for f in fragments if f["fragment_type"] == "object")

    for fragment in (redis, objects):
        assert fragment["comparison"]["changed_count"] == 1
        assert fragment["comparison"]["changed"][0]["change"] == "appeared"
        assert fragment["status"] == "AMBIGUOUS"
        assert any(fragment["extension"].values()) is True


def test_identical_moments_are_compliant_not_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same observation twice IS a real answer: nothing changed."""
    mongo = _stub_mongo(monkeypatch)
    collect_evidence_node(_state(
        base=_moment(key_present=True, object_present=True),
        head=_moment(key_present=True, object_present=True),
    ))

    fragments = mongo.packs[0]["fragments"]
    for fragment in fragments:
        assert fragment["comparison"]["changed_count"] == 0
        assert fragment["status"] == "COMPLIANT"


def test_an_empty_moment_is_no_evidence_not_compliant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing observed ⇒ nothing claimed.

    "We did not look" and "we looked and it was fine" are different
    facts, and only one of them is a green.
    """
    mongo = _stub_mongo(monkeypatch)
    collect_evidence_node(_state(
        base=_moment(key_present=False, object_present=False),
        head=_moment(key_present=False, object_present=False),
    ))

    fragments = mongo.packs[0]["fragments"]
    for fragment in fragments:
        assert fragment["status"] == "NO_EVIDENCE"
        assert fragment["confidence"] == 0.0


def test_the_pack_carries_the_fragments_with_their_honest_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mongo = _stub_mongo(monkeypatch)
    state = _state(
        base=_moment(key_present=False, object_present=False),
        head=_moment(key_present=True, object_present=True),
    )
    state["contracts"] = [{
        "id": "CACHE-01",
        "checker_type": "redis",
        "requirement": "the cached user entry must be evicted on write",
    }]
    collect_evidence_node(state)

    assert len(mongo.packs) == 1
    pack = mongo.packs[0]
    assert pack["job_id"] == "job-339-0001"
    # A pack is keyed by (job_id, contract_id) — the collection carries a
    # unique index on exactly that pair.
    assert pack["contract_id"] == "CACHE-01"
    assert pack["created_at"]
    fragments = pack["fragments"]
    assert fragments
    types = {f["fragment_type"] for f in fragments}
    assert types == {"redis", "object"}
    # Every fragment carries the honest status vocabulary — no invented
    # "COMPLIANT" for something nobody looked at.
    allowed = {
        "COMPLIANT", "REGRESSION", "AMBIGUOUS",
        "NON_REPRODUCIBLE", "NO_EVIDENCE",
    }
    for fragment in fragments:
        assert fragment["status"] in allowed
        assert fragment["experiment_id"] == "job-339-0001"


def test_the_capsule_coordinates_are_observed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pipeline's OWN objects must appear in the evidence.

    The capsule coordinates are the run's own artifacts. Before the
    capsules existed there was no such object; after, there is. The
    object fragment must say so — that is what "the evidence chain
    carries the address" means in practice.
    """
    mongo = _stub_mongo(monkeypatch)
    ref = f"{BUCKET}/jobs/job-339-0001/capsule-F1.zip"

    class _FakeStore:
        def object_exists(self, bucket: str, object_name: str) -> bool:
            return f"{bucket}/{object_name}" == ref

        def object_stat(self, bucket: str, object_name: str) -> dict[str, Any]:
            return {
                "size_bytes": 42,
                "content_type": "application/zip",
                "sha256": "a" * 64,
            }

    monkeypatch.setattr(
        "experiments.external_state.build_object_store", lambda: _FakeStore()
    )

    state = _state(
        base=_moment(key_present=False, object_present=False),
        head=_moment(key_present=False, object_present=False),
    )
    state["capsule_refs"] = [ref]
    collect_evidence_node(state)

    fragments = mongo.packs[0]["fragments"]
    objects = next(f for f in fragments if f["fragment_type"] == "object")
    assert objects["comparison"]["changed_count"] == 1
    changed = objects["comparison"]["changed"][0]
    assert changed["change"] == "appeared"
    assert changed["ref"] == ref
    # And the coordinate is IN the evidence — the address, not a path.
    assert ref in objects["head"]


def test_a_run_that_may_not_write_the_trail_does_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The audit trail belongs to real verification jobs.

    A measurement's packs would be `eval-*` rows in the product's
    MongoDB that nobody can delete by job id. The fragments were still
    OBSERVED — the run says so — they were just not filed.
    """
    mongo = _stub_mongo(monkeypatch)
    state = _state(
        base=_moment(key_present=False, object_present=False),
        head=_moment(key_present=True, object_present=True),
    )
    state["write_evidence_pack"] = False

    result = collect_evidence_node(state)

    assert result["evidence_pack_saved"] is False
    assert "may not write" in str(result["evidence_pack_error"])
    # The observation still happened — the count says so.
    assert result["fragments_collected"] == 2
    assert mongo.packs == []


def test_each_contract_gets_only_the_fragments_that_bear_on_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pack is the evidence for ONE contract.

    A contract checked by the redis checker is about the redis state; the
    object coordinates are where its evidence was filed. The rabbitmq
    observation says nothing about it — and a pack full of unrelated
    observations is how a reader ends up believing the wrong thing was
    checked.
    """
    mongo = _stub_mongo(monkeypatch)
    state = _state(
        base=_moment(key_present=False, object_present=False),
        head=_moment(key_present=True, object_present=True),
    )
    state["contracts"] = [
        {
            "id": "CACHE-01",
            "checker_type": "redis",
            "requirement": "the cached user entry must be evicted on write",
        },
        {
            "id": "AUTH-01",
            "checker_type": "http",
            "requirement": "unauthenticated requests must receive 401",
        },
    ]

    result = collect_evidence_node(state)

    assert result["evidence_pack_saved"] is True
    packs = {p["contract_id"]: p for p in mongo.packs}
    cache_kinds = {
        f["fragment_type"] for f in packs["CACHE-01"]["fragments"]
    }
    auth_kinds = {f["fragment_type"] for f in packs["AUTH-01"]["fragments"]}
    assert cache_kinds == {"redis", "object"}
    assert auth_kinds == {"object"}


def test_the_mq_surface_says_why_it_cannot_be_observed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing observation and an UNOBSERVABLE one are different facts.

    The publish happens inside the test's JVM, so the pipeline cannot
    see it from out here. Instead of a silent gap, the rabbitmq-checked
    contract gets an explicit NO_EVIDENCE fragment that says why — so a
    reader of the pack does not have to guess which kind of absence they
    are looking at.
    """
    mongo = _stub_mongo(monkeypatch)
    state = _state(
        base=_moment(key_present=False, object_present=False),
        head=_moment(key_present=True, object_present=True),
    )
    state["contracts"] = [
        {
            "id": "EVENT-01",
            "checker_type": "rabbitmq",
            "requirement": "the event must be published exactly once",
        },
    ]

    collect_evidence_node(state)

    fragments = mongo.packs[0]["fragments"]
    mq = next(f for f in fragments if f["fragment_type"] == "mq")
    assert mq["status"] == "NO_EVIDENCE"
    assert mq["confidence"] == 0.0
    assert mq["extension"]["observed_any_publish"] is False
    assert "test's JVM" in mq["extension"]["not_observable_reason"]


def test_a_contract_that_names_no_key_family_gets_no_redis_fragment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No family named ⇒ nothing observed for it — and nothing invented.

    A contract that does not say which keys it is about cannot have its
    keys guessed: the ids belong to the domain. Guessing would put
    observations in the pack that were never asked for.
    """
    mongo = _stub_mongo(monkeypatch)
    state = _state(
        base=_moment(key_present=True, object_present=False),
        head=_moment(key_present=True, object_present=True),
    )
    state["contracts"] = [
        {"id": "AUTH-01", "checker_type": "http",
         "requirement": "unauthenticated requests must receive 401"},
    ]

    collect_evidence_node(state)

    kinds = {f["fragment_type"] for f in mongo.packs[0]["fragments"]}
    assert kinds == {"object"}
    # And the key that WAS observed for another contract is not in here.
    assert "user:cache:1" not in str(mongo.packs[0]["fragments"])


def test_each_contract_gets_its_own_pack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pack is filed per CONTRACT.

    The collection carries a unique index on (job_id, contract_id) and
    a pack IS "the evidence for this contract" — one pack per contract,
    each carrying the fragments this run observed. (Which fragments BEAR
    on which contract is the wiring still to come; until then every
    pack carries the whole observation set — honest and addressable,
    just not yet narrowed.)
    """
    mongo = _stub_mongo(monkeypatch)
    state = _state(
        base=_moment(key_present=False, object_present=False),
        head=_moment(key_present=True, object_present=True),
    )
    state["contracts"] = [
        {"id": "AUTH-01", "checker_type": "http",
         "requirement": "unauthenticated requests must receive 401"},
        {"id": "CACHE-01", "checker_type": "redis",
         "requirement": "the cached user entry must be evicted on write"},
    ]

    result = collect_evidence_node(state)

    assert result["evidence_pack_saved"] is True
    assert [p["contract_id"] for p in mongo.packs] == ["AUTH-01", "CACHE-01"]
    for pack in mongo.packs:
        assert pack["job_id"] == "job-339-0001"
        assert pack["fragments"]


def test_a_run_with_no_contract_files_no_pack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pack needs a contract to be filed under — and says so.

    Without one there is no address: a pack keyed by nothing could not
    be found by `get_evidence_pack(job_id, contract_id)`.
    """
    mongo = _stub_mongo(monkeypatch)
    state = _state(
        base=_moment(key_present=False, object_present=False),
        head=_moment(key_present=True, object_present=True),
    )
    state["contracts"] = []

    result = collect_evidence_node(state)

    assert result["evidence_pack_saved"] is False
    assert "no contract" in str(result["evidence_pack_error"])
    assert mongo.packs == []


def test_the_graph_runs_the_node_after_the_capsules_exist() -> None:
    """The node must be IN the pipeline, not merely importable — and it
    must run AFTER the capsules are created.

    A collector that no graph edge reaches is a library, and the evidence
    pack would never be produced by a real run. And a pack assembled
    BEFORE the capsules exist would observe a world in which the run's
    own artifacts do not exist yet — the capsule object coordinates are
    the pipeline's own objects, and they come into being with the
    capsules.
    """
    from agent.graph import build_phase0_graph

    graph = build_phase0_graph()
    nodes = set(graph.get_graph().nodes)
    assert "collect_evidence" in nodes

    edges = {
        (e.source, e.target)
        for e in graph.get_graph().edges
    }
    assert ("create_capsule", "collect_evidence") in edges
    assert ("collect_evidence", "run_release_checks") in edges
    # And the differential's two moments still reach the collector.
    assert ("run_deep_experiments", "review_court") in edges
    assert ("review_court", "build_matrix") in edges
    assert ("build_matrix", "create_capsule") in edges
