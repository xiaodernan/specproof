
"""compile_contracts node — convert requirements into verifiable contracts.

Phase 0: rule-based parser with optional LLM fallback.
Phase 1+: full LLM-based compilation.

Counters (#192): ``compile_contracts_runs_total`` counts every invocation
and ``compile_contracts_outcomes_<word>_total`` records which compiler
produced the final contract list — the report's accepted_count alone
cannot tell "rules were sufficient" from "LLM never ran" from "LLM
produced nothing usable". The seven words are the closed vocabulary
COMPILE_OUTCOMES; a new word must move the declaration, the parity
family and the drift gate together.
"""

import asyncio
import json
import re
import time
from dataclasses import replace
from typing import Any

from agent.contracts.compile_report import (
    CompileReport,
    RejectedCandidate,
    merge_reports,
    requirement_digest,
)
from agent.contracts.records import checker_version_for
from agent.nodes._llm_provider import get_provider as _get_provider
from agent.state import Phase0State
from observability.metrics import incr
from providers.judge_persona import build_judge_prompt

#: Semantic version of the deterministic rule parser + contract templates
#: in this module. Bump whenever a pattern or template changes what the
#: rule-based pass produces; every compile report stamps this version so a
#: small candidate set can be traced to a parser change, not just the spec.
PARSER_RULE_VERSION = "1.0.0"

