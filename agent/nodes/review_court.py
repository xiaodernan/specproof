"""review_court node — Prosecutor / Defender / Judge evaluation.

Phase 0: rule-based with optional LLM-based three-party debate.
Phase 1+: full LLM-based review court.
"""

import asyncio
import json
import os

from agent.state import Phase0State

_LLM_PROSECUTOR_PROMPT = """You are a PROSECUTOR in a code review court. Your role is to argue
why each finding is a REAL regression or security issue that must block the PR.

Candidate findings:
{candidates_json}

For each finding, produce a JSON object with:
- id: the finding's id
- prosecution_argument: why this is a real issue (1-2 sentences, concrete)
- recommended_severity: BLOCKER / MAJOR / MINOR
- confidence: 0.0 to 1.0

Return a JSON array. No other text."""

_LLM_DEFENDER_PROMPT = """You are a DEFENDER in a code review court. Your role is to argue
against false positives — identify findings that may be benign, intentional, or incorrectly flagged.

Candidate findings:
{candidates_json}

Prosecutor arguments:
{prosecutor_arguments}

For each finding, produce a JSON object with:
- id: the finding's id
- defense_argument: why this might be a false positive (1-2 sentences)
- is_false_positive: true or false
- counter_confidence: 0.0 to 1.0 (how confident you are this is NOT a real issue)

Return a JSON array. No other text."""

_LLM_JUDGE_PROMPT = """You are a JUDGE in a code review court. After hearing both sides,
make a final ruling on each finding.

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

Evidence policy:
- BLOCKER: strong executable evidence, confidence >= 0.90
- MAJOR: at least one strong evidence source, confidence >= 0.82
- MINOR: repository evidence + logic, confidence >= 0.72
- Below 0.72: DISMISSED

Return a JSON array. No other text."""


def _get_provider():
    """Create an LLM provider from env vars. Returns None if not configured."""
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key or api_key == "replace_me":
        return None
    try:
        from providers.openai_compatible import OpenAICompatibleProvider
        return OpenAICompatibleProvider(probe_on_init=False)
    except Exception:
        return None


