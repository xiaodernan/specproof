"""The object-store collector: what the bucket ACTUALLY holds (P1-7).

The evidence pack and the capsules live in object storage. Until now
nothing in the evidence chain could say WHERE an object is: the bytes
were durable and the chain had no address for them.

The rules are the ones the other collectors already follow:

- **absence is recorded, never invented** — an object that is not there
  is ``present: false``, never an empty value and never "deleted";
- **the caller may not supply the verdict** — the collector describes
  what changed; whether that is bad is the Review Court's call;
- the dependencies arrive as arguments, so the whole thing runs without
  MinIO.
"""

from __future__ import annotations

from typing import Any

import pytest

from evidence.fragments import ObjectObservation
from experiments.collectors import (
    STATUS_AMBIGUOUS,
    STATUS_COMPLIANT,
    STATUS_NO_EVIDENCE,
    ObjectState,
    ObjectStateCollector,
)

BUCKET = "specproof"
REF = f"{BUCKET}/jobs/job-1/capsule.zip"


class FakeObjectStore:
    """An object-store double: holds bytes, or does not."""

    def __init__(self, objects: dict[str, dict[str, Any]] | None = None) -> None:
        self.objects = objects or {}
        self.unreachable = False

    def object_exists(self, bucket: str, object_name: str) -> bool:
        if self.unreachable:
            raise RuntimeError("minio unreachable")
        return f"{bucket}/{object_name}" in self.objects

    def object_stat(self, bucket: str, object_name: str) -> dict[str, Any]:
        if self.unreachable:
            raise RuntimeError("minio unreachable")
        return dict(self.objects[f"{bucket}/{object_name}"])


def _store(**objects: dict[str, Any]) -> FakeObjectStore:
    return FakeObjectStore({f"{BUCKET}/{name}": meta for name, meta in objects.items()})


def _meta(sha: str = "a" * 64, size: int = 10, ctype: str = "application/zip") -> dict[str, Any]:
    return {"size_bytes": size, "content_type": ctype, "sha256": sha}


# ── the snapshot ────────────────────────────────────────────────────────────


def test_a_present_object_is_observed_with_its_metadata() -> None:
    collector = ObjectStateCollector(_store(**{"jobs/job-1/capsule.zip": _meta()}))
    states = collector.snapshot([REF])
    state = states[REF]
    assert state.present is True
    assert state.bucket == BUCKET
    assert state.object_name == "jobs/job-1/capsule.zip"
    assert state.sha256 == "a" * 64
    assert state.size_bytes == 10
    assert state.content_type == "application/zip"


def test_a_missing_object_is_reported_as_absent_not_invented() -> None:
    collector = ObjectStateCollector(_store())
    states = collector.snapshot([REF])
    state = states[REF]
    assert state.present is False
    assert state.sha256 == "", "an absent object carries no digest"
    assert state.size_bytes == 0


def test_an_unreachable_store_is_absence_not_a_crash() -> None:
    """The store being down is a fact about the observation, not a bug.

    It is reported as "nothing was observed" — the fragment then says
    NO_EVIDENCE, which is the honest verdict for "we could not look".
    """
    store = _store(**{"jobs/job-1/capsule.zip": _meta()})
    store.unreachable = True
    collector = ObjectStateCollector(store)
    states = collector.snapshot([REF])
    assert states[REF].present is False


def test_a_reference_without_a_bucket_is_skipped() -> None:
    collector = ObjectStateCollector(_store())
    assert collector.snapshot(["no-bucket-here"]) == {}


# ── the comparison ──────────────────────────────────────────────────────────


def test_the_comparison_reports_what_changed() -> None:
    collector = ObjectStateCollector(_store())
    base = {
        REF: ObjectState(BUCKET, "jobs/job-1/capsule.zip", True, 10, "application/zip", "a" * 64),
        f"{BUCKET}/gone.zip": ObjectState(BUCKET, "gone.zip", True, 5, "application/zip", "b" * 64),
    }
    head = {
        REF: ObjectState(BUCKET, "jobs/job-1/capsule.zip", True, 11, "application/zip", "c" * 64),
        f"{BUCKET}/new.zip": ObjectState(BUCKET, "new.zip", True, 1, "application/zip", "d" * 64),
    }
    comparison = collector.compare(base, head)
    kinds = {entry["change"] for entry in comparison["changed"]}
    assert kinds == {"appeared", "disappeared", "content_changed"}
    assert comparison["changed_count"] == 3


