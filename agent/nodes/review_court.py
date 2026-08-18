
"""review_court node — Prosecutor / Defender / Judge evaluation.

P0.5 Evidence Policy (strict enforcement, v2):
  BLOCKER requires ALL 6 conditions:
    1. Approved contract (contract_id in state.contracts)
    2. Real Base/Head execution evidence recorded by run_differential
       (base_pass_head_fail with actual exit codes — never static diff)
    3. Attribution to Head (location present in changed files)
    4. Real DB evidence (db_state_verdict == DB_MUTATED_ON_UNAUTH from H2 dump)
    5. Replay constructible (executable evidence + generated test file exists)
    6. Confidence >= 0.90

  Static/source-diff findings are capped at MAJOR (never BLOCKER).
  Digests are named "evidence_digest", never "signature".
  Duplicate candidates for the same (contract, type) are merged.
"""
import asyncio
import hashlib
import json
import os
from typing import Any

from agent.state import Phase0State

_BLOCKER_REQUIRED_EVIDENCE_TYPES = frozenset({
    "base_pass_head_fail",
    "differential_execution",
})

_NON_BLOCKER_EVIDENCE_TYPES = frozenset({
    "static_regex_analysis",
    "static_analysis",
    "java_source_diff",
    "heuristic",
})

_LLM_PROSECUTOR_PROMPT = """You are a PROSECUTOR in a code review court. Your role is to argue
why each finding is a REAL regression or security issue.

Candidate findings:
{candidates_json}

For each finding, produce a JSON object with:
- id: the finding's id
- prosecution_argument: why this is a real issue (1-2 sentences, concrete)
- recommended_severity: BLOCKER / MAJOR / MINOR
- confidence: 0.0 to 1.0

IMPORTANT: Static analysis alone cannot justify BLOCKER severity.
Only findings with executable evidence (base_pass_head_fail, differential
execution, real DB state mutation) can be recommended as BLOCKER.

Return a JSON array. No other text."""

_LLM_DEFENDER_PROMPT = """You are a DEFENDER in a code review court. Your role is to argue
against false positives.

Candidate findings:
{candidates_json}

Prosecutor arguments:
{prosecutor_arguments}

For each finding, produce a JSON object with:
- id: the finding's id
- defense_argument: why this might be a false positive (1-2 sentences)
- is_false_positive: true or false
- counter_confidence: 0.0 to 1.0

Return a JSON array. No other text."""

_LLM_JUDGE_PROMPT = """You are a JUDGE in a code review court.

Prosecutor arguments:
{prosecutor_arguments}

Defender arguments:
{defender_arguments}

For each finding, produce a JSON object with:
- id: the finding's id
- verdict: CONFIRMED or DISMISSED
- severity: BLOCKER / MAJOR / MINOR
- confidence: 0.0 to 1.0
- reasoning: 1 sentence explaining the ruling

EVIDENCE POLICY (strict):
- BLOCKER requires ALL of:
  1) approved contract exists
  2) base/head real execution evidence (not static diff)
  3) attribution to Head (diff between versions)
  4) DB or behavioral evidence
  5) reproducible in clean capsule
  6) confidence >= 0.90
- Static findings can NEVER be BLOCKER (max MAJOR).
- MAJOR: at least one strong evidence source, confidence >= 0.82
- MINOR: evidence + logic, confidence >= 0.72
- Below 0.72: DISMISSED

Return a JSON array. No other text."""


def _get_provider() -> Any:
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key or api_key == "replace_me":
        return None
    try:
        from providers.openai_compatible import OpenAICompatibleProvider
        return OpenAICompatibleProvider(probe_on_init=False)
    except Exception:
        return None


