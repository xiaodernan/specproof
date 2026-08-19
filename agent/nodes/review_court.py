"""review_court node — two-layer Review Court (master plan §14.1).

Layer 1 — model defense (optional, injected):
  model_produce_defense(candidates, state) returns defense material and a
  candidate confidence per finding. It never decides severity or status.
  Default is OFF: when no callable is injected, the court is fully
  deterministic.

Layer 2 — deterministic policy (agent/review_court/policy.py):
  policy_recalculate recomputes severity and status from evidence kinds,
  confidence ceilings and the Base/Head runtime comparison. It enforces the
  P0.5 six-condition BLOCKER policy (byte-compatible with the pre-split
  rule-based court) plus the preexisting-defect rule: when Base also fails
  the same assertion/behavior, the finding is downgraded to
  NOT_ATTRIBUTED / INFORMATIONAL unless a distinct head-only behavior
  difference exists.

Every candidate — including model-ignored ones, parse failures and
preexisting-defect downgrades — is recorded in state["court_audit"].
"""
import asyncio
import concurrent.futures
import inspect
import json
import os
from collections.abc import Awaitable, Callable
from typing import Any

from agent.review_court.policy import (
    NON_BLOCKER_EVIDENCE_TYPES,
    STATIC_CONFIDENCE_CEILING,
    DefenseMaterial,
    ModelDefenseOutput,
    _dedup_candidates,
    policy_recalculate,
)
from agent.state import Phase0State
from providers.judge_persona import build_judge_prompt

DefenseProducer = Callable[
    [list[dict[str, Any]], Any],
    ModelDefenseOutput | Awaitable[ModelDefenseOutput],
]

