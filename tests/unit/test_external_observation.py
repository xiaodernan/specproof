"""The external observation — one comparison, two readers (#365).

The evidence pack files the observation as a fragment; the matrix row
discloses what that observation could not say. Both must come from the
SAME comparison, or the reader ends up holding two versions of the
truth about what was seen on the outside of the JVM.

What is asserted here:

- nothing is invented: a contract that names no key family, or a run
  whose two moments were never captured, produces NO observation;
- the disclosed limits are the collectors' own facts (nothing observed,
  the world not put back, value-level leftovers, a truncated scan), and
  they are spoken in the reader's language;
- the matrix row and the evidence pack agree, because they are the same
  comparison — not two implementations that happen to agree today.
"""

from __future__ import annotations

from typing import Any

import pytest

from agent.external_observation import (
    LIMIT_MOMENTS_NOT_COMPARABLE,
    LIMIT_MQ_BROKER_SIDE,
    LIMIT_MQ_ONE_SIDE,
    LIMIT_NOT_OBSERVED,
    LIMIT_TRUNCATED,
    LIMIT_VALUE_LEVEL_LEFTOVERS,
    observation_for,
    observation_limits,
    observation_status,
    observations,
)
from agent.nodes.build_matrix import build_matrix_node
from agent.nodes.collect_evidence import collect_evidence_node

KEY = "user:cache:1"


def _moment(*, present: bool, value: str = "alice") -> dict[str, Any]:
    """One captured moment of the external world."""
    return {
        "redis": {
            KEY: {
                "key": KEY,
                "present": present,
                "value": value if present else None,
                "ttl_seconds": 60 if present else None,
            },
        },
        "objects": {},
    }


def _contract(**overrides: Any) -> dict[str, Any]:
    """A contract that DECLARES the key family it is about."""
    contract: dict[str, Any] = {
        "id": "CACHE-01",
        "checker_type": "redis",
        "requirement": (
            "the cached user entry must be evicted on write\n"
            "observes keys: user:cache:*"
        ),
    }
    contract.update(overrides)
    return contract


def _state(
    *,
    base: dict[str, Any] | None = None,
    head: dict[str, Any] | None = None,
    reset: dict[str, Any] | None = None,
    contracts: list[dict[str, Any]] | None = None,
    truncated: list[str] | None = None,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "job_id": "job-365-0001",
        "contracts": contracts if contracts is not None else [_contract()],
    }
    if base is not None:
        state["external_state_base"] = base
    if head is not None:
        state["external_state_head"] = head
    if reset is not None:
        state["external_reset"] = reset
    if truncated:
        for snapshot in (base, head):
            if snapshot is not None:
                snapshot["truncated_patterns"] = list(truncated)
    return state


# ── nothing is invented ───────────────────────────────────────────────────


def test_a_run_without_the_two_moments_produces_no_observation() -> None:
    """No moments -> no comparison. "Not observed" is not "unchanged"."""
    state = _state()
    assert observation_for(state, _contract()) is None
    assert observations(state) == {}


def test_a_contract_that_names_no_key_family_is_not_observed() -> None:
    """Guessing a key family for a contract that names none would invent
    evidence — so there is no observation at all."""
    state = _state(
        base=_moment(present=True),
        head=_moment(present=True),
        contracts=[_contract(requirement="the order must be created")],
    )
    assert observation_for(state, _contract(
        requirement="the order must be created",
    )) is None
    assert observations(state) == {}


def test_a_contract_without_an_id_is_not_observed() -> None:
    state = _state(
        base=_moment(present=True),
        head=_moment(present=True),
        contracts=[_contract(id="")],
    )
    assert observations(state) == {}


# ── the limits, in the reader's language ──────────────────────────────────


def test_an_unchanged_observation_declares_no_limit() -> None:
    state = _state(
        base=_moment(present=True),
        head=_moment(present=True),
        reset={"reset": True, "keys_modified_by_base": []},
    )
    observation = observation_for(state, _contract())
    assert observation is not None
    assert observation_status(observation) == "COMPLIANT"
    assert observation_limits(observation) == []


def test_value_level_leftovers_are_disclosed() -> None:
    """The keys the Base run only CHANGED still carry its value: the
    comparison can speak about presence and TTL, not about the value."""
    state = _state(
        base=_moment(present=True),
        head=_moment(present=True),
        reset={"reset": True, "keys_modified_by_base": [KEY]},
    )
    observation = observation_for(state, _contract())
    assert observation is not None
    limits = observation_limits(observation)
    assert LIMIT_VALUE_LEVEL_LEFTOVERS.format(count=1) in limits


def test_an_unreset_world_is_disclosed() -> None:
    """Without the world being put back, a key the Base created reads as
    unchanged — a different fact, and the reader has to know it."""
    state = _state(
        base=_moment(present=True),
        head=_moment(present=True),
        reset={},
    )
    observation = observation_for(state, _contract())
    assert observation is not None
    assert LIMIT_MOMENTS_NOT_COMPARABLE in observation_limits(observation)


