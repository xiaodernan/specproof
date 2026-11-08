"""Boundary tests for ``evaluate_probe_expectation`` / ``_probe_field_ok``.

The happy paths and the per-case regressions (#97/#98/#100) are locked in
``test_probe_differential.py``. This file pins the semantics that decide
whether a *type-strictness* failure reads as "case never measured"
(NON_REPRODUCIBLE) or as "head violates its profile" (REGRESSION), plus the
empty-payloads rule: a zero-payload artifact is never "all timestamps
non-null", even though ``all()`` over an empty iterable is vacuously true.
"""

from __future__ import annotations

from agent.nodes.run_differential import evaluate_probe_expectation


def _payload(timestamp: str | None = "2026-01-01T00:00:00Z") -> dict[str, object]:
    return {
        "exchange": "specproof.demo.events",
        "routingKey": "order.created",
        "type": "OrderCreatedEvent",
        "timestamp": timestamp,
    }


def _artifact(
    publish_count: int,
    outcome: str = "success",
    payloads: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    if payloads is None:
        payloads = [_payload() for _ in range(publish_count)]
    return {
        "probe_version": 1,
        "publish_count": publish_count,
        "outcome": outcome,
        "payloads": payloads,
    }


# ── expectation type-strictness: base side fails closed ───────────────────


def test_base_publish_count_expectation_of_wrong_type_is_non_reproducible() -> None:
    expectation = {"base": {"publish_count": "1"}, "head": {"publish_count": 1}}
    verdict, _detail, violations = evaluate_probe_expectation(
        expectation, _artifact(1), _artifact(1)
    )
    assert verdict == "NON_REPRODUCIBLE"
    assert violations == ["publish_count"]


def test_base_outcome_expectation_of_wrong_type_is_non_reproducible() -> None:
    expectation = {"base": {"outcome": 200}, "head": {"outcome": "success"}}
    verdict, _detail, violations = evaluate_probe_expectation(
        expectation, _artifact(1), _artifact(1)
    )
    assert verdict == "NON_REPRODUCIBLE"
    assert violations == ["outcome"]


def test_base_payload_timestamp_expectation_must_be_bool() -> None:
    expectation = {
        "base": {"payload_timestamp_non_null": 1},
        "head": {"payload_timestamp_non_null": True},
    }
    verdict, _detail, violations = evaluate_probe_expectation(
        expectation, _artifact(1), _artifact(1)
    )
    assert verdict == "NON_REPRODUCIBLE"
    assert violations == ["payload_timestamp_non_null"]


# ── expectation type-strictness: head side is a REGRESSION ──────────────────


def test_head_publish_count_expectation_of_wrong_type_is_regression() -> None:
    expectation = {"base": {"publish_count": 1}, "head": {"publish_count": "1"}}
    verdict, _detail, violations = evaluate_probe_expectation(
        expectation, _artifact(1), _artifact(1)
    )
    assert verdict == "REGRESSION"
    assert violations == ["publish_count"]


def test_head_outcome_expectation_of_wrong_type_is_regression() -> None:
    expectation = {"base": {"outcome": "success"}, "head": {"outcome": 0}}
    verdict, _detail, violations = evaluate_probe_expectation(
        expectation, _artifact(1), _artifact(1)
    )
    assert verdict == "REGRESSION"
    assert violations == ["outcome"]


def test_head_payload_timestamp_expectation_must_be_bool() -> None:
    expectation = {
        "base": {"payload_timestamp_non_null": True},
        "head": {"payload_timestamp_non_null": 1},
    }
    verdict, _detail, violations = evaluate_probe_expectation(
        expectation, _artifact(1), _artifact(1)
    )
    assert verdict == "REGRESSION"
    assert violations == ["payload_timestamp_non_null"]


# ── empty payloads are never "all timestamps non-null" ──────────────────────


def test_empty_payloads_violate_a_true_timestamp_expectation() -> None:
    expectation = {
        "base": {"payload_timestamp_non_null": False},
        "head": {"payload_timestamp_non_null": True},
    }
    verdict, _detail, violations = evaluate_probe_expectation(
        expectation,
        _artifact(0, payloads=[]),
        _artifact(0, payloads=[]),
    )
    assert verdict == "REGRESSION"
    assert violations == ["payload_timestamp_non_null"]


def test_empty_payloads_satisfy_a_false_timestamp_expectation() -> None:
    expectation = {
        "base": {"payload_timestamp_non_null": False},
        "head": {"payload_timestamp_non_null": False},
    }
    verdict, detail, violations = evaluate_probe_expectation(
        expectation,
        _artifact(0, payloads=[]),
        _artifact(0, payloads=[]),
    )
    assert verdict == "COMPLIANT"
    assert violations == []
    assert detail


# ── missing-artifact attribution ─────────────────────────────────────────────


def test_head_missing_artifact_reports_head_not_base() -> None:
    expectation = {"base": {"publish_count": 1}, "head": {"publish_count": 1}}
    verdict, detail, _violations = evaluate_probe_expectation(
        expectation, _artifact(1), None
    )
    assert verdict == "NON_REPRODUCIBLE"
    assert "head" in detail
    assert "base" not in detail


def test_both_sides_missing_report_both() -> None:
    expectation = {"base": {"publish_count": 1}, "head": {"publish_count": 1}}
    verdict, detail, _violations = evaluate_probe_expectation(expectation, None, None)
    assert verdict == "NON_REPRODUCIBLE"
    assert "base and head" in detail


# ── mixed head violations stay head-only ──────────────────────────────────────


def test_multiple_head_violations_exclude_base_and_are_named() -> None:
    expectation = {
        "base": {"publish_count": 1, "outcome": "success"},
        "head": {"publish_count": 3, "outcome": "rejected"},
    }
    verdict, detail, violations = evaluate_probe_expectation(
        expectation,
        _artifact(1, "success"),
        _artifact(2, "accepted"),
    )
    assert verdict == "REGRESSION"
    assert set(violations) == {"publish_count", "outcome"}
    assert "publish_count" in detail and "outcome" in detail


# ── base violations outrank head violations ────────────────────────────────────


def test_base_violation_takes_precedence_over_head_violation() -> None:
    expectation = {
        "base": {"publish_count": 1},
        "head": {"publish_count": 2},
    }
    verdict, detail, violations = evaluate_probe_expectation(
        expectation, _artifact(3), _artifact(9)
    )
    assert verdict == "NON_REPRODUCIBLE"
    assert violations == ["publish_count"]
    assert "base" in detail
