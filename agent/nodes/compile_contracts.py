
"""compile_contracts node — convert requirements into verifiable contracts.

Phase 0: rule-based parser with optional LLM fallback.
Phase 1+: full LLM-based compilation.
"""
import asyncio
import json
import os
import re
from typing import Any

from agent.state import Phase0State

_CONTRACT_TEMPLATES = {
    "auth": {
        "checker_type": "http",
        "expected_behavior": "Unauthenticated requests must receive 401 Unauthorized",
    },
    "unique": {
        "checker_type": "sql",
        "expected_behavior": (
            "Duplicate email insertion must be rejected with "
            "constraint violation or application error"
        ),
    },
    "token_invalidation": {
        "checker_type": "redis",
        "expected_behavior": "After email change, old token keys must be deleted from Redis",
    },
    "backward_compatible": {
        "checker_type": "openapi",
        "expected_behavior": "API schema must remain backward-compatible between base and head",
    },
    "event_once": {
        "checker_type": "rabbitmq",
        "expected_behavior": "Email change event must be published exactly once per change",
    },
    "transaction": {
        "checker_type": "sql",
        "expected_behavior": "Email update and token invalidation must be in same transaction",
    },
}

_LLM_CONTRACT_PROMPT = """You are a requirements analyst. Given a requirement specification,
extract all verifiable contracts as JSON.

For each requirement, produce a contract with:
- id: short kebab-case identifier (e.g. "AUTH-01", "UNIQUE-01")
- checker_type: one of [http, sql, redis, openapi, rabbitmq]
- requirement: the requirement text (max 200 chars)
- expected_behavior: concrete, testable description of expected behavior

Return a JSON array of contract objects. No other text.

Requirement specification:
{spec_text}

Repository context (retrieved symbol chunks relevant to this requirement —
use it to ground the contracts in real code, NEVER invent symbols):
{repo_context}

Contracts (JSON array):"""


def _parse_requirements(text: str) -> list[dict[str, Any]]:
    """Parse requirement text into contract candidates using regex rules."""
    contracts = []
    text_lower = text.lower()

    patterns = {
        "auth": [
            r"unauthorized|unauthenticated|not logged in|without auth|401",
            r"must (be|require) (authenticated|auth|login)",
            r"@PreAuthorize|isAuthenticated",
        ],
        "unique": [
            r"unique|duplicate|already (exists|taken|used)",
            r"email.*unique|unique.*email",
        ],
        "token_invalidation": [
            r"token.*invalid|invalidate.*token|old token",
            r"session.*expire|expire.*session|redis.*delete",
        ],
        "backward_compatible": [
            r"backward.compatible|api.*compatible|schema.*compatible",
            r"openapi|swagger|breaking.change",
        ],
        "event_once": [
            r"exactly once|idempotent|duplicate.*event|event.*once",
            r"rabbitmq|message.*queue|publish.*once",
            # Execution-only delivery regressions (wrong routing keys) are
            # declared as "publish to the documented routing key" prose.
            r"publish|routing",
        ],
        "transaction": [
            r"transaction|atomic|rollback|@Transactional",
            r"all.or.nothing|consistency",
        ],
    }

    for contract_type, regexes in patterns.items():
        for regex in regexes:
            if re.search(regex, text_lower):
                contracts.append({
                    "id": f"{contract_type.upper()}-01",
                    "requirement": text.strip().split("\n")[0][:120],
                    "checker_type": _CONTRACT_TEMPLATES[contract_type]["checker_type"],
                    "expected_behavior": _CONTRACT_TEMPLATES[contract_type]["expected_behavior"],
                    "result": "UNVERIFIED",
                    "evidence_ref": None,
                })
                break

    return contracts


def _get_provider() -> Any:
    """Create an LLM provider from env vars. Returns None if not configured."""
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key or api_key == "replace_me":
        return None
    try:
        from providers.openai_compatible import OpenAICompatibleProvider
        provider = OpenAICompatibleProvider(probe_on_init=False)
        return provider
    except Exception:
        return None