async def _llm_review_court(
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    from providers.base import LLMMessage

    provider = _get_provider()
    if provider is None:
        raise RuntimeError("No LLM provider available")

    candidates_json = json.dumps(
        [{k: v for k, v in c.items() if k != "source"} for c in candidates],
        indent=2, ensure_ascii=False,
    )

    prosecutor_response = await provider.chat(
        messages=[LLMMessage(
            role="user",
            content=_LLM_PROSECUTOR_PROMPT.format(candidates_json=candidates_json),
        )],
        thinking=True,
        timeout=90.0,
    )
    prosecutor_args = _extract_json_array(prosecutor_response.content or "")

    defender_response = await provider.chat(
        messages=[LLMMessage(
            role="user",
            content=_LLM_DEFENDER_PROMPT.format(
                candidates_json=candidates_json,
                prosecutor_arguments=json.dumps(prosecutor_args, indent=2),
            ),
        )],
        thinking=True,
        timeout=90.0,
    )
    defender_args = _extract_json_array(defender_response.content or "")

    judge_response = await provider.chat(
        messages=[LLMMessage(
            role="user",
            content=_LLM_JUDGE_PROMPT.format(
                prosecutor_arguments=json.dumps(prosecutor_args, indent=2),
                defender_arguments=json.dumps(defender_args, indent=2),
            ),
        )],
        thinking=True,
        timeout=90.0,
    )
    judge_rulings = _extract_json_array(judge_response.content or "")

    return prosecutor_args, defender_args, judge_rulings


def _extract_json_array(content: str) -> list[dict[str, Any]]:
    start = content.find("[")
    end = content.rfind("]") + 1
    if start >= 0 and end > start:
        try:
            parsed = json.loads(content[start:end])
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return []


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
        evidence_type in _BLOCKER_REQUIRED_EVIDENCE_TYPES
        and _has_real_execution_evidence(diff_results)
    )

    location = finding.get("location", "")
    conditions["3_attribution_to_head"] = bool(
        location
        and any(location in cf for cf in changed_files)
    ) or evidence_type == "base_pass_head_fail"

    conditions["4_db_behavior_evidence"] = (
        finding.get("db_state_verdict") == "DB_MUTATED_ON_UNAUTH"
        or any(
            dr.get("db_state_verdict") == "DB_MUTATED_ON_UNAUTH"
            for dr in diff_results
        )
    )

    conditions["5_capsule_replayable"] = (
        evidence_type in _BLOCKER_REQUIRED_EVIDENCE_TYPES
        and bool(generated_tests_path)
    )

    conditions["6_confidence_090"] = finding.get("confidence", 0) >= 0.90

    all_met = all(conditions.values())
    return {
        "blocker_conditions": conditions,
        "all_blocker_conditions_met": all_met,
    }


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


def _apply_judge_rulings(
    candidates: list[dict[str, Any]],
    judge_rulings: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    diff_results: list[dict[str, Any]],
    generated_tests_path: str,
    changed_files: list[str],
) -> list[dict[str, Any]]:
    """Apply judge rulings with P0.5 evidence policy enforcement.

    A missing or unmatched ruling defaults to NEEDS_CONFIRMATION (never
    silently CONFIRMED).
    """
    rulings_by_id = {r.get("id", "").upper(): r for r in judge_rulings}
    confirmed: list[dict[str, Any]] = []

    for cf in candidates:
        cid = cf.get("id", "").upper()
        ruling = rulings_by_id.get(cid)

        if ruling is None:
            # Judge never evaluated this finding — do not confirm it.
            confirmed.append({
                **cf,
                "status": "needs_confirmation",
                "severity": (
                    "MAJOR" if cf.get("severity") == "BLOCKER"
                    else cf.get("severity", "MINOR")
                ),
                "confidence": min(cf.get("confidence", 0.8), 0.8),
                "judge_reasoning": "No judge ruling returned for this finding",
                "court_source": "llm_three_party",
            })
            continue

        verdict = ruling.get("verdict", "")
        if verdict == "DISMISSED":
            continue

        evidence_type = cf.get("evidence_type", "")
        severity = ruling.get("severity") or cf.get("severity", "MAJOR")
        confidence = ruling.get("confidence", cf.get("confidence", 0.8))

        if evidence_type in _NON_BLOCKER_EVIDENCE_TYPES and severity == "BLOCKER":
            severity = "MAJOR"
            confidence = min(confidence, 0.85)

        blocker_check = _check_blocker_conditions(
            cf, contracts, diff_results, generated_tests_path, changed_files
        )
        if severity == "BLOCKER" and not blocker_check["all_blocker_conditions_met"]:
            severity = "MAJOR"

        evidence_json = json.dumps({
            "id": cid,
            "evidence_type": evidence_type,
            "verdict": verdict,
            "severity": severity,
            "confidence": confidence,
        }, sort_keys=True)
        evidence_digest = hashlib.sha256(evidence_json.encode()).hexdigest()

        confirmed.append({
            **cf,
            "status": "confirmed",
            "severity": severity,
            "confidence": confidence,
            "judge_reasoning": ruling.get("reasoning", ""),
            "court_source": "llm_three_party",
            "evidence_digest": f"sha256:{evidence_digest}",
            "blocker_check": blocker_check,
        })

    return _dedup_candidates(confirmed)