#: The closed set of ways a compile run can end (#192): which compiler
#: produced the final contract list. Mirrored by the parity family's regex
#: and the drift gate — a new word must move all three together.
COMPILE_OUTCOMES = frozenset({
    "empty_input",       # no requirement text — nothing to compile
    "approved_loaded",   # registry-approved contracts took precedence
    "rules_sufficient",  # >=2 rule matches — the LLM is never attempted
    "llm_disabled",      # sparse rules + use_llm=False — deterministic by request
    "llm_unavailable",   # sparse rules, LLM wanted, no provider configured
    "llm_replaced",      # LLM candidates accepted, the rule list is replaced
    "llm_degraded",      # LLM attempted, produced nothing usable; rules kept
})

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
    # ── P6 100-case families (case-21..100) ─────────────────────────
    "cache": {
        "checker_type": "redis",
        "expected_behavior": "User reads follow cache-aside semantics and email change "
        "evicts the user cache with a bounded TTL",
    },
    "concurrency": {
        "checker_type": "sql",
        "expected_behavior": "Stock updates must be guarded by optimistic locking — "
        "stale writes must be rejected, never silently overwritten",
    },
    "nplusone": {
        "checker_type": "sql",
        "expected_behavior": "List endpoints must serve users with a bounded number of "
        "SQL queries (no per-user query loops)",
    },
    "idempotent": {
        "checker_type": "rabbitmq",
        "expected_behavior": "Replaying the same order request must return the existing "
        "order without a second stock decrement",
    },
    "atomicity": {
        "checker_type": "sql",
        "expected_behavior": "Failed order placements must roll back stock decrements; "
        "cancelling an order must restock the product",
    },
    "order_event": {
        "checker_type": "rabbitmq",
        "expected_behavior": "order.created must be published to the documented "
        "exchange and routing key",
    },
    "email_format": {
        "checker_type": "http",
        "expected_behavior": "Malformed email values must be rejected with 4xx",
    },
    "boundary": {
        "checker_type": "sql",
        "expected_behavior": "Ordering exactly the available stock must succeed",
    },
    "order_amount": {
        "checker_type": "sql",
        "expected_behavior": "The order amount must equal unit price times quantity",
    },
    "test_strength": {
        "checker_type": "tests",
        "expected_behavior": "The repository's own test suite must keep its test "
        "methods and assertions (tests must not be weakened or disabled)",
    },
    "migration": {
        "checker_type": "sql",
        "expected_behavior": "Schema migrations must not drop or shrink existing "
        "columns, tables or constraints",
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
        "cache": [
            r"cache|ttl|evict|cached",
        ],
        "concurrency": [
            r"optimistic|concurr|lost update|stale write|@Version|version.*(check|guard)",
        ],
        "nplusone": [
            r"n\+1|query count|batch(ed)? query|aggregate query|single query",
        ],
        "idempotent": [
            r"idempoten|dedup|duplicate order|replay",
        ],
        "atomicity": [
            r"rollback|roll back|restock|compensat",
        ],
        "order_event": [
            r"order\.created|order.*(event|publish)|event.*order",
        ],
        "email_format": [
            r"email (must|is|be) valid|valid email|@Email|malformed",
        ],
        "boundary": [
            r"boundary (value|case|behavior)|exactly.*stock|full stock|entire stock",
        ],
        "order_amount": [
            r"amount|total price|price.*quantit",
        ],
        "test_strength": [
            r"assertion|@Disabled|test.*(weaken|disable|remove|delet)",
        ],
        "migration": [
            r"migration|ddl|schema\.sql|alter table",
            r"\b(column|table|constraint)\b.*(drop|remov|shrink|reduc)",
            r"(drop|remov|shrink|reduc).*\b(column|table|constraint)\b",
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


async def _llm_compile_contracts(
    text: str, provider: Any, repo_context: list[dict[str, Any]] | None = None,
) -> tuple[list[Any], list[str]]:
    """Use LLM to compile contracts from requirement text + retrieved context.

    Returns ``(raw_candidates, problems)``. ``problems`` explains why the
    LLM response produced nothing usable (call failure, missing or non-JSON
    array); per-candidate schema validation happens in the caller. This
    helper never raises — degradation is reported, never swallowed.

    The no-fake-pass judge persona is APPENDED after the base contract
    validation prompt via build_judge_prompt, keeping the stable base-prompt
    prefix byte-identical at the front (KV-cache-friendly ordering).
    """
    from providers.base import LLMMessage
    from providers.redaction import redact_text

    # P0-A3: scrub the untrusted spec before it leaves the host.
    safe_text, _scrubbed = redact_text(text[:4000])
    context_block = "\n".join(
        "[" + c.get("symbol", "?") + " @ " + c.get("path", "") + "]\n"
        + (c.get("content") or "")[:600]
        for c in (repo_context or [])[:8]
    ) or "(no repository context retrieved)"
    base_prompt = _LLM_CONTRACT_PROMPT.format(
        spec_text=safe_text, repo_context=context_block,
    )
    judge_prompt = build_judge_prompt(base_prompt)

    try:
        response = await provider.chat(
            messages=[LLMMessage(role="user", content=judge_prompt)],
            timeout=60.0,
        )
    except Exception as exc:  # noqa: BLE001
        return [], [f"LLM call failed: {exc}"]

    content = response.content or ""
    # Extract JSON array from response
    start = content.find("[")
    end = content.rfind("]") + 1
    if start < 0 or end <= start:
        return [], ["LLM response contained no JSON array"]
    try:
        parsed = json.loads(content[start:end])
    except Exception as exc:  # noqa: BLE001
        return [], [f"LLM response JSON parse failed: {exc}"]
    if not isinstance(parsed, list):
        return [], ["LLM response was not a JSON array"]
    for c in parsed:
        if isinstance(c, dict):
            c.setdefault("result", "UNVERIFIED")
            c.setdefault("evidence_ref", None)
    return parsed, []


def _elapsed_ms(started: float) -> int:
    """Milliseconds since *started* (perf_counter), clamped at 0."""
    return max(0, int((time.perf_counter() - started) * 1000))


def _running_loop() -> Any | None:
    """The running event loop, or None when outside async context.

    get_event_loop() is deprecated in 3.12 and raises under the
    pytest-asyncio policy, so probe get_running_loop() instead.
    """
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def _candidate_summary(candidate: dict[str, Any]) -> str:
    """Stable one-line candidate summary for the compile report."""
    cid = str(candidate.get("id") or "?")
    ctype = str(candidate.get("checker_type") or "?")
    requirement = str(candidate.get("requirement") or "")
    return f"{cid} [{ctype}]: {requirement[:80]}"


def _schema_problems_for(candidate: dict[str, Any]) -> list[str]:
    """Schema violations of one normalized candidate ([] = valid).

    Runs AFTER checker_type backfill, so only structural gaps remain: a
    contract must identify itself, name its checker family, and state both
    the requirement and the expected behavior it checks.
    """
    problems: list[str] = []
    cid = candidate.get("id")
    if not isinstance(cid, str) or not cid.strip():
        problems.append("missing or invalid id")
    ctype = candidate.get("checker_type")
    if not isinstance(ctype, str) or not ctype.strip():
        problems.append("missing or invalid checker_type")
    requirement = candidate.get("requirement")
    if not isinstance(requirement, str) or not requirement.strip():
        problems.append("missing or invalid requirement")
    behavior = candidate.get("expected_behavior")
    if not isinstance(behavior, str) or not behavior.strip():
        problems.append("missing or invalid expected_behavior")
    return problems


def _run_llm_pass(
    text: str,
    provider: Any,
    repo_context: list[dict[str, Any]],
    errors: list[str],
    digest: str,
) -> tuple[CompileReport, list[dict[str, Any]]]:
    """One LLM compilation pass, with per-pass reporting.

    Accepted candidates replace the deterministic list; schema-invalid
    candidates become rejected entries with their problems recorded in
    schema_errors; call/parse failures become degrade_reasons. The
    deterministic result is NEVER discarded because the LLM failed.
    """
    raw: list[Any] = []
    problems: list[str] = []
    try:
        if _running_loop() is not None:
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    _llm_compile_contracts(text, provider, repo_context),
                )
                raw, problems = future.result(timeout=30)
        else:
            raw, problems = asyncio.run(
                _llm_compile_contracts(text, provider, repo_context)
            )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"LLM contract compilation failed: {exc}")
        problems = [f"LLM contract compilation failed: {exc}"]

    degrade = list(problems)
    rejected: list[RejectedCandidate] = []
    schema_errors: list[str] = []
    accepted: list[dict[str, Any]] = []
    for c in raw:
        if not isinstance(c, dict):
            rejected.append(RejectedCandidate(
                reason="not_an_object",
                candidate_summary=f"<non-object>: {str(c)[:160]}",
            ))
            schema_errors.append(f"candidate is not an object: {str(c)[:160]}")
    normalized = _normalize_llm_contracts(
        [c for c in raw if isinstance(c, dict)]
    )
    for c in normalized:
        problems_for = _schema_problems_for(c)
        if problems_for:
            rejected.append(RejectedCandidate(
                reason="schema_invalid",
                candidate_summary=_candidate_summary(c),
            ))
            schema_errors.extend(
                f"{_candidate_summary(c)}: {p}" for p in problems_for
            )
        else:
            accepted.append(c)
    if raw and not accepted:
        degrade.append("LLM compilation produced no schema-valid contracts")
    elif not raw and not degrade:
        degrade.append("LLM compilation returned no contracts")

    report = CompileReport(
        parser_rule_version=PARSER_RULE_VERSION,
        llm_used=bool(accepted),
        candidate_count=len(raw),
        accepted_count=len(accepted),
        rejected=rejected,
        schema_errors=schema_errors,
        degrade_reasons=degrade,
        requirement_digest=digest,
        duration_ms=0,
    )
    return report, accepted