_LLM_DEFENSE_PROMPT = """You are the DEFENDER in a code review court. Your role is to produce
defense material for each candidate finding — never the final severity.

Candidate findings:
{candidates_json}

For each finding, produce a JSON object with:
- id: the finding's id
- defense_argument: why this might be a false positive (1-2 sentences, concrete)
- is_false_positive: true or false (advisory only; the deterministic policy
  recomputes severity and status and is not bound by this field)
- candidate_confidence: 0.0 to 1.0 (your confidence that the finding is real)

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


def _extract_json_array(content: str) -> list[dict[str, Any]]:
    start = content.find("[")
    end = content.rfind("]") + 1
    if start >= 0 and end > start:
        try:
            parsed = json.loads(content[start:end])
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def _as_confidence(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return min(max(float(value), 0.0), 1.0)
    return None


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


async def _llm_defense_materials(
    provider: Any, candidates: list[dict[str, Any]]
) -> ModelDefenseOutput:
    """Ask the model for defense material only; parse failures are flagged.

    The no-fake-pass judge persona is APPENDED after the base defense prompt
    via build_judge_prompt, so the stable base-prompt prefix stays
    byte-identical at the front (KV-cache-friendly ordering). This only
    happens on the LLM path — the default deterministic court builds no
    prompt at all.
    """
    from providers.base import LLMMessage

    candidates_json = json.dumps(
        [{k: v for k, v in c.items() if k != "source"} for c in candidates],
        indent=2, ensure_ascii=False,
    )
    base_prompt = _LLM_DEFENSE_PROMPT.format(candidates_json=candidates_json)
    judge_prompt = build_judge_prompt(base_prompt)
    response = await provider.chat(
        messages=[LLMMessage(
            role="user",
            content=judge_prompt,
        )],
        thinking=True,
        timeout=90.0,
    )
    raw = _extract_json_array(response.content or "")
    if not raw:
        return {"defense_materials": [], "parse_failed": True, "error": ""}
    materials: list[DefenseMaterial] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        materials.append({
            "id": str(item.get("id", "")),
            "defense_argument": str(item.get("defense_argument", "")),
            "candidate_confidence": _as_confidence(item.get("candidate_confidence")),
            "is_false_positive": _as_bool(item.get("is_false_positive")),
        })
    return {
        "defense_materials": materials,
        "parse_failed": False,
        "error": "",
    }


def build_llm_defense_producer(provider: Any) -> DefenseProducer:
    """Build the built-in LLM defense producer for explicit injection.

    The court node does NOT call the model by default (default off); a caller
    that wants model defense material passes this producer to
    run_review_court. The policy layer still recomputes severity/status.
    """

    async def produce(
        candidates: list[dict[str, Any]], _state: dict[str, Any]
    ) -> ModelDefenseOutput:
        return await _llm_defense_materials(provider, candidates)

    return produce


def _build_candidates(state: Phase0State) -> list[dict[str, Any]]:
    """Deterministically assemble every candidate the policy layer sees.

    Byte-compatible with the pre-split rule-based court, plus the runtime
    evidence copy (exit codes, output tails, DB snapshots, test counts) the
    preexisting-defect rule compares.
    """
    static_findings = state.get("static_findings", [])
    diff_results = state.get("diff_results", [])

    candidates: list[dict[str, Any]] = []

    for sf in static_findings:
        evidence_type = sf.get("evidence_type", "static_analysis")
        candidate = {**sf, "source": "static_analysis", "status": "candidate"}
        if evidence_type in NON_BLOCKER_EVIDENCE_TYPES:
            candidate["severity"] = (
                "MAJOR" if sf.get("severity") == "BLOCKER"
                else sf.get("severity", "MAJOR")
            )
            candidate["confidence"] = min(
                sf.get("confidence", 0.8), STATIC_CONFIDENCE_CEILING
            )
        candidates.append(candidate)

    for index, dr in enumerate(diff_results):
        if dr.get("verdict") not in ("REGRESSION", "AMBIGUOUS"):
            continue
        evidence_type = dr.get("evidence_type", "differential_execution")
        severity = dr.get("severity")
        if evidence_type in NON_BLOCKER_EVIDENCE_TYPES:
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
            # Runtime evidence copy — the policy layer compares Base/Head
            # behavior from these fields (preexisting-defect rule).
            "diff_result_index": index,
            "base_exit_code": dr.get("base_exit_code"),
            "head_exit_code": dr.get("head_exit_code"),
            "base_output": dr.get("base_output", ""),
            "head_output": dr.get("head_output", ""),
            "base_db_snapshot": dr.get("base_db_snapshot") or {},
            "head_db_snapshot": dr.get("head_db_snapshot") or {},
            "base_test_counts": dr.get("base_test_counts") or {},
            "head_test_counts": dr.get("head_test_counts") or {},
        })

    return _dedup_candidates(candidates)


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
        return []
    return []


def _invoke_defense_producer(
    producer: DefenseProducer,
    candidates: list[dict[str, Any]],
    state: Phase0State,
) -> ModelDefenseOutput | None:
    """Run the injected model layer; any failure degrades to deterministic.

    Producer exceptions are recorded as model_error so the policy layer can
    fall back to the fully deterministic path — never to auto-confirmation.
    """
    try:
        result = producer(candidates, state)
    except Exception as exc:
        return {"defense_materials": [], "parse_failed": False, "error": str(exc)}

    if inspect.isawaitable(result):

        async def _collect(
            awaitable: Awaitable[ModelDefenseOutput],
        ) -> ModelDefenseOutput:
            return await awaitable

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            try:
                return asyncio.run(_collect(result))
            except Exception as exc:
                return {
                    "defense_materials": [],
                    "parse_failed": False,
                    "error": str(exc),
                }
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _collect(result))
                return future.result(timeout=180)
        except Exception as exc:
            return {
                "defense_materials": [],
                "parse_failed": False,
                "error": str(exc),
            }

    if isinstance(result, dict):
        return result
    return {
        "defense_materials": [],
        "parse_failed": False,
        "error": "invalid defense producer output",
    }


def run_review_court(
    state: Phase0State,
    model_produce_defense: DefenseProducer | None = None,
) -> dict[str, Any]:
    """Run the two-layer Review Court (§14.1).

    model_produce_defense is an injected callable
    (candidates, state) -> ModelDefenseOutput, sync or async. It defaults to
    OFF: when absent the court is fully deterministic. The deterministic
    policy layer sees ALL candidates regardless of what the model ignored.
    """
    static_findings = state.get("static_findings", [])
    diff_results = state.get("diff_results", [])

    if not static_findings and not diff_results:
        return {
            "candidate_findings": [],
            "confirmed_findings": [],
            "court_audit": [],
        }

    candidates = _build_candidates(state)
    model_output: ModelDefenseOutput | None = None
    if model_produce_defense is not None:
        model_output = _invoke_defense_producer(
            model_produce_defense, candidates, state
        )

    result = policy_recalculate(
        candidates=candidates,
        model_output=model_output,
        contracts=state.get("contracts", []),
        diff_results=diff_results,
        generated_tests_path=state.get("generated_tests_path", ""),
        changed_files=_changed_files(state),
    )
    return {
        "candidate_findings": result["candidate_findings"],
        "confirmed_findings": result["confirmed_findings"],
        "court_audit": result["audit_entries"],
    }


def review_court_node(state: Phase0State) -> dict[str, Any]:
    """LangGraph node entry — deterministic policy court by default.

    The model defense layer is opt-in: callers that want LLM defense
    material inject build_llm_defense_producer(provider) via run_review_court.
    The policy layer recomputes severity/status either way, and every
    candidate is retained in state["court_audit"].
    """
    return run_review_court(state)

