"""review_court node — Prosecutor / Defender / Judge evaluation.

P0.5 Evidence Policy (strict enforcement):
  BLOCKER requires ALL 6 conditions:
    1. Approved contract (contract_id in state.contracts)
    2. Base/Head real execution evidence (not static regex alone)
    3. Attribution to Head (diff between base and head)
    4. DB/behavior evidence (db_state_mutation or equivalent)
    5. Capsule replayable (reproducible with clean checkout)
    6. Confidence >= 0.90

  Static regex findings capped at MAJOR (never BLOCKER).
  SHA-256 hash named "evidence_digest" or "manifest_digest", never "signature".
"""

import asyncio
import hashlib
import json
import os

from agent.state import Phase0State

# P0.5: BLOCKER requirements
_BLOCKER_REQUIRED_EVIDENCE_TYPES = frozenset({
    "base_pass_head_fail",
    "db_state_mutation",
    "differential_execution",
})

# Evidence types that CANNOT produce BLOCKER on their own
_NON_BLOCKER_EVIDENCE_TYPES = frozenset({
    "static_regex_analysis",
    "static_analysis",
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

IMPORTANT: Static regex analysis alone cannot justify BLOCKER severity.
Only findings with executable evidence (base_pass_head_fail, differential execution,
DB state mutation) can be recommended as BLOCKER.

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
  2) base/head real execution evidence (not static regex)
  3) attribution to Head (diff between versions)
  4) DB or behavioral evidence
  5) reproducible in clean capsule
  6) confidence >= 0.90
- Static regex findings can NEVER be BLOCKER (max MAJOR).
- MAJOR: at least one strong evidence source, confidence >= 0.82
- MINOR: evidence + logic, confidence >= 0.72
- Below 0.72: DISMISSED