def test_a_truncated_scan_is_disclosed() -> None:
    state = _state(
        base=_moment(present=True),
        head=_moment(present=True),
        reset={"reset": True},
        truncated=["user:cache:*"],
    )
    observation = observation_for(state, _contract())
    assert observation is not None
    assert LIMIT_TRUNCATED.format(count=1) in observation_limits(observation)


def test_nothing_observed_is_disclosed() -> None:
    """The store answered, and the family was empty: that is NO_EVIDENCE,
    and it reads differently from "the collector ran and found nothing"."""
    state = _state(
        base=_moment(present=False),
        head=_moment(present=False),
        reset={"reset": True},
    )
    observation = observation_for(state, _contract())
    assert observation is not None
    assert observation_status(observation) == "NO_EVIDENCE"
    assert LIMIT_NOT_OBSERVED in observation_limits(observation)


def test_no_observation_declares_no_limit() -> None:
    """None is not "an observation without limits" — the caller has to
    say the two apart."""
    assert observation_limits(None) == []
    assert observation_status(None) == ""


# ── the verdict layer reads it ────────────────────────────────────────────


def _row(state: dict[str, Any], contract_id: str = "CACHE-01") -> dict[str, Any]:
    matrix = build_matrix_node(state)["matrix"]  # type: ignore[arg-type]
    return next(r for r in matrix["rows"] if r["contract_id"] == contract_id)


def test_the_matrix_row_carries_the_disclosed_limits() -> None:
    state = _state(
        base=_moment(present=True),
        head=_moment(present=True),
        reset={"reset": True, "keys_modified_by_base": [KEY]},
    )
    row = _row(state)
    assert row["observation_status"] == "COMPLIANT"
    assert LIMIT_VALUE_LEVEL_LEFTOVERS.format(count=1) in row["observation_limits"]


def test_the_matrix_row_is_blank_when_nothing_was_observed() -> None:
    """Blank, not missing: every row carries the fields, and an absent
    observation reads as an empty status rather than a fabricated one."""
    row = _row(_state())
    assert row["observation_status"] == ""
    assert row["observation_limits"] == []


def test_the_row_never_changes_the_verdict() -> None:
    """The disclosure qualifies the verdict; it never decides it."""
    state = _state(
        base=_moment(present=True),
        head=_moment(present=True),
        reset={"reset": True, "keys_modified_by_base": [KEY]},
    )
    row = _row(state)
    assert row["result"] in {"UNVERIFIED", "PASS", "FAIL"}
    assert row["observation_limits"]


# ── the pack and the row are the same comparison ──────────────────────────


class _RecordingMongo:
    """A MongoDB double: records the packs it was asked to save."""

    def __init__(self) -> None:
        self.packs: list[dict[str, Any]] = []

    def save_evidence_pack(self, pack: dict[str, Any]) -> str:
        self.packs.append(pack)
        return "pack-id"


def _stub_mongo(monkeypatch: pytest.MonkeyPatch) -> _RecordingMongo:
    recorder = _RecordingMongo()

    class _MongoFactory:
        def __init__(self) -> None:
            self.save_evidence_pack = recorder.save_evidence_pack

    monkeypatch.setattr(
        "storage.mongodb.MongoDBStore", lambda *a, **k: _MongoFactory()
    )
    return recorder


def test_the_pack_and_the_matrix_row_agree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One comparison, two readers: the fragment the pack files and the
    limits the row shows come from the same observation."""
    mongo = _stub_mongo(monkeypatch)
    state = _state(
        base=_moment(present=True),
        head=_moment(present=True, value="bob"),
        reset={"reset": True, "keys_modified_by_base": [KEY]},
    )
    collect_evidence_node(state)  # type: ignore[arg-type]
    assert mongo.packs, "the pack was not written — nothing to compare"

    fragments = mongo.packs[0]["fragments"]
    redis = next(f for f in fragments if f["fragment_type"] == "redis")
    row = _row(state)
    assert redis["extension"]["value_level_leftover_count"] == 1
    assert LIMIT_VALUE_LEVEL_LEFTOVERS.format(count=1) in row["observation_limits"]
    assert row["observation_status"] == redis["status"]


# ── the disclosure reaches the reader ─────────────────────────────────────


def test_the_summary_carries_the_observation_to_the_api() -> None:
    """The row is not enough: the persisted summary is what the coverage
    page reads, so the disclosure has to travel with it."""
    from agent.worker import _matrix_rows_for_summary

    state = _state(
        base=_moment(present=True),
        head=_moment(present=True),
        reset={"reset": True, "keys_modified_by_base": [KEY]},
    )
    matrix = build_matrix_node(state)["matrix"]  # type: ignore[arg-type]
    summary = _matrix_rows_for_summary(matrix)
    assert summary["matrix_rows"]
    row = summary["matrix_rows"][0]
    assert row["observation_status"] == "COMPLIANT"
    assert LIMIT_VALUE_LEVEL_LEFTOVERS.format(count=1) in row["observation_limits"]


# ── the MQ surface: the broker is not observable, the test's report is ───

MQ_REPORT = (
    "SPECPROOF_MQ routing_key=email.changed "
    "exchange=specproof.demo.events publishes=1"
)
MQ_REPORT_NONE = (
    "SPECPROOF_MQ routing_key=email.changed "
    "exchange=specproof.demo.events publishes=0"
)


def _mq_contract(**overrides: Any) -> dict[str, Any]:
    contract: dict[str, Any] = {
        "id": "EVENT-01",
        "checker_type": "rabbitmq",
        "requirement": "email.changed must reach the documented exchange",
    }
    contract.update(overrides)
    return contract


def _mq_state(*, base_output: str = "", head_output: str = "") -> dict[str, Any]:
    """A state whose differential captured the test's output."""
    return {
        "job_id": "job-366-0001",
        "contracts": [_mq_contract()],
        # The two moments are there so the pack has an object fragment to
        # file under; the MQ observation does not depend on them.
        "external_state_base": {"redis": {}, "objects": {}},
        "external_state_head": {"redis": {}, "objects": {}},
        "diff_results": [{
            "contract_id": "EVENT-01",
            "base_output": base_output,
            "head_output": head_output,
        }],
    }