def compile_contracts_node(state: Phase0State) -> dict[str, Any]:
    """Compile requirements into a list of Contract dicts + a compile report.

    Deterministic rule-based parsing runs first; when the LLM is configured
    it may enrich a sparse result. An empty contract list is honest — the
    pipeline reports UNVERIFIED rather than inventing a generic contract.
    LLM failures are recorded in state["errors"] and explained in the §14.1
    compile report (state["compile_report"]), never silently swallowed.
    #192: emits compile_contracts_runs_total plus exactly one
    ``compile_contracts_outcomes_<word>_total`` per invocation
    (COMPILE_OUTCOMES is the closed vocabulary).
    """
    text = state.get("requirement_text", "")
    errors: list[str] = list(state.get("errors", []))
    started = time.perf_counter()
    digest = requirement_digest(text)

    # #192: count every compile execution that reaches this node
    incr("compile_contracts_runs_total")

    if not text:
        # #192: nothing to compile — the rule/LLM fork below is unreachable
        incr("compile_contracts_outcomes_empty_input_total")
        report = CompileReport(
            parser_rule_version=PARSER_RULE_VERSION,
            llm_used=False,
            candidate_count=0,
            accepted_count=0,
            rejected=[],
            schema_errors=[],
            degrade_reasons=[],
            requirement_digest=digest,
            duration_ms=_elapsed_ms(started),
        )
        return {"contracts": [], "compile_report": report.to_dict()}

    # P2: registry-approved contracts take precedence over implicit
    # compilation (they were explicitly approved by a human).
    approved_loaded = state.get("approved_contracts", [])
    # The key families the SPEC declares, read by the spec language
    # (#368). Every contract then carries the ones that belong to ITS
    # family — whichever path it came from.
    declared_keys = _declared_key_patterns(text)
    if approved_loaded:
        # #192: human-approved registry rows take precedence over any compilation
        incr("compile_contracts_outcomes_approved_loaded_total")
        for c in approved_loaded:
            c.setdefault("result", "UNVERIFIED")
            c.setdefault("evidence_ref", None)
            c.setdefault("approved", True)
            # §A task 6: registry-approved contracts carry their stored
            # version + checker implementation version; backfill defaults
            # for legacy rows so every contract in state is versioned.
            c.setdefault("version", 1)
            if not c.get("checker_version"):
                c["checker_version"] = checker_version_for(c.get("checker_type", ""))
        _apply_observes_keys(approved_loaded, declared_keys)
        report = CompileReport(
            parser_rule_version=PARSER_RULE_VERSION,
            llm_used=False,
            candidate_count=len(approved_loaded),
            accepted_count=len(approved_loaded),
            rejected=[],
            schema_errors=[],
            degrade_reasons=[],
            requirement_digest=digest,
            duration_ms=_elapsed_ms(started),
        )
        return {
            "contracts": approved_loaded,
            "errors": errors,
            "compile_report": report.to_dict(),
        }

    rule_contracts = _parse_requirements(text)
    rule_report = CompileReport(
        parser_rule_version=PARSER_RULE_VERSION,
        llm_used=False,
        candidate_count=len(rule_contracts),
        accepted_count=len(rule_contracts),
        rejected=[],
        schema_errors=[],
        degrade_reasons=[],
        requirement_digest=digest,
        duration_ms=0,
    )
    llm_report: CompileReport | None = None

    # LLM enrichment when the rule-based parser found few contracts.
    # The retrieved repository context (P2 RAG) rides along so contracts
    # are grounded in the actual code, not just the spec prose.
    repo_context = state.get("repo_context", [])
    use_llm = state.get("use_llm", True)
    provider = _get_provider() if use_llm else None
    if provider is not None and len(rule_contracts) < 2:
        llm_report, llm_contracts = _run_llm_pass(
            text, provider, repo_context, errors, digest
        )
        if llm_contracts:
            contracts = llm_contracts
            # #192: the LLM pass replaced the deterministic candidate list
            incr("compile_contracts_outcomes_llm_replaced_total")
            rule_report = replace(
                rule_report,
                accepted_count=0,
                rejected=[
                    RejectedCandidate(
                        reason="replaced_by_llm",
                        candidate_summary=_candidate_summary(c),
                    )
                    for c in rule_contracts
                ],
            )
        else:
            contracts = rule_contracts
            # #192: LLM attempted but produced nothing usable (degrade_reasons)
            incr("compile_contracts_outcomes_llm_degraded_total")
    elif provider is None and use_llm and len(rule_contracts) < 2:
        # #192: LLM wanted (use_llm=True, sparse rules) but no key configured
        incr("compile_contracts_outcomes_llm_unavailable_total")
        llm_report = CompileReport(
            parser_rule_version=PARSER_RULE_VERSION,
            llm_used=False,
            candidate_count=0,
            accepted_count=0,
            rejected=[],
            schema_errors=[],
            degrade_reasons=["LLM unavailable: LLM_API_KEY not configured"],
            requirement_digest=digest,
            duration_ms=0,
        )
        contracts = rule_contracts
    else:
        contracts = rule_contracts
        if len(rule_contracts) >= 2:
            # #192: by design — the rule parser was enough, the LLM is never
            # attempted for rich specs
            incr("compile_contracts_outcomes_rules_sufficient_total")
        else:
            # #192: use_llm=False with sparse rules — deterministic by request
            incr("compile_contracts_outcomes_llm_disabled_total")

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
        # §A task 6: every compiled contract carries an exact version
        # (implicit compilation starts at 1) and the checker
        # implementation version that produced it.
        c.setdefault("version", 1)
        if not c.get("checker_version"):
            c["checker_version"] = checker_version_for(c.get("checker_type", ""))
        cid = c.get("id", "")
        if cid in forbidden_by_id:
            c["forbidden_changes"] = forbidden_by_id[cid]
    # The key families this contract is about, as a FIELD (#368). The
    # syntax belongs to the spec language; the collector reads the field
    # and never re-parses prose. A contract that declares nothing gets an
    # empty list — "this contract names no key family", which is not the
    # same as "no keys exist".
    _apply_observes_keys(contracts, declared_keys)

    report = merge_reports(
        [rule_report, llm_report] if llm_report is not None else [rule_report]
    )
    report = replace(report, duration_ms=_elapsed_ms(started))
    return {
        "contracts": contracts,
        "errors": errors,
        "compile_report": report.to_dict(),
    }


