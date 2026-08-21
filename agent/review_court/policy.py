"""Deterministic Review Court policy layer.

The Review Court is split in two (master plan §14.1):

* The model layer (agent/nodes/review_court.py) only produces defense
  material and candidate confidence — it never decides severity or status.
* This module is the deterministic policy layer. policy_recalculate
  recomputes severity and status from evidence kinds, confidence ceilings
  and the Base/Head runtime comparison. It is pure: no I/O, no randomness,
  same inputs -> same outputs.

Policies enforced, in order:

1. Parse failures of model output never auto-confirm: affected candidates
   become needs_confirmation.
2. NON_REPRODUCIBLE evidence is bookkeeping, never confirmed.
3. Static/source-diff evidence is capped at MAJOR with confidence ≤ 0.85.
4. Preexisting-defect rule: when the linked runtime experiment shows Base
   ALSO fails (base_exit_code ≠ 0 and head_exit_code ≠ 0), the finding is
   downgraded to NOT_ATTRIBUTED / INFORMATIONAL unless a distinct head-only
   behavioral difference exists (different failure signature, head-only DB
   mutation, extra head failures, different exit code). The comparison is
   recorded in the audit entry.
5. BLOCKER six-conditions (ADR-004), byte-compatible with the pre-split
   rule-based court: approved contract + real Base/Head execution evidence +
   attribution to Head + DB/behavioral evidence + capsule replayability +
   confidence ≥ 0.90. A BLOCKER missing any condition is capped at MAJOR.

Model-ignored candidates are always policy-evaluated and recorded in the
audit trail; the model may supply arguments, never verdicts.
"""
import hashlib
import json
from typing import Any, TypedDict

# ── Evidence policy constants (P0.5, ADR-004) ──────────────────────────

BLOCKER_REQUIRED_EVIDENCE_TYPES = frozenset({
    "base_pass_head_fail",
    "differential_execution",
})

NON_BLOCKER_EVIDENCE_TYPES = frozenset({
    "static_regex_analysis",
    "static_analysis",
    "java_source_diff",
    "heuristic",
})

STATIC_CONFIDENCE_CEILING = 0.85
DOWNGRADED_BLOCKER_CONFIDENCE_CEILING = 0.88

NOT_ATTRIBUTED_STATUS = "not_attributed"
NOT_ATTRIBUTED_SEVERITY = "INFORMATIONAL"
NOT_ATTRIBUTED_CONFIDENCE_CEILING = 0.5

POLICY_VERSION = "review-court-policy-v2"

# ── Model layer contract ────────────────────────────────────────────────


class DefenseMaterial(TypedDict):
    """One candidate's defense material produced by the model layer."""

    id: str
    defense_argument: str
    candidate_confidence: float | None
    is_false_positive: bool | None


class ModelDefenseOutput(TypedDict):
    """Structured output of an injected model_produce_defense callable.

    parse_failed marks a model response that could not be parsed at all;
    the policy layer turns that into needs_confirmation, never confirmation.
    A non-empty error degrades to the fully deterministic path.
    """

    defense_materials: list[DefenseMaterial]
    parse_failed: bool
    error: str


# ── Base/Head behavior comparison (preexisting-defect rule) ────────────

_FAILURE_MARKERS = (
    "AssertionError",
    "AssertionFailedError",
    "ComparisonFailure",
    "expected",
    "but was",
    "Exception",
    "FAILED",
)


def _failure_signature(output: str) -> str:
    """Extract a normalized failure signature from a test-run output tail.

    Deterministic: only lines carrying assertion/exception markers are kept,
    whitespace is normalized, and at most the first 8 lines are compared.
    An empty signature means the output carried no recognizable failure.
    """
    kept: list[str] = []
    for raw_line in output.splitlines():
        line = " ".join(raw_line.split())
        if not line:
            continue
        if any(marker in line for marker in _FAILURE_MARKERS):
            kept.append(line)
    return " || ".join(kept[:8])


def _failure_count(test_counts: Any) -> int:
    if not isinstance(test_counts, dict):
        return 0
    return int(test_counts.get("failures", 0) or 0) + int(
        test_counts.get("errors", 0) or 0
    )


def _db_rows(snapshot: Any) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {}
    rows = snapshot.get("rows")
    if not isinstance(rows, dict):
        return {}
    return rows


