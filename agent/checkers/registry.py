"""Checker registry + compatibility matrix (§14.1 run_static_checks).

Every source-diff checker is registered with its metadata: applicable
language, framework, contract families, checker version, evidence level,
known-false-positive notes, estimated cost, and whether its findings may
block. The compatibility matrix maps (language, framework) targets to the
checkers that may run on them; any unsupported target is reported as an
explicit NOT_IMPLEMENTED note (same fail-closed culture as the execution
adapter matrix) instead of being silently treated as clean.

Checker exceptions become CHECKER_FAILED evidence — never an empty result:
a crashing checker must not read as "no problems found".

All path/line/symbol locations flow through normalize_location so reports,
inline comments and capsules point at the same canonical position.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import agent.checkers.java_source as java_source


@dataclass(frozen=True)
class CheckerSpec:
    """Registry metadata for one source-diff checker (§14.1)."""

    name: str
    language: str
    framework: str
    contract_families: tuple[str, ...]
    version: str
    evidence_level: str
    known_false_positives: str
    estimated_cost: str
    can_block: bool
    fn: Callable[[dict[str, str], dict[str, str]], list[dict[str, Any]]] = field(
        repr=False,
    )


def normalize_location(
    path: str, line: int | None = None, symbol: str | None = None,
) -> dict[str, Any]:
    """Canonical location: posix path without leading ./, optional line/symbol.

    Idempotent: normalizing an already-normalized location is a no-op.
    Windows backslashes are converted to posix so reports, inline comments
    and capsules agree on one spelling.
    """
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    out: dict[str, Any] = {"path": "/".join(parts)}
    if line is not None:
        out["line"] = int(line)
    if symbol is not None:
        out["symbol"] = symbol
    return out


# ── Registry (single source of truth for checker metadata) ────────────────

REGISTRY: tuple[CheckerSpec, ...] = (
    CheckerSpec(
        name="check_auth_annotations",
        language="java",
        framework="spring-boot",
        contract_families=("AUTH-01",),
        version=java_source.CHECKER_VERSION,
        evidence_level="static",
        known_false_positives=(
            "composed annotations are matched by the documented equivalence "
            "set (source-text heuristic, no meta-annotation resolution)"
        ),
        estimated_cost="low",
        can_block=False,
        fn=java_source.check_auth_annotations,
    ),
    CheckerSpec(
        name="check_transactional",
        language="java",
        framework="spring-boot",
        contract_families=("TRANSACTION-01",),
        version=java_source.CHECKER_VERSION,
        evidence_level="static",
        known_false_positives=(
            "programmatic transactions are invisible to the source heuristic"
        ),
        estimated_cost="low",
        can_block=False,
        fn=java_source.check_transactional,
    ),
    CheckerSpec(
        name="check_unique_email",
        language="java",
        framework="spring-boot",
        contract_families=("UNIQUE-01",),
        version=java_source.CHECKER_VERSION,
        evidence_level="static",
        known_false_positives=(
            "custom repository method names are matched heuristically"
        ),
        estimated_cost="low",
        can_block=False,
        fn=java_source.check_unique_email,
    ),
    CheckerSpec(
        name="check_token_invalidation",
        language="java",
        framework="spring-boot",
        contract_families=("TOKEN_INVALIDATION-01",),
        version=java_source.CHECKER_VERSION,
        evidence_level="static",
        known_false_positives=(
            "invalidation via other cache APIs is invisible to the heuristic"
        ),
        estimated_cost="low",
        can_block=False,
        fn=java_source.check_token_invalidation,
    ),
    CheckerSpec(
        name="check_event_once",
        language="java",
        framework="spring-boot",
        contract_families=("EVENT_ONCE-01",),
        version=java_source.CHECKER_VERSION,
        evidence_level="static",
        known_false_positives=(
            "publish sites outside convertAndSend are invisible to the heuristic"
        ),
        estimated_cost="low",
        can_block=False,
        fn=java_source.check_event_once,
    ),
    CheckerSpec(
        name="check_schema_compat",
        language="java",
        framework="spring-boot",
        contract_families=("BACKWARD_COMPATIBLE-01",),
        version=java_source.CHECKER_VERSION,
        evidence_level="static",
        known_false_positives=(
            "DTO detection by path/name suffix is the documented approximation"
        ),
        estimated_cost="low",
        can_block=False,
        fn=java_source.check_schema_compat,
    ),
    CheckerSpec(
        name="check_endpoint_changes",
        language="java",
        framework="spring-boot",
        contract_families=("OPENAPI-01",),
        version=java_source.CHECKER_VERSION,
        evidence_level="static",
        known_false_positives=(
            "route templates are matched textually, not via the Spring "
            "mapping model"
        ),
        estimated_cost="low",
        can_block=False,
        fn=java_source.check_endpoint_changes,
    ),
)


def checker_by_name(name: str) -> CheckerSpec | None:
    """Lookup one registered checker; None when unregistered (honest miss)."""
    for spec in REGISTRY:
        if spec.name == name:
            return spec
    return None


#: Compatibility matrix: (language, framework) -> applicable checker names.
#: Unsupported targets are NOT_IMPLEMENTED, never silently treated as clean.
MATRIX: dict[tuple[str, str], tuple[str, ...]] = {
    ("java", "spring-boot"): tuple(s.name for s in REGISTRY),
}


def matrix_note(language: str, framework: str) -> str | None:
    """NOT_IMPLEMENTED note for unsupported targets; None when supported."""
    if (language, framework) in MATRIX:
        return None
    supported = ", ".join(lang + "/" + fw for (lang, fw) in MATRIX)
    return (
        "NOT_IMPLEMENTED: no static checker registered for target "
        f"{language}/{framework} (supported: {supported})"
    )


def checkers_for(language: str, framework: str) -> list[CheckerSpec]:
    """Applicable checkers for a target, in registry order."""
    names = MATRIX.get((language, framework), ())
    return [s for s in REGISTRY if s.name in names]


def checker_failure_finding(
    name: str,
    exc: BaseException,
    families: tuple[str, ...] = (),
) -> dict[str, Any]:
    """CHECKER_FAILED evidence — a crashing checker is a finding, not silence."""
    return {
        "id": "CHECKER-FAILED-" + name.upper(),
        "contract_id": "CHECKER_FAILED",
        "severity": "NONE",
        "type": "checker_failed",
        "families": list(families),
        "description": (
            f"checker {name} raised {type(exc).__name__}: {exc} — "
            "the checked contracts stay UNVERIFIED, never PASS by silence"
        ),
        "evidence_type": "checker_failed",
        "confidence": 1.0,
        "location": str(
            normalize_location("agent/checkers/" + name + ".py")["path"]
        ),
        "source": "checker_registry",
    }


def run_registered_checks(
    base_files: dict[str, str],
    head_files: dict[str, str],
    language: str = "java",
    framework: str = "spring-boot",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    """Run the registered checkers for a target.

    Returns (findings, checker_failures, matrix_note). On an unsupported
    target: no checkers run and the NOT_IMPLEMENTED note explains why the
    result set is empty. On a checker exception: CHECKER_FAILED evidence is
    emitted and the surviving checkers still report their own findings.
    """
    note = matrix_note(language, framework)
    if note is not None:
        return [], [], note
    findings: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for spec in checkers_for(language, framework):
        try:
            findings.extend(spec.fn(base_files, head_files))
        except Exception as exc:  # noqa: BLE001 — evidence, never silence
            failures.append(
                checker_failure_finding(spec.name, exc, spec.contract_families)
            )
    return findings, failures, None