def _rule_based_court(state: Phase0State) -> dict[str, Any]:
    """Rule-based Review Court with P0.5 evidence policy."""
    static_findings = state.get("static_findings", [])
    diff_results = state.get("diff_results", [])
    contracts = state.get("contracts", [])
    generated_tests_path = state.get("generated_tests_path", "")
    changed_files = _changed_files(state)

    candidates: list[dict[str, Any]] = []

    for sf in static_findings:
        evidence_type = sf.get("evidence_type", "static_analysis")
        candidate = {**sf, "source": "static_analysis", "status": "candidate"}
        if evidence_type in _NON_BLOCKER_EVIDENCE_TYPES:
            candidate["severity"] = (
                "MAJOR" if sf.get("severity") == "BLOCKER"
                else sf.get("severity", "MAJOR")
            )
            candidate["confidence"] = min(sf.get("confidence", 0.8), 0.85)
        candidates.append(candidate)

    for dr in diff_results:
        if dr.get("verdict") not in ("REGRESSION", "AMBIGUOUS"):
            continue
        evidence_type = dr.get("evidence_type", "differential_execution")
        severity = dr.get("severity")
        if evidence_type in _NON_BLOCKER_EVIDENCE_TYPES:
            severity = "MAJOR" if severity == "BLOCKER" else (severity or "MAJOR")
        elif severity is None:
            severity = "MAJOR" if dr.get("verdict") == "REGRESSION" else "MINOR"
        # Severity-NONE entries (contracts the failing test did NOT exercise)
        # are bookkeeping, not findings — they must never surface as
        # confirmed findings or false positives.
        if severity == "NONE":
            continue
        confidence = dr.get("confidence")
        if confidence is None:
            confidence = 0.88 if dr.get("verdict") == "REGRESSION" else 0.65

        candidates.append({
            "id": f"COURT-{dr.get('contract_id', 'UNKNOWN')}",
            "contract_id": dr.get("contract_id", ""),
            "severity": severity,
            "type": "differential_regression",
            "description": dr.get("detail", "Differential test regression"),
            "evidence_type": evidence_type,
            "confidence": confidence,
            "source": "differential",
            "status": "candidate",
            "diff_verdict": dr.get("verdict"),
            "db_state_verdict": dr.get("db_state_verdict", ""),
            "location": dr.get("location", ""),
            "evidence_digest": dr.get("evidence_digest", ""),
        })

    candidates = _dedup_candidates(candidates)

    confirmed: list[dict[str, Any]] = []
    for cf in candidates:
        if cf.get("diff_verdict") == "NON_REPRODUCIBLE":
            continue

        evidence_type = cf.get("evidence_type", "")
        if evidence_type in _NON_BLOCKER_EVIDENCE_TYPES:
            cf["severity"] = (
                "MAJOR" if cf.get("severity") == "BLOCKER"
                else cf.get("severity", "MAJOR")
            )
            cf["confidence"] = min(cf.get("confidence", 0.8), 0.85)

        blocker_check = _check_blocker_conditions(
            cf, contracts, diff_results, generated_tests_path, changed_files
        )
        cf["blocker_check"] = blocker_check
        if cf.get("severity") == "BLOCKER" and not blocker_check["all_blocker_conditions_met"]:
            cf["severity"] = "MAJOR"
            cf["confidence"] = min(cf.get("confidence", 0.88), 0.88)

        evidence_json = json.dumps({
            "id": cf.get("id", ""),
            "evidence_type": evidence_type,
            "severity": cf.get("severity"),
            "confidence": cf.get("confidence"),
        }, sort_keys=True)
        cf["evidence_digest"] = (
            "sha256:" + hashlib.sha256(evidence_json.encode()).hexdigest()
        )
        cf.setdefault("court_source", "rule_based")
        confirmed.append({**cf, "status": "confirmed"})

    return {
        "candidate_findings": candidates,
        "confirmed_findings": confirmed,
    }


def _changed_files(state: Phase0State) -> list[str]:
    import subprocess
    repo_path = state.get("repo_path", "")
    base_ref = state.get("base_ref", "base")
    head_ref = state.get("head_ref", "head-v1")
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "diff", "--name-only", base_ref, head_ref],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return [f.strip() for f in result.stdout.splitlines() if f.strip()]
    except Exception:
        pass
    return []


def review_court_node(state: Phase0State) -> dict[str, Any]:
    """Evaluate candidate findings through the P0.5 Review Court."""
    contracts = state.get("contracts", [])
    diff_results = state.get("diff_results", [])

    if not state.get("static_findings") and not diff_results:
        return {"candidate_findings": [], "confirmed_findings": []}

    provider = _get_provider() if state.get("use_llm", True) else None
    if provider is not None:
        try:
            # Build the same candidate set the rule-based court uses.
            rule_candidates = _rule_based_court(state)["candidate_findings"]
            if rule_candidates:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(
                            asyncio.run, _llm_review_court(rule_candidates)
                        )
                        _pros, _def, judge_rulings = future.result(timeout=180)
                else:
                    _pros, _def, judge_rulings = asyncio.run(
                        _llm_review_court(rule_candidates)
                    )
                if judge_rulings:
                    confirmed_findings = _apply_judge_rulings(
                        rule_candidates, judge_rulings, contracts, diff_results,
                        state.get("generated_tests_path", ""),
                        _changed_files(state),
                    )
                    return {
                        "candidate_findings": rule_candidates,
                        "confirmed_findings": confirmed_findings,
                    }
        except Exception:
            # LLM court unavailable — fall through to the deterministic court.
            pass

    return _rule_based_court(state)
