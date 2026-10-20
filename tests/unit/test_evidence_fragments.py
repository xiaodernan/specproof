"""Evidence Fragment schema tests (Phase 2, P2-1).

The fragment is the unit the evidence chain is built from: one experiment,
one observation, one honest comparison. These tests pin the properties
the chain depends on:

- round-trip fidelity (a fragment survives dict → object → dict);
- the digest covers the content and is stable across key order;
- a fragment that was never observed says so instead of carrying an
  invented base or head;
- the specific observation types are usable as fragments.
"""

from __future__ import annotations

import json

import pytest

from evidence.fragments import (
    BuildObservation,
    DbObservation,
    EvidenceFragment,
    HttpObservation,
    MqObservation,
    PerformanceObservation,
    RedisObservation,
    SchemaObservation,
    StaticObservation,
)


def _fragment(**overrides: object) -> EvidenceFragment:
    base: dict[str, object] = {
        "experiment_id": "exp-1",
        "fragment_type": "http",
        "collector_version": "1.0.0",
        "collected_at": "2026-10-20T00:00:00.000Z",
        "base": {"status": 401, "body": "unauthorized"},
        "head": {"status": 200, "body": "ok"},
        "normalization": {"ignored_fields": ["timestamp"]},
        "comparison": {"changed": ["status", "body"]},
        "status": "REGRESSION",
        "confidence": 0.95,
        "evidence_ref": "minio://tenant/repo/job/http/1",
        "reproducibility": "reproducible",
    }
    base.update(overrides)
    return EvidenceFragment(**base)  # type: ignore[arg-type]


# ── the contract ───────────────────────────────────────────────────────────


def test_fragment_carries_every_contract_field() -> None:
    fragment = _fragment()
    payload = fragment.to_dict()
    for key in (
        "experiment_id",
        "fragment_type",
        "collector_version",
        "collected_at",
        "base",
        "head",
        "normalization",
        "comparison",
        "status",
        "confidence",
        "evidence_ref",
        "reproducibility",
    ):
        assert key in payload, f"missing {key}"


def test_round_trip_preserves_everything() -> None:
    fragment = _fragment()
    restored = EvidenceFragment.from_dict(fragment.to_dict())
    assert restored.to_dict() == fragment.to_dict()


def test_round_trip_survives_json() -> None:
    fragment = _fragment()
    restored = EvidenceFragment.from_dict(json.loads(json.dumps(fragment.to_dict())))
    assert restored.to_dict() == fragment.to_dict()


def test_digest_is_stable_across_key_order() -> None:
    """The digest is a canonical digest — key order cannot change it."""
    fragment = _fragment()
    shuffled = dict(reversed(list(fragment.to_dict().items())))
    restored = EvidenceFragment.from_dict(shuffled)
    assert restored.digest() == fragment.digest()


def test_digest_changes_when_content_changes() -> None:
    base = _fragment()
    head = _fragment(head={"status": 403, "body": "forbidden"})
    assert base.digest() != head.digest()


# ── honesty ────────────────────────────────────────────────────────────────


def test_unobserved_side_is_none_not_invented() -> None:
    """A side that was never observed is None — never a plausible value."""
    fragment = _fragment(base=None, status="NO_EVIDENCE", confidence=0.0)
    payload = fragment.to_dict()
    assert payload["base"] is None
    assert payload["status"] == "NO_EVIDENCE"
    assert payload["confidence"] == 0.0


def test_unjudged_fragment_survives_the_round_trip() -> None:
    fragment = _fragment(base=None, head=None, status="NON_REPRODUCIBLE")
    restored = EvidenceFragment.from_dict(fragment.to_dict())
    assert restored.base is None
    assert restored.head is None
    assert restored.status == "NON_REPRODUCIBLE"


def test_extension_defaults_to_empty_dict() -> None:
    fragment = _fragment()
    assert fragment.to_dict()["extension"] == {}


def test_extension_is_carried_verbatim() -> None:
    fragment = _fragment(extension={"probe": "target/specproof-probe.json"})
    restored = EvidenceFragment.from_dict(fragment.to_dict())
    assert restored.extension == {"probe": "target/specproof-probe.json"}


# ── the observation types ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "cls",
    [
        HttpObservation,
        DbObservation,
        RedisObservation,
        MqObservation,
        SchemaObservation,
        PerformanceObservation,
        StaticObservation,
        BuildObservation,
    ],
)
def test_observation_types_are_usable_fragments(cls: type) -> None:
    """Each observation type is a fragment — same contract, same digest."""
    fragment = cls(
        experiment_id="exp-2",
        fragment_type="typed",
        collector_version="1.0.0",
        collected_at="2026-10-20T00:00:00.000Z",
        base={"v": 1},
        head={"v": 2},
        normalization=None,
        comparison=None,
        status="REGRESSION",
    )
    assert isinstance(fragment, EvidenceFragment)
    assert fragment.digest().startswith("sha256:")
    assert EvidenceFragment.from_dict(fragment.to_dict()).to_dict() == fragment.to_dict()


def test_observation_types_keep_their_own_type_identity() -> None:
    """A DbObservation is a DbObservation — the subclass is not erased."""
    fragment = DbObservation(
        experiment_id="exp-3",
        fragment_type="db",
        collector_version="1.0.0",
        collected_at="2026-10-20T00:00:00.000Z",
        base={"rows": 1},
        head={"rows": 0},
        normalization=None,
        comparison=None,
        status="REGRESSION",
    )
    assert type(fragment) is DbObservation
    assert fragment.to_dict()["fragment_type"] == "db"