async def _llm_compile_contracts(
    text: str, provider: Any, repo_context: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Use LLM to compile contracts from requirement text + retrieved context."""
    from providers.base import LLMMessage
    from providers.redaction import redact_text

    # P0-A3: scrub the untrusted spec before it leaves the host.
    safe_text, _scrubbed = redact_text(text[:4000])
    context_block = "\n".join(
        "[" + c.get("symbol", "?") + " @ " + c.get("path", "") + "]\n"
        + (c.get("content") or "")[:600]
        for c in (repo_context or [])[:8]
    ) or "(no repository context retrieved)"
    prompt = _LLM_CONTRACT_PROMPT.format(
        spec_text=safe_text, repo_context=context_block,
    )

    try:
        response = await provider.chat(
            messages=[LLMMessage(role="user", content=prompt)],
            timeout=60.0,
        )
        content = response.content or ""
        # Extract JSON array from response
        start = content.find("[")
        end = content.rfind("]") + 1
        if start >= 0 and end > start:
            contracts = json.loads(content[start:end])
            if isinstance(contracts, list):
                for c in contracts:
                    c.setdefault("result", "UNVERIFIED")
                    c.setdefault("evidence_ref", None)
                return contracts
    except Exception:
        pass

    return []


def compile_contracts_node(state: Phase0State) -> dict[str, Any]:
    """Compile requirements into a list of Contract dicts.

    Deterministic rule-based parsing runs first; when the LLM is configured
    it may enrich a sparse result. An empty contract list is honest — the
    pipeline reports UNVERIFIED rather than inventing a generic contract.
    LLM failures are recorded in state["errors"], never silently swallowed.
    """
    text = state.get("requirement_text", "")
    errors: list[str] = list(state.get("errors", []))

    if not text:
        return {"contracts": []}

    # P2: registry-approved contracts take precedence over implicit
    # compilation (they were explicitly approved by a human).
    approved_loaded = state.get("approved_contracts", [])
    if approved_loaded:
        for c in approved_loaded:
            c.setdefault("result", "UNVERIFIED")
            c.setdefault("evidence_ref", None)
            c.setdefault("approved", True)
        return {"contracts": approved_loaded, "errors": errors}

    contracts = _parse_requirements(text)

    # LLM enrichment when the rule-based parser found few contracts.
    # The retrieved repository context (P2 RAG) rides along so contracts
    # are grounded in the actual code, not just the spec prose.
    repo_context = state.get("repo_context", [])
    provider = _get_provider() if state.get("use_llm", True) else None
    if provider is not None and len(contracts) < 2:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        _llm_compile_contracts(text, provider, repo_context),
                    )
                    llm_contracts = future.result(timeout=30)
            else:
                llm_contracts = asyncio.run(
                    _llm_compile_contracts(text, provider, repo_context)
                )
            if llm_contracts:
                normalized = _normalize_llm_contracts(llm_contracts)
                if normalized:
                    contracts = normalized
        except Exception as exc:  # noqa: BLE001
            errors.append(f"LLM contract compilation failed: {exc}")

    # Every contract starts UNVERIFIED; only real experiments set PASS/FAIL.
    # P2: contracts compiled directly from the spec the user explicitly
    # passed to verify carry IMPLICIT approval (approved=True). Contracts
    # loaded from the registry carry explicit approvals; the Review Court
    # checks this flag for BLOCKER condition 1.
    forbidden_by_id = _forbidden_changes_by_family(text)
    # Implicit approval only when the user did NOT demand registry approval:
    # with --use-approved-contracts and an empty registry, contracts stay
    # unapproved and the Review Court refuses BLOCKER on them.
    require_approval = state.get("require_approved_contracts", False)
    for c in contracts:
        c.setdefault("result", "UNVERIFIED")
        c.setdefault("evidence_ref", None)
        c.setdefault("approved", not require_approval)
        cid = c.get("id", "")
        if cid in forbidden_by_id:
            c["forbidden_changes"] = forbidden_by_id[cid]

    return {"contracts": contracts, "errors": errors}


def _forbidden_changes_by_family(text: str) -> dict[str, list[str]]:
    """Extract 'must not / never' clauses per canonical contract family.

    Uses the P2 structured parser; the result rides the contract dicts so
    the (future) constitution checker can verify them.
    """
    from agent.contracts.compiler import family_id_for
    from agent.contracts.parser import parse_requirements

    result: dict[str, list[str]] = {}
    parsed = parse_requirements(text)
    for req in parsed.requirements:
        for clause in req.forbidden_changes:
            for ctype in ("http", "sql", "redis", "openapi", "rabbitmq"):
                lowered = clause.lower()
                if (
                    (ctype == "http" and "auth" in lowered)
                    or (ctype == "sql" and (
                        "transaction" in lowered or "unique" in lowered
                        or "constraint" in lowered
                    ))
                    or (ctype == "redis" and (
                        "token" in lowered or "cache" in lowered
                        or "redis" in lowered
                    ))
                    or (ctype == "openapi" and (
                        "api" in lowered or "schema" in lowered
                    ))
                    or (ctype == "rabbitmq" and (
                        "event" in lowered or "message" in lowered
                    ))
                ):
                    family = family_id_for(ctype, clause)
                    result.setdefault(family, []).append(clause)
                    break
    return result


def _normalize_llm_contracts(contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fill in checker_type defaults for LLM-produced contracts."""
    type_by_prefix = {
        "AUTH": "http",
        "UNIQUE": "sql",
        "TOKEN_INVALIDATION": "redis",
        "BACKWARD_COMPATIBLE": "openapi",
        "EVENT_ONCE": "rabbitmq",
        "TRANSACTION": "sql",
    }
    for c in contracts:
        cid = str(c.get("id", ""))
        if not c.get("checker_type"):
            for prefix, ctype in type_by_prefix.items():
                if cid.upper().startswith(prefix):
                    c["checker_type"] = ctype
                    break
        c.setdefault("result", "UNVERIFIED")
        c.setdefault("evidence_ref", None)
    return contracts