def _declared_key_patterns(text: str) -> list[str]:
    """The key families the text DECLARES, read by the spec language.

    The syntax lives in ``agent.contracts.parser`` (#368): the spec
    language owns "observes keys: …", and every consumer asks it rather
    than keeping its own copy of the pattern.
    """
    from agent.contracts.parser import declared_key_patterns

    return declared_key_patterns(text)


def _declared_key_patterns_for_contract(
    contract_id: str, declared: list[str],
) -> list[str]:
    """The declared key families that belong to THIS contract.

    A declaration names keys; the contract that owns them is the one in
    that key family (the profile says what each family is called in
    this domain). A declaration that belongs to no family here is not
    attached to a guess — it simply reaches no contract.
    """
    from experiments.external_state import (
        key_family_of_contract,
        key_patterns_for_family,
    )

    return key_patterns_for_family(
        key_family_of_contract(contract_id), declared,
    )


def _apply_observes_keys(
    contracts: list[dict[str, Any]], declared: list[str],
) -> None:
    """Give every contract the key families it declared.

    A contract that already carries the field keeps it (the registry
    path may know better than the spec text does); a contract that does
    not gets the declarations that belong to its family.
    """
    for c in contracts:
        if "observes_keys" in c:
            continue
        c["observes_keys"] = _declared_key_patterns_for_contract(
            str(c.get("id") or ""), declared,
        )


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
        "CACHE": "redis",
        "CONCURRENCY": "sql",
        "NPLUSONE": "sql",
        "IDEMPOTENT": "rabbitmq",
        "ATOMICITY": "sql",
        "ORDER_EVENT": "rabbitmq",
        "EMAIL_FORMAT": "http",
        "BOUNDARY": "sql",
        "ORDER_AMOUNT": "sql",
        "TEST_STRENGTH": "tests",
        "MIGRATION": "sql",
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
