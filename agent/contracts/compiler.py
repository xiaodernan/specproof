"""P2 — Contract candidate compiler.

Compiles structured requirements (agent/contracts/parser.py) into
machine-checkable contract candidates. Each candidate names:
  - which checker family verifies it (checker_type)
  - the concrete expected behaviour
  - where it came from (source + evidence snippet)

Candidates are PROPOSALS. They only become enforceable contracts after
human approval through the contract registry (agent/contracts/registry.py).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from agent.contracts.parser import Requirement


class ContractCandidate(BaseModel):
    id: str
    checker_type: str  # http | sql | redis | openapi | rabbitmq | constitution
    requirement: str
    requirement_ref: str
    expected_behavior: str
    forbidden_changes: list[str] = Field(default_factory=list)
    source: str  # spec | constitution | tests | docs
    evidence: str = ""
    result: str = "UNVERIFIED"
    evidence_ref: str | None = None
    approved: bool = False


_TYPE_RULES: list[tuple[str, re.Pattern[str], str]] = [
    (
        "http",
        re.compile(
            r"(?i)auth|authenticat|authoriz|401|403|permission|role|login|preauthorize|secured"
        ),
        "API endpoints must enforce the documented authentication/authorization rules",
    ),
    (
        "sql",
        re.compile(
            r"(?i)unique|duplicate|transaction|atomic|rollback|constraint"
            r"|foreign key|migration",
        ),
        "Database writes must preserve uniqueness and transactional guarantees",
    ),
    (
        "redis",
        re.compile(r"(?i)redis|cache|token.*invalid|session|ttl|expire"),
        "Cache/token state must match the documented invalidation semantics",
    ),
    (
        "openapi",
        re.compile(r"(?i)api.*compat|backward|schema|response.*shape|field|openapi|endpoint"),
        "The public API surface must remain backward-compatible",
    ),
    (
        "rabbitmq",
        re.compile(r"(?i)event|exactly.once|idempot|queue|message|publish|delivery|rabbitmq|outbox"),
        "Events must be published with the documented delivery guarantees",
    ),
]


def _candidate_id(requirement_id: str, checker_type: str, index: int) -> str:
    stem = re.sub(r"[^A-Z0-9]+", "-", requirement_id.upper()).strip("-")[:12]
    return stem + "-" + checker_type.upper()[:4] + "-" + str(index).zfill(2)


def compile_candidates(requirements: list[Requirement]) -> list[ContractCandidate]:
    """Deterministic requirement→contract compilation.

    Each requirement maps to at most ONE candidate per matching checker
    family. A requirement that matches nothing is reported honestly:
    the candidate list simply omits it (the matrix will show UNVERIFIED).
    """
    candidates: list[ContractCandidate] = []
    for req in requirements:
        index = 0
        haystack = (
            req.statement
            + " "
            + " ".join(ac.text for ac in req.acceptance_criteria)
            + " " + " ".join(req.forbidden_changes)
        )
        for checker_type, pattern, default_behavior in _TYPE_RULES:
            if not pattern.search(haystack):
                continue
            index += 1
            matching_criteria = [
                ac.text for ac in req.acceptance_criteria
                if pattern.search(ac.text)
            ]
            behavior = (
                matching_criteria[0][:300]
                if matching_criteria else default_behavior
            )
            candidates.append(ContractCandidate(
                id=_candidate_id(req.id, checker_type, index),
                checker_type=checker_type,
                requirement=req.statement[:200],
                requirement_ref=req.id,
                expected_behavior=behavior,
                forbidden_changes=req.forbidden_changes,
                source="spec",
                evidence="; ".join(matching_criteria[:3]),
            ))
    return candidates


def candidates_from_constitution(
    policy_texts: list[str],
) -> list[ContractCandidate]:
    """Extract candidate rules from repository constitution sources
    (README / ADR / docs). Every extracted rule is a proposal, not a
    contract: approval is always required.
    """
    candidates: list[ContractCandidate] = []
    rule_re = re.compile(
        r"(?im)^\s*[-*]\s*(?P<rule>(?:must|must not|never|always"
        r"|\u6240\u6709|\u5fc5\u987b|\u7981\u6b62)\b[^\n]{10,240})"
    )
    seen: set[str] = set()
    for source_text in policy_texts:
        for m in rule_re.finditer(source_text):
            rule = m.group("rule").strip()
            key = rule.lower()
            if key in seen:
                continue
            seen.add(key)
            for checker_type, pattern, _default in _TYPE_RULES:
                if pattern.search(rule):
                    cid = (
                        "CONST-" + checker_type.upper()[:4]
                        + "-" + str(len(candidates) + 1).zfill(2)
                    )
                    candidates.append(ContractCandidate(
                        id=cid,
                        checker_type=checker_type,
                        requirement=rule[:200],
                        requirement_ref="constitution",
                        expected_behavior=rule[:300],
                        source="constitution",
                        evidence=rule[:200],
                    ))
                    break
    return candidates


def family_id_for(checker_type: str, behavior: str) -> str:
    """Map a candidate to the canonical contract family id used by the
    deterministic checker registry (AUTH-01, UNIQUE-01, ...). The registry
    keeps human-readable candidate ids; the pipeline dispatches on the
    family id so checkers and the Review Court stay exact-match."""
    b = behavior.lower()
    if checker_type == "http":
        return "AUTH-01"
    if checker_type == "redis":
        return "TOKEN_INVALIDATION-01"
    if checker_type == "openapi":
        return "BACKWARD_COMPATIBLE-01"
    if checker_type == "rabbitmq":
        return "EVENT_ONCE-01"
    if checker_type == "sql":
        if "transaction" in b or "atomic" in b or "rollback" in b:
            return "TRANSACTION-01"
        return "UNIQUE-01"
    if checker_type == "constitution":
        if "auth" in b or "permission" in b or "role" in b:
            return "AUTH-01"
        return "UNIQUE-01"
    return checker_type.upper() + "-01"


def dedupe_candidates(
    candidates: list[ContractCandidate],
) -> list[ContractCandidate]:
    """Merge candidates that express the same (checker_type, behaviour)."""
    by_key: dict[tuple[str, str], ContractCandidate] = {}
    for c in candidates:
        key = (c.checker_type, c.expected_behavior.lower()[:120])
        existing = by_key.get(key)
        if existing is None or c.source == "spec" and existing.source != "spec":
            by_key[key] = c
    return list(by_key.values())