def test_a_content_type_change_is_reported_separately() -> None:
    collector = ObjectStateCollector(_store())
    base = {REF: ObjectState(BUCKET, "x", True, 10, "application/zip", "a" * 64)}
    head = {REF: ObjectState(BUCKET, "x", True, 10, "text/plain", "a" * 64)}
    comparison = collector.compare(base, head)
    assert [e["change"] for e in comparison["changed"]] == ["content_type_changed"]


def test_two_absent_objects_are_not_a_change() -> None:
    """Nothing observed on either side is not a difference."""
    collector = ObjectStateCollector(_store())
    absent = {REF: ObjectState(BUCKET, "x", False)}
    assert collector.compare(absent, dict(absent))["changed_count"] == 0


# ── the fragment ────────────────────────────────────────────────────────────


def test_no_observation_is_no_evidence() -> None:
    collector = ObjectStateCollector(_store())
    states = collector.snapshot([REF])
    fragment = collector.fragment("exp-1", states, states)
    assert isinstance(fragment, ObjectObservation)
    assert fragment.fragment_type == "object"
    assert fragment.status == STATUS_NO_EVIDENCE
    assert fragment.confidence == 0.0


def test_an_unchanged_object_is_compliant() -> None:
    collector = ObjectStateCollector(_store(**{"jobs/job-1/capsule.zip": _meta()}))
    states = collector.snapshot([REF])
    fragment = collector.fragment("exp-1", states, states)
    assert fragment.status == STATUS_COMPLIANT
    assert fragment.comparison["changed_count"] == 0
    assert fragment.extension["observed_any_object"] is True


def test_a_changed_object_is_ambiguous_not_a_verdict() -> None:
    """The collector describes; it does not judge.

    AMBIGUOUS is the honest status for "the bytes differ" — whether that
    is a regression is the Review Court's decision, and a collector that
    answered on its own would be answering in the Court's name.
    """
    collector = ObjectStateCollector(_store())
    base = {REF: ObjectState(BUCKET, "x", True, 10, "application/zip", "a" * 64)}
    head = {REF: ObjectState(BUCKET, "x", True, 12, "application/zip", "b" * 64)}
    fragment = collector.fragment("exp-1", base, head)
    assert fragment.status == STATUS_AMBIGUOUS
    assert fragment.comparison["changed_count"] == 1
    assert fragment.comparison["changed"][0]["change"] == "content_changed"


def test_the_fragment_round_trips_through_the_schema() -> None:
    from evidence.fragments import EvidenceFragment

    collector = ObjectStateCollector(_store(**{"jobs/job-1/capsule.zip": _meta()}))
    states = collector.snapshot([REF])
    fragment = collector.fragment("exp-1", states, states)
    restored = EvidenceFragment.from_dict(fragment.to_dict())
    assert restored.to_dict() == fragment.to_dict()
    assert fragment.digest().startswith("sha256:")


@pytest.mark.parametrize(
    "ref",
    [f"{BUCKET}/jobs/job-1/capsule.zip"],
)
def test_the_address_is_the_object_coordinate(ref: str) -> None:
    """The fragment carries the address the bucket understands.

    A path is where the file WAS; the coordinate is where the bytes
    ARE. The chain needs the second one.
    """
    collector = ObjectStateCollector(_store(**{"jobs/job-1/capsule.zip": _meta()}))
    fragment = collector.fragment("exp-1", collector.snapshot([ref]), {})
    assert ref in fragment.base
    assert fragment.base[ref]["bucket"] == BUCKET
    assert fragment.base[ref]["object_name"] == "jobs/job-1/capsule.zip"