def _head_only_behavior_difference(record: dict[str, Any]) -> dict[str, Any]:
    """Decide whether a both-sides-fail run shows a NEW head-only difference.

    Signals (any one is enough to keep attribution to Head):
    - different nonzero exit codes (different failure mechanics);
    - different failure signature in the output tails (different exception,
      different expected/actual values);
    - more failures/errors in the Head test counts (extra head failures);
    - different persisted DB rows (head-only side effect).
    No signal -> the failure is indistinguishable from the Base failure and
    must not be attributed to Head.
    """
    signals: list[str] = []

    base_exit = record.get("base_exit_code")
    head_exit = record.get("head_exit_code")
    if (
        isinstance(base_exit, int)
        and isinstance(head_exit, int)
        and base_exit != head_exit
    ):
        signals.append("exit_code_differs")

    base_sig = _failure_signature(str(record.get("base_output", "")))
    head_sig = _failure_signature(str(record.get("head_output", "")))
    if base_sig and head_sig and base_sig != head_sig:
        signals.append("failure_signature_differs")

    base_count = _failure_count(record.get("base_test_counts"))
    head_count = _failure_count(record.get("head_test_counts"))
    if head_count > base_count:
        signals.append("head_extra_failure_count")

    base_rows = _db_rows(record.get("base_db_snapshot"))
    head_rows = _db_rows(record.get("head_db_snapshot"))
    if base_rows and head_rows and base_rows != head_rows:
        signals.append("head_db_state_differs")

    return {"distinct": bool(signals), "signals": signals}


