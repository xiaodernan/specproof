"""Gate: every ``probe_expectation`` in a golden case must be *evaluable*.

``_load_probe_expectation`` reads it verbatim and ``evaluate_probe_expectation``
rejects unknown fields and wrong-typed expectation values as NON_REPRODUCIBLE —
which the eval then reports as "not measured", forever. That failure mode is
invisible: the case just never detects anything. This gate scans the repo's
golden cases and requires:

1. at least one probe_expectation exists (anti-vacuity);
2. contract_id / test_method are non-empty strings; severity is
   BLOCKER/MAJOR/MINOR;
3. base/head profiles are non-empty dicts whose keys are all known to the
   evaluator (_PROBE_KNOWN_FIELDS);
4. expectation value TYPES match the evaluator's isinstance checks
   (publish_count int, outcome str, payload_timestamp_non_null bool);
5. a synthesized artifact satisfying each profile round-trips to COMPLIANT
   through evaluate_probe_expectation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.nodes.run_differential import (
    _PROBE_KNOWN_FIELDS,
    evaluate_probe_expectation,
)

GOLDEN = Path(__file__).resolve().parents[2] / "golden-cases"

_FIELD_TYPES = {
    "publish_count": int,
    "outcome": str,
    "payload_timestamp_non_null": bool,
}


def _case_expectations() -> list[tuple[str, dict[str, Any]]]:
    found: list[tuple[str, dict[str, Any]]] = []
    for gt_file in sorted(GOLDEN.glob("*/ground-truth.json")):
        data = json.loads(gt_file.read_text(encoding="utf-8"))
        expectation = data.get("probe_expectation")
        if isinstance(expectation, dict):
            found.append((gt_file.parent.name, expectation))
    return found


def _artifact_satisfying(profile: dict[str, Any]) -> dict[str, Any]:
    publish_count = profile.get("publish_count", 1)
    outcome = profile.get("outcome", "success")
    if profile.get("payload_timestamp_non_null") is True:
        payloads: list[dict[str, Any]] = [{"timestamp": "2026-01-01T00:00:00Z"}]
    else:
        payloads = []
    return {
        "probe_version": 1,
        "publish_count": publish_count,
        "outcome": outcome,
        "payloads": payloads,
    }


def test_at_least_one_probe_expectation_exists() -> None:
    expectations = _case_expectations()
    assert expectations, "no golden case carries a probe_expectation"


def test_probe_expectations_are_evaluable() -> None:
    problems: list[str] = []
    for case, expectation in _case_expectations():
        contract_id = expectation.get("contract_id")
        test_method = expectation.get("test_method")
        severity = expectation.get("severity")
        if not isinstance(contract_id, str) or not contract_id.strip():
            problems.append(f"{case}: contract_id must be a non-empty string")
        if not isinstance(test_method, str) or not test_method.strip():
            problems.append(f"{case}: test_method must be a non-empty string")
        if severity not in ("BLOCKER", "MAJOR", "MINOR"):
            problems.append(f"{case}: severity {severity!r} not in BLOCKER/MAJOR/MINOR")
        for side in ("base", "head"):
            profile = expectation.get(side)
            if not isinstance(profile, dict) or not profile:
                problems.append(f"{case}: {side} profile must be a non-empty dict")
                continue
            unknown = sorted(set(profile) - set(_PROBE_KNOWN_FIELDS))
            if unknown:
                problems.append(f"{case}: {side} profile has unknown fields {unknown}")
            for field, value in profile.items():
                expected_type = _FIELD_TYPES.get(field)
                # bool IS an int subclass: isinstance(True, int) is True, so a
                # bool-typed expectation for publish_count passes isinstance(int).
                # The evaluator uses the same check, so mirror it exactly.
                if expected_type is not None and not isinstance(value, expected_type):
                    problems.append(
                        f"{case}: {side}.{field} expected {expected_type.__name__}, "
                        f"got {type(value).__name__}"
                    )
        # Round-trip: an artifact satisfying the profiles must judge COMPLIANT.
        base = expectation.get("base")
        head = expectation.get("head")
        if isinstance(base, dict) and isinstance(head, dict):
            verdict, detail, _violations = evaluate_probe_expectation(
                expectation, _artifact_satisfying(base), _artifact_satisfying(head)
            )
            if verdict != "COMPLIANT":
                problems.append(f"{case}: round-trip verdict {verdict} ({detail})")
    assert not problems, "\n".join(problems)