def test_the_test_report_is_recorded_as_the_observation() -> None:
    """The publish happens inside the test's JVM, but the test REPORTS
    what it counted — and that report is what the fragment carries."""
    observation = observation_for(
        _mq_state(base_output=MQ_REPORT, head_output=MQ_REPORT),
        _mq_contract(),
    )
    assert observation is not None
    assert observation.fragment_type == "mq"
    assert observation.base["publish_count"] == 1
    assert observation.base["routing_keys"] == ["email.changed"]
    assert observation.head["publish_count"] == 1
    assert observation_status(observation) == "COMPLIANT"


def test_a_head_that_published_nothing_is_ambiguous() -> None:
    observation = observation_for(
        _mq_state(base_output=MQ_REPORT, head_output=MQ_REPORT_NONE),
        _mq_contract(),
    )
    assert observation is not None
    assert observation_status(observation) == "AMBIGUOUS"
    assert observation.comparison["changed"][0]["change"] == "publish_count_changed"


def test_a_test_that_reported_nothing_is_no_evidence() -> None:
    observation = observation_for(_mq_state(), _mq_contract())
    assert observation is not None
    assert observation_status(observation) == "NO_EVIDENCE"
    assert observation.extension["observed_any_publish"] is False


def test_the_broker_side_gap_is_stated_on_every_mq_observation() -> None:
    """The broker side is STILL not observed. The fragment says what it
    does carry (the test's report) and what it cannot (the broker)."""
    observation = observation_for(
        _mq_state(base_output=MQ_REPORT, head_output=MQ_REPORT),
        _mq_contract(),
    )
    assert observation is not None
    assert LIMIT_MQ_BROKER_SIDE in observation_limits(observation)
    assert "broker" in observation.extension["not_observable_reason"]
    assert "test's own report" in observation.extension["observed_via"]


def test_a_one_sided_report_is_disclosed() -> None:
    observation = observation_for(
        _mq_state(base_output=MQ_REPORT), _mq_contract(),
    )
    assert observation is not None
    assert LIMIT_MQ_ONE_SIDE in observation_limits(observation)
    assert observation.extension["both_sides_observed"] is False


def test_the_matrix_row_discloses_the_mq_gap() -> None:
    state = _mq_state(base_output=MQ_REPORT, head_output=MQ_REPORT)
    row = _row(state, "EVENT-01")
    assert row["observation_status"] == "COMPLIANT"
    assert LIMIT_MQ_BROKER_SIDE in row["observation_limits"]


def test_the_pack_and_the_row_agree_on_the_mq_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mongo = _stub_mongo(monkeypatch)
    state = _mq_state(base_output=MQ_REPORT, head_output=MQ_REPORT)
    collect_evidence_node(state)  # type: ignore[arg-type]
    fragment = next(
        f for f in mongo.packs[0]["fragments"] if f["fragment_type"] == "mq"
    )
    row = _row(state, "EVENT-01")
    assert fragment["base"]["publish_count"] == 1
    assert row["observation_status"] == fragment["status"]
    assert LIMIT_MQ_BROKER_SIDE in row["observation_limits"]


def test_the_html_report_shows_the_limits() -> None:
    """A reader who sees PASS in the report must be able to see how far
    the external observation backs it."""
    from evidence.report import render_verification_report

    state = _state(
        base=_moment(present=True),
        head=_moment(present=True),
        reset={"reset": True, "keys_modified_by_base": [KEY]},
    )
    matrix = build_matrix_node(state)["matrix"]  # type: ignore[arg-type]
    html = render_verification_report(
        "repo", "base", "head", matrix, [], generated_at="2026-01-01 00:00:00 UTC",
    )
    assert "值层面无法区分" in html