async def _llm_review_court(candidates: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Run LLM-based three-party debate. Returns (prosecutor, defender, judge) results."""
    from providers.base import LLMMessage

    provider = _get_provider()
    if provider is None:
        raise RuntimeError("No LLM provider available")

    candidates_json = json.dumps(
        [{k: v for k, v in c.items() if k != "source"} for c in candidates],
        indent=2, ensure_ascii=False,
    )

    # Phase 1: Prosecutor
    prosecutor_response = await provider.chat(
        messages=[LLMMessage(
            role="user",
            content=_LLM_PROSECUTOR_PROMPT.format(candidates_json=candidates_json),
        )],
        timeout=60.0,
    )
    prosecutor_args = _extract_json_array(prosecutor_response.content or "")

    # Phase 2: Defender
    defender_response = await provider.chat(
        messages=[LLMMessage(
            role="user",
            content=_LLM_DEFENDER_PROMPT.format(
                candidates_json=candidates_json,
                prosecutor_arguments=json.dumps(prosecutor_args, indent=2),
            ),
        )],
        timeout=60.0,
    )
    defender_args = _extract_json_array(defender_response.content or "")

    # Phase 3: Judge
    judge_response = await provider.chat(
        messages=[LLMMessage(
            role="user",
            content=_LLM_JUDGE_PROMPT.format(
                prosecutor_arguments=json.dumps(prosecutor_args, indent=2),
                defender_arguments=json.dumps(defender_args, indent=2),
            ),
        )],
        timeout=60.0,
    )
    judge_rulings = _extract_json_array(judge_response.content or "")

    return prosecutor_args, defender_args, judge_rulings


def _extract_json_array(content: str) -> list[dict]:
    """Extract a JSON array from LLM response text."""
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


def _apply_judge_rulings(
    candidates: list[dict],
    judge_rulings: list[dict],
) -> list[dict]:
    """Apply judge rulings to candidate findings, producing confirmed findings."""
    rulings_by_id = {
        r.get("id", "").upper(): r for r in judge_rulings
    }
    confirmed: list[dict] = []

    for cf in candidates:
        cid = cf.get("id", "").upper()
        ruling = rulings_by_id.get(cid, {})

        verdict = ruling.get("verdict", "CONFIRMED")
        if verdict == "DISMISSED":
            continue

        severity = ruling.get("severity") or cf.get("severity", "MAJOR")
        confidence = ruling.get("confidence", cf.get("confidence", 0.8))

        confirmed.append({
            **cf,
            "status": "confirmed",
            "severity": severity,
            "confidence": confidence,
            "judge_reasoning": ruling.get("reasoning", ""),
            "court_source": "llm_three_party",
        })

    return confirmed


def _rule_based_court(state: Phase0State) -> dict:
    """Original rule-based Review Court (Phase 0 baseline)."""
    static_findings = state.get("static_findings", [])
    diff_results = state.get("diff_results", [])
    candidate_findings: list[dict] = []
    confirmed_findings: list[dict] = []

    # ── Prosecutor: gather all potential issues ──
    for sf in static_findings:
        candidate_findings.append({
            **sf,
            "source": "static_analysis",
            "status": "candidate",
        })

    for dr in diff_results:
        if dr.get("verdict") in ("REGRESSION", "AMBIGUOUS"):
            candidate_findings.append({
                "id": f"COURT-{dr.get('contract_id', 'UNKNOWN')}",
                "contract_id": dr.get("contract_id", ""),
                "severity": "MAJOR",
                "type": "differential_regression",
                "description": dr.get("detail", "Differential test regression"),
                "evidence_type": "base_pass_head_fail",
                "confidence": 0.85 if dr.get("verdict") == "REGRESSION" else 0.65,
                "source": "differential",
                "status": "candidate",
                "diff_verdict": dr.get("verdict"),
            })

    # ── Defender: filter out false positives ──
    for cf in candidate_findings:
        is_false_positive = False
        if cf.get("diff_verdict") == "NON_REPRODUCIBLE":
            is_false_positive = True
        if not is_false_positive:
            confirmed_findings.append({**cf, "status": "confirmed"})

    # ── Judge: apply evidence policy ──
    for f in confirmed_findings:
        evidence_type = f.get("evidence_type", "")
        confidence = f.get("confidence", 0.0)
        is_strong = evidence_type in (
            "base_pass_head_fail",
            "static_analysis",
            "deterministic_contract_failure",
        )

        if is_strong and confidence >= 0.90:
            f["severity"] = "BLOCKER"
        elif is_strong and confidence >= 0.82:
            f["severity"] = "MAJOR"
        elif confidence >= 0.72:
            f["severity"] = "MINOR"
        else:
            f["severity"] = "NEEDS_CONFIRMATION"

    return {
        "candidate_findings": candidate_findings,
        "confirmed_findings": confirmed_findings,
    }


def review_court_node(state: Phase0State) -> dict:
    """Evaluate candidate findings through the Review Court process.

    Phase 0: tries LLM-based three-party debate if provider available,
    falls back to rule-based court.
    """
    static_findings = state.get("static_findings", [])
    diff_results = state.get("diff_results", [])

    # Gather candidates (same as rule-based phase 1)
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
                "evidence_type": "base_pass_head_fail",
                "confidence": 0.85 if dr.get("verdict") == "REGRESSION" else 0.65,
                "source": "differential",
                "status": "candidate",
                "diff_verdict": dr.get("verdict"),
            })

    if not candidates:
        return {
            "candidate_findings": [],
            "confirmed_findings": [],
        }

    confirmed_findings: list[dict] = []
    court_source = "rule_based"

    # Try LLM-based three-party debate
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
                confirmed_findings = _apply_judge_rulings(candidates, judge_rulings)
                court_source = "llm_three_party"
        except Exception:
            pass

    # Fall back to rule-based if LLM produced no confirmed findings
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