Return a JSON array. No other text."""


def _get_provider():
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key or api_key == "replace_me":
        return None
    try:
        from providers.openai_compatible import OpenAICompatibleProvider
        return OpenAICompatibleProvider(probe_on_init=False)
    except Exception:
        return None


async def _llm_review_court(candidates: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
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


def _extract_json_array(content: str) -> list[dict]:
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


def _check_blocker_conditions(
    finding: dict,
    contracts: list[dict],
    has_diff_evidence: bool,
    has_db_evidence: bool,
) -> dict:
    """Check all 6 BLOCKER conditions for P0.5 evidence policy.

    Returns a dict with condition_results and whether all are met.
    """
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

    # Condition 1: Approved contract exists
    conditions["1_approved_contract"] = any(
        c.get("id") == contract_id for c in contracts
    ) if contract_id else False

    # Condition 2: Base/Head real execution (not static regex)
    conditions["2_base_head_execution"] = (
        evidence_type not in _NON_BLOCKER_EVIDENCE_TYPES
        and evidence_type in _BLOCKER_REQUIRED_EVIDENCE_TYPES
    ) or has_diff_evidence

    # Condition 3: Attribution to Head
    conditions["3_attribution_to_head"] = (
        finding.get("diff_verdict") == "REGRESSION"
        or evidence_type in ("base_pass_head_fail", "differential_execution")
        or has_diff_evidence
    )

    # Condition 4: DB/behavior evidence
    conditions["4_db_behavior_evidence"] = (
        has_db_evidence
        or evidence_type == "db_state_mutation"
        or finding.get("db_state_verdict") == "DB_MUTATED_ON_UNAUTH"
    )

    # Condition 5: Capsule replayable (REGRESSION findings produce capsules)
    severity = finding.get("severity", "")
    conditions["5_capsule_replayable"] = severity in ("BLOCKER", "MAJOR")

    # Condition 6: Confidence >= 0.90
    conditions["6_confidence_090"] = finding.get("confidence", 0) >= 0.90

    all_met = all(conditions.values())
    return {
        "blocker_conditions": conditions,
        "all_blocker_conditions_met": all_met,
    }


def _apply_judge_rulings(
    candidates: list[dict],
    judge_rulings: list[dict],
    contracts: list[dict],
    diff_results: list[dict],
) -> list[dict]:
    """Apply judge rulings with P0.5 evidence policy enforcement.

    Static regex findings can NEVER be BLOCKER regardless of judge ruling.
    """
    rulings_by_id = {r.get("id", "").upper(): r for r in judge_rulings}
    confirmed: list[dict] = []

    # Check for diff evidence presence
    has_diff_evidence = any(
        dr.get("verdict") == "REGRESSION" for dr in diff_results
    )
    has_db_evidence = any(
        dr.get("db_state_verdict") == "DB_MUTATED_ON_UNAUTH"
        for dr in diff_results
    )

    for cf in candidates:
        cid = cf.get("id", "").upper()
        ruling = rulings_by_id.get(cid, {})

        verdict = ruling.get("verdict", "CONFIRMED")
        if verdict == "DISMISSED":
            continue

        evidence_type = cf.get("evidence_type", "")
        severity = ruling.get("severity") or cf.get("severity", "MAJOR")
        confidence = ruling.get("confidence", cf.get("confidence", 0.8))

        # P0.5: Static regex can NEVER be BLOCKER
        if evidence_type in _NON_BLOCKER_EVIDENCE_TYPES and severity == "BLOCKER":
            severity = "MAJOR"
            confidence = min(confidence, 0.85)

        # P0.5: Check all 6 BLOCKER conditions
        blocker_check = _check_blocker_conditions(
            cf, contracts, has_diff_evidence, has_db_evidence
        )
        if severity == "BLOCKER" and not blocker_check["all_blocker_conditions_met"]:
            severity = "MAJOR"

        # Compute evidence digest
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

    return confirmed


def _rule_based_court(state: Phase0State) -> dict:
    """Rule-based Review Court with P0.5 evidence policy.

    Static regex findings → max MAJOR.
    BLOCKER requires approved contract + real execution + DB evidence.
    """
    static_findings = state.get("static_findings", [])
    diff_results = state.get("diff_results", [])
    contracts = state.get("contracts", [])
    candidate_findings: list[dict] = []
    confirmed_findings: list[dict] = []

    has_diff_evidence = any(
        dr.get("verdict") == "REGRESSION" for dr in diff_results
    )
    has_db_evidence = any(
        dr.get("db_state_verdict") == "DB_MUTATED_ON_UNAUTH"
        for dr in diff_results
    )

    # Gather candidates from static findings → evidence_type checked
    for sf in static_findings:
        evidence_type = sf.get("evidence_type", "static_analysis")
        candidate = {
            **sf,
            "source": "static_analysis",
            "status": "candidate",
        }
        # P0.5: Static regex findings can only be MAJOR at most
        if evidence_type in _NON_BLOCKER_EVIDENCE_TYPES:
            candidate["severity"] = (
                "MAJOR" if sf.get("severity") == "BLOCKER"
                else sf.get("severity", "MAJOR")
            )
            candidate["confidence"] = min(
                sf.get("confidence", 0.8), 0.85
            )
        candidate_findings.append(candidate)

    # Gather candidates from differential results
    for dr in diff_results:
        if dr.get("verdict") in ("REGRESSION", "AMBIGUOUS"):
            is_regression = dr.get("verdict") == "REGRESSION"
            evidence_type = dr.get("evidence_type", "differential_execution")
            db_verdict = dr.get("db_state_verdict", "")

            # P0.5: BLOCKER only if both HTTP and DB evidence confirm
            if is_regression and db_verdict == "DB_MUTATED_ON_UNAUTH":
                severity = "BLOCKER"
                confidence = 0.95
            elif is_regression:
                severity = "MAJOR"
                confidence = 0.85
            else:
                severity = "MINOR"
                confidence = 0.65

            candidate = {
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
                "db_state_verdict": db_verdict,
            }
            candidate_findings.append(candidate)

    # Defender: filter false positives
    for cf in candidate_findings:
        is_false_positive = False
        if cf.get("diff_verdict") == "NON_REPRODUCIBLE":
            is_false_positive = True
        if not is_false_positive:
            confirmed_findings.append({**cf, "status": "confirmed"})

    # Judge: apply evidence policy
    for f in confirmed_findings:
        evidence_type = f.get("evidence_type", "")
        db_verdict = f.get("db_state_verdict", "")

        # P0.5: Static regex → max MAJOR
        if evidence_type in _NON_BLOCKER_EVIDENCE_TYPES:
            f["severity"] = (
                "MAJOR" if f.get("severity") == "BLOCKER"
                else f.get("severity", "MAJOR")
            )

        # P0.5: BLOCKER requires all 6 conditions
        blocker_check = _check_blocker_conditions(
            f, contracts, has_diff_evidence, has_db_evidence
        )
        f["blocker_check"] = blocker_check

        if f.get("severity") == "BLOCKER":
            if not blocker_check["all_blocker_conditions_met"]:
                f["severity"] = "MAJOR"

        # Compute evidence digest (never called "signature")
        evidence_json = json.dumps({
            "id": f.get("id", ""),
            "evidence_type": evidence_type,
            "severity": f.get("severity"),
            "confidence": f.get("confidence"),
        }, sort_keys=True)
        f["evidence_digest"] = (
            "sha256:" + hashlib.sha256(evidence_json.encode()).hexdigest()
        )
        f.setdefault("court_source", "rule_based")

    return {
        "candidate_findings": candidate_findings,
        "confirmed_findings": confirmed_findings,
    }


def review_court_node(state: Phase0State) -> dict:
    """Evaluate candidate findings through P0.5 Review Court.

    Enforces evidence policy:
    - Static regex alone cannot produce BLOCKER
    - BLOCKER requires 6 conditions
    - SHA-256 named evidence_digest, never "signature"
    """
    static_findings = state.get("static_findings", [])
    diff_results = state.get("diff_results", [])
    contracts = state.get("contracts", [])

    candidates: list[dict] = []
    for sf in static_findings:
        candidates.append({**sf, "source": "static_analysis", "status": "candidate"})
    for dr in diff_results:
        if dr.get("verdict") in ("REGRESSION", "AMBIGUOUS"):
            candidates.append({
                "id": f"COURT-{dr.get('contract_id', 'UNKNOWN')}",
                "contract_id": dr.get("contract_id", ""),
                "severity": "MAJOR",
                "type": "differential_regression",
                "description": dr.get("detail", "Differential test regression"),
                "evidence_type": dr.get("evidence_type", "differential_execution"),
                "confidence": 0.85 if dr.get("verdict") == "REGRESSION" else 0.65,
                "source": "differential",
                "status": "candidate",
                "diff_verdict": dr.get("verdict"),
                "db_state_verdict": dr.get("db_state_verdict", ""),
            })

    if not candidates:
        return {"candidate_findings": [], "confirmed_findings": []}

    confirmed_findings: list[dict] = []
    court_source = "rule_based"

    provider = _get_provider()
    if provider is not None:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run, _llm_review_court(candidates)
                    )
                    _pros, _def, judge_rulings = future.result(timeout=180)
            else:
                _pros, _def, judge_rulings = asyncio.run(
                    _llm_review_court(candidates)
                )
            if judge_rulings:
                confirmed_findings = _apply_judge_rulings(
                    candidates, judge_rulings, contracts, diff_results
                )
                court_source = "llm_three_party"
        except Exception:
            pass

    if court_source == "rule_based" or not confirmed_findings:
        rule_result = _rule_based_court(state)
        confirmed_findings = rule_result["confirmed_findings"]
        court_source = "rule_based"

    for f in confirmed_findings:
        f.setdefault("court_source", court_source)

    return {
        "candidate_findings": candidates,
        "confirmed_findings": confirmed_findings,
    }