def _linked_runtime_records(
    candidate: dict[str, Any], diff_results: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Runtime evidence records linked to a candidate.

    A differential candidate owns exactly one record (diff_result_index, or
    its own embedded runtime fields). A static candidate is linked by
    contract_id to every runtime record of the same contract.
    """
    index = candidate.get("diff_result_index")
    if isinstance(index, int) and 0 <= index < len(diff_results):
        return [diff_results[index]]
    if candidate.get("base_exit_code") is not None:
        return [candidate]
    contract_id = candidate.get("contract_id", "")
    if not contract_id:
        return []
    return [dr for dr in diff_results if dr.get("contract_id") == contract_id]


def _preexisting_check(
    candidate: dict[str, Any], diff_results: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Check the preexisting-defect rule against linked runtime evidence.

    Returns None when the rule does not apply (no linked record proves Base
    also failed). Returns the full comparison otherwise; the caller
    downgrades when head_only_difference is False.
    """
    for record in _linked_runtime_records(candidate, diff_results):
        base_exit = record.get("base_exit_code")
        head_exit = record.get("head_exit_code")
        if base_exit is None or head_exit is None:
            continue
        if base_exit == 0 or head_exit == 0:
            # Base passed (head-only failure) or Head fixed it — the
            # preexisting-defect rule does not apply.
            continue
        behavior = _head_only_behavior_difference(record)
        return {
            "applicable": True,
            "contract_id": record.get("contract_id", ""),
            "verdict": record.get("verdict", ""),
            "evidence_digest": record.get("evidence_digest", ""),
            "base_exit_code": base_exit,
            "head_exit_code": head_exit,
            "base_failure_signature": _failure_signature(
                str(record.get("base_output", ""))
            ),
            "head_failure_signature": _failure_signature(
                str(record.get("head_output", ""))
            ),
            "head_only_difference": behavior["distinct"],
            "head_only_signals": behavior["signals"],
        }
    return None


# ── P0.5 six-condition BLOCKER check (byte-compatible) ─────────────────


def _has_real_execution_evidence(diff_results: list[dict[str, Any]]) -> bool:
    """Real execution evidence = a recorded base/head run with exit codes.

    A bare evidence-type string is not evidence; the run must carry the
    recorded exit codes that prove both sides actually executed.
    """
    for dr in diff_results:
        has_exits = "base_exit_code" in dr and "head_exit_code" in dr
        if dr.get("evidence_type") == "base_pass_head_fail" and has_exits:
            return True
        if (
            dr.get("evidence_type") == "differential_execution"
            and dr.get("verdict") == "REGRESSION"
            and has_exits
        ):
            return True
    return False


def _check_blocker_conditions(
    finding: dict[str, Any],
    contracts: list[dict[str, Any]],
    diff_results: list[dict[str, Any]],
    generated_tests_path: str,
    changed_files: list[str],
) -> dict[str, Any]:
    """Check all 6 BLOCKER conditions against real recorded evidence."""
    evidence_type = finding.get("evidence_type", "")
    contract_id = finding.get("contract_id", "")

    conditions = {
        "1_approved_contract": False,
        "2_base_head_execution": False,
        "3_attribution_to_head": False,
        "4_db_behavior_evidence": False,
        "5_capsule_replayable": False,
        "6_confidence_090": False,
    }

    conditions["1_approved_contract"] = (
        any(
            c.get("id") == contract_id and c.get("approved", True)
            for c in contracts
        )
        if contract_id else False
    )

    conditions["2_base_head_execution"] = (
        evidence_type in BLOCKER_REQUIRED_EVIDENCE_TYPES
        and _has_real_execution_evidence(diff_results)
    )

    location = finding.get("location", "")
    conditions["3_attribution_to_head"] = bool(
        location
        and any(location in cf for cf in changed_files)
    ) or evidence_type == "base_pass_head_fail"

    conditions["4_db_behavior_evidence"] = (
        finding.get("db_state_verdict") in ("DB_MUTATED_ON_UNAUTH", "DB_MUTATED")
        or any(
            dr.get("db_state_verdict") in ("DB_MUTATED_ON_UNAUTH", "DB_MUTATED")
            for dr in diff_results
        )
    )

    conditions["5_capsule_replayable"] = (
        evidence_type in BLOCKER_REQUIRED_EVIDENCE_TYPES
        and bool(generated_tests_path)
    )

    conditions["6_confidence_090"] = finding.get("confidence", 0) >= 0.90

    all_met = all(conditions.values())
    return {
        "blocker_conditions": conditions,
        "all_blocker_conditions_met": all_met,
    }


# ── Shared helpers ──────────────────────────────────────────────────────


def _dedup_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge candidates that report the same (contract, type) keeping the strongest."""
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for c in candidates:
        key = (c.get("contract_id", ""), c.get("type", ""))
        existing = merged.get(key)
        if existing is None:
            merged[key] = dict(c)
            continue
        if c.get("confidence", 0) > existing.get("confidence", 0):
            merged[key] = dict(c)
        # Merge evidence notes from the weaker duplicate.
        desc = existing.get("description", "")
        if c.get("description") and c.get("description") not in desc:
            existing["description"] = desc + " | " + c["description"]
    return list(merged.values())


def _evidence_digest(
    finding_id: str, evidence_type: str, severity: Any, confidence: Any
) -> str:
    """Deterministic evidence digest (same payload as the legacy court)."""
    payload = json.dumps({
        "id": finding_id,
        "evidence_type": evidence_type,
        "severity": severity,
        "confidence": confidence,
    }, sort_keys=True)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def _model_material_by_id(
    model_output: ModelDefenseOutput | None,
) -> dict[str, DefenseMaterial]:
    if model_output is None:
        return {}
    materials: dict[str, DefenseMaterial] = {}
    for item in model_output.get("defense_materials", []):
        fid = str(item.get("id", "")).upper()
        if fid:
            materials[fid] = item
    return materials


# ── The pure policy function ────────────────────────────────────────────


def policy_recalculate(
    candidates: list[dict[str, Any]],
    model_output: ModelDefenseOutput | None = None,
    contracts: list[dict[str, Any]] | None = None,
    diff_results: list[dict[str, Any]] | None = None,
    generated_tests_path: str = "",
    changed_files: list[str] | None = None,
) -> dict[str, Any]:
    """Recompute severity/status for every candidate from evidence only.

    The model layer output can contribute defense arguments and a candidate
    confidence (clamped by the evidence-kind ceilings) but never a verdict,
    severity or status. Returns:

    - candidate_findings: finalized candidates (legacy rule-based shape).
    - confirmed_findings: deduplicated confirmed/needs_confirmation findings.
    - audit_entries: one entry per candidate — including model-ignored
      candidates, parse-failure outcomes and preexisting-defect downgrades.
    """
    contracts_list = contracts or []
    diff_list = diff_results or []
    changed = changed_files or []

    materials = _model_material_by_id(model_output)
    parse_failed = bool(model_output is not None and model_output.get("parse_failed"))
    model_error = model_output.get("error", "") if model_output is not None else ""

    finalized_candidates: list[dict[str, Any]] = []
    confirmed: list[dict[str, Any]] = []
    audit_entries: list[dict[str, Any]] = []

    for cf in candidates:
        cf_id = str(cf.get("id", ""))
        evidence_type = cf.get("evidence_type", "")
        candidate_severity = cf.get("severity", "MAJOR")
        candidate_confidence = cf.get("confidence", 0.8)

        material = materials.get(cf_id.upper())
        model_ignored = material is None
        defense_argument = (
            material.get("defense_argument", "") if material is not None else ""
        )

        audit: dict[str, Any] = {
            "id": cf_id,
            "contract_id": cf.get("contract_id", ""),
            "type": cf.get("type", ""),
            "source": cf.get("source", ""),
            "evidence_type": evidence_type,
            "model_ignored": model_ignored,
            "parse_failed": parse_failed,
            "model_error": model_error,
            "defense_argument": defense_argument,
            "policy_version": POLICY_VERSION,
        }
        if material is not None and material.get("is_false_positive") is not None:
            audit["model_advisory_false_positive"] = material.get(
                "is_false_positive"
            )

        # ── 1. Parse failures never auto-confirm ──
        if parse_failed:
            severity = (
                "MAJOR" if candidate_severity == "BLOCKER"
                else (candidate_severity or "MINOR")
            )
            confidence = min(candidate_confidence, 0.8)
            digest = _evidence_digest(cf_id, evidence_type, severity, confidence)
            outcome = {
                **cf,
                "status": "needs_confirmation",
                "severity": severity,
                "confidence": confidence,
                "defense_reasoning": (
                    "Model defense output could not be parsed — "
                    "needs human confirmation"
                ),
                "court_source": "model_defense_policy",
                "evidence_digest": digest,
            }
            confirmed.append(outcome)
            finalized_candidates.append({
                **outcome,
                "status": "candidate",
                "policy_outcome": "needs_confirmation",
            })
            audit.update({
                "final_status": "needs_confirmation",
                "final_severity": severity,
                "final_confidence": confidence,
                "court_source": "model_defense_policy",
                "evidence_digest": digest,
                "blocker_check": None,
                "preexisting_check": None,
            })
            audit_entries.append(audit)
            continue

        # ── 2. NON_REPRODUCIBLE evidence is bookkeeping ──
        if cf.get("diff_verdict") == "NON_REPRODUCIBLE":
            finalized_candidates.append({
                **cf,
                "policy_outcome": "skipped",
            })
            audit.update({
                "final_status": "skipped",
                "final_severity": candidate_severity,
                "final_confidence": candidate_confidence,
                "court_source": "",
                "evidence_digest": "",
                "blocker_check": None,
                "preexisting_check": None,
                "skip_reason": "diff_verdict=NON_REPRODUCIBLE",
            })
            audit_entries.append(audit)
            continue

        # ── Model candidate confidence participates within the bounds ──
        severity = candidate_severity
        confidence = candidate_confidence
        if material is not None and material.get("candidate_confidence") is not None:
            model_conf = material.get("candidate_confidence")
            if isinstance(model_conf, int | float):
                confidence = min(max(float(model_conf), 0.0), 1.0)

        # ── 3. Static evidence cap (byte-compatible) ──
        if evidence_type in NON_BLOCKER_EVIDENCE_TYPES:
            if severity == "BLOCKER":
                severity = "MAJOR"
            confidence = min(confidence, STATIC_CONFIDENCE_CEILING)

        blocker_check = _check_blocker_conditions(
            cf, contracts_list, diff_list, generated_tests_path, changed
        )

        # ── 4. Preexisting-defect rule ──
        preexisting = _preexisting_check(cf, diff_list)
        if preexisting is not None and not preexisting["head_only_difference"]:
            final_severity = NOT_ATTRIBUTED_SEVERITY
            final_confidence = min(confidence, NOT_ATTRIBUTED_CONFIDENCE_CEILING)
            digest = _evidence_digest(
                cf_id, evidence_type, final_severity, final_confidence
            )
            finalized_candidates.append({
                **cf,
                "severity": severity,
                "confidence": confidence,
                "blocker_check": blocker_check,
                "preexisting_check": preexisting,
                "court_source": cf.get("court_source", "rule_based"),
                "evidence_digest": digest,
                "policy_outcome": NOT_ATTRIBUTED_STATUS,
            })
            audit.update({
                "final_status": NOT_ATTRIBUTED_STATUS,
                "final_severity": final_severity,
                "final_confidence": final_confidence,
                "court_source": "policy",
                "evidence_digest": digest,
                "blocker_check": blocker_check,
                "preexisting_check": preexisting,
            })
            audit_entries.append(audit)
            continue

        # ── 5. BLOCKER six-conditions (byte-compatible) ──
        if severity == "BLOCKER" and not blocker_check["all_blocker_conditions_met"]:
            severity = "MAJOR"
            confidence = min(confidence, DOWNGRADED_BLOCKER_CONFIDENCE_CEILING)

        digest = _evidence_digest(cf_id, evidence_type, severity, confidence)
        court_source = cf.get("court_source", "rule_based")
        outcome = {
            **cf,
            "status": "confirmed",
            "severity": severity,
            "confidence": confidence,
            "court_source": court_source,
            "evidence_digest": digest,
            "blocker_check": blocker_check,
        }
        if preexisting is not None:
            outcome["preexisting_check"] = preexisting
        if defense_argument:
            outcome["defense_argument"] = defense_argument
        confirmed.append(outcome)
        finalized_candidates.append({
            **outcome,
            "status": "candidate",
            "policy_outcome": "confirmed",
        })
        audit.update({
            "final_status": "confirmed",
            "final_severity": severity,
            "final_confidence": confidence,
            "court_source": court_source,
            "evidence_digest": digest,
            "blocker_check": blocker_check,
            "preexisting_check": preexisting,
        })
        audit_entries.append(audit)

    return {
        "candidate_findings": finalized_candidates,
        "confirmed_findings": _dedup_candidates(confirmed),
        "audit_entries": audit_entries,
    }

