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

Registry contents (the complete run_static_checks checker inventory):

* REGISTRY — the 7 uniform java-source diff checkers. Their `fn` takes the
  standard (base_files, head_files) signature; run_registered_checks()
  executes them for the registered (language, framework) target.
* EXTENDED_REGISTRY — the 3 heterogeneous checkers run_static_checks
  dispatches by name through dispatch_checker():
    check_schema_sql        MIGRATION-01     schema.sql DDL + JPA entity
                                             @Column constraints
    check_test_weakening    TEST_STRENGTH-01 JUnit test sources
    check_forbidden_changes per-contract     "forbidden changes" clauses
                                             from the requirement
* ALL_REGISTRY = REGISTRY + EXTENDED_REGISTRY — the single inventory every
  lookup searches (checker_by_name / require_checker / dispatch_checker).

Every entry carries: name (the registry id), check_target, file_types
(documented input kinds, values from FILE_TYPES), output_schema (finding
keys), severity_cap ("MAJOR": static source verdicts can never reach
BLOCKER; the node additionally caps confidence at 0.85) and args_spec
(the call signature the node and the replay path use).

Fail-closed rules (the checker × file-type compatibility matrix lives in
docs/design/STATIC_CHECKER_MATRIX.md and is mirrored by FILE_TYPE_MATRIX):

* unknown checker name  -> UnknownCheckerError (require_checker /
                           dispatch_checker / file_type_status)
* unknown file type     -> UnknownFileTypeError (file_type_status)
* unsupported target    -> NOT_IMPLEMENTED note (matrix_note /
                           run_registered_checks)
* crashing checker      -> CHECKER_FAILED evidence; the contract family
                           stays UNVERIFIED, never PASS by silence
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import agent.checkers.constitution as constitution
import agent.checkers.java_source as java_source
import agent.checkers.schema_and_tests as schema_and_tests


@dataclass(frozen=True)
class CheckerSpec:
    """Registry metadata for one source-diff checker (§14.1).

    ``name`` is the registry id used by every lookup. ``file_types`` names
    the documented input kinds (values from FILE_TYPES); the per-file-type
    support status lives in FILE_TYPE_MATRIX. ``output_schema`` lists the
    finding keys every emission carries. ``severity_cap`` is the strongest
    verdict the checker may emit: static source verdicts are capped at MAJOR
    (BLOCKER requires real execution evidence).
    """

    name: str
    language: str
    framework: str
    contract_families: tuple[str, ...]
    version: str
    evidence_level: str
    known_false_positives: str
    estimated_cost: str
    can_block: bool
    check_target: str
    file_types: tuple[str, ...]
    output_schema: tuple[str, ...]
    severity_cap: str
    args_spec: str
    fn: Callable[..., list[dict[str, Any]]] = field(repr=False)


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


#: Canonical finding keys every registered checker emits. checker_failed
#: evidence additionally carries "families" (severity NONE, confidence 1.0).
OUTPUT_SCHEMA: tuple[str, ...] = (
    "id",
    "contract_id",
    "severity",
    "type",
    "description",
    "evidence_type",
    "confidence",
    "location",
    "source",
)

#: File-type vocabulary for the compatibility matrix (§14.1). "java/main"
#: and "java/test" are the two Java input streams run_static_checks reads;
#: "sql/ddl" is src/main/resources/schema.sql; the rest are foreign file
#: types the node never reads today.
FILE_TYPES: tuple[str, ...] = (
    "java/main",
    "java/test",
    "sql/ddl",
    "python",
    "typescript",
    "go",
    "pom",
    "yaml",
)

#: Status vocabulary for FILE_TYPE_MATRIX:
#:   supported   implemented for this file type (documented scope); the
#:               per-checker test coverage is listed in the matrix doc
#:   unsupported explicitly out of scope (path filters, documented scope)
#:   unverified  the checker would mechanically scan this input but no test
#:               ever exercised it — honest, never claimed as supported
FILE_TYPE_STATUSES: frozenset[str] = frozenset(
    {"supported", "unsupported", "unverified"}
)

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
        check_target=(
            "security annotations on mutating endpoints (*Controller.java "
            "methods with @Put/Post/Delete/PatchMapping)"
        ),
        file_types=("java/main",),
        output_schema=OUTPUT_SCHEMA,
        severity_cap="MAJOR",
        args_spec="base_files, head_files",
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
        check_target=(
            "write methods in *Service.java must keep @Transactional and "
            "write operations must not move outside a transaction boundary"
        ),
        file_types=("java/main",),
        output_schema=OUTPUT_SCHEMA,
        severity_cap="MAJOR",
        args_spec="base_files, head_files",
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
        check_target="duplicate-email guard (existsByEmail) must not be removed",
        file_types=("java/main",),
        output_schema=OUTPUT_SCHEMA,
        severity_cap="MAJOR",
        args_spec="base_files, head_files",
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
        check_target=(
            "old-token invalidation call sites (invalidateOldTokens / "
            "redisTemplate.delete) must not be removed"
        ),
        file_types=("java/main",),
        output_schema=OUTPUT_SCHEMA,
        severity_cap="MAJOR",
        args_spec="base_files, head_files",
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
        check_target="event publish count (convertAndSend) must not increase",
        file_types=("java/main",),
        output_schema=OUTPUT_SCHEMA,
        severity_cap="MAJOR",
        args_spec="base_files, head_files",
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
        check_target="API DTO fields must not be removed or renamed",
        file_types=("java/main",),
        output_schema=OUTPUT_SCHEMA,
        severity_cap="MAJOR",
        args_spec="base_files, head_files",
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
        check_target=(
            "public endpoint surface (HTTP verb, path) must not shrink or "
            "change"
        ),
        file_types=("java/main",),
        output_schema=OUTPUT_SCHEMA,
        severity_cap="MAJOR",
        args_spec="base_files, head_files",
        fn=java_source.check_endpoint_changes,
    ),
)


#: Heterogeneous checkers the node dispatches by name (dispatch_checker).
#: Their fn signatures differ from the uniform 2-dict shape, so they are
#: documented (args_spec) rather than run by run_registered_checks.
EXTENDED_REGISTRY: tuple[CheckerSpec, ...] = (
    CheckerSpec(
        name="check_schema_sql",
        language="sql",
        framework="jpa-entity+ddl",
        contract_families=("MIGRATION-01",),
        version=schema_and_tests.CHECKER_VERSION,
        evidence_level="static",
        known_false_positives=(
            "SQL types are whitespace-normalized before comparison; "
            "line-level constraints (PRIMARY/UNIQUE/KEY/INDEX/FOREIGN) are "
            "skipped by the parser"
        ),
        estimated_cost="low",
        can_block=False,
        check_target=(
            "schema.sql DDL (tables/columns must not drop, shrink or change "
            "type) + JPA entity @Column constraints (nullable/unique/length "
            "must not weaken)"
        ),
        file_types=("sql/ddl", "java/main"),
        output_schema=OUTPUT_SCHEMA,
        severity_cap="MAJOR",
        args_spec="base_schema, head_schema, base_files, head_files",
        fn=schema_and_tests.check_schema_sql,
    ),
    CheckerSpec(
        name="check_test_weakening",
        language="java",
        framework="junit",
        contract_families=("TEST_STRENGTH-01",),
        version=schema_and_tests.CHECKER_VERSION,
        evidence_level="static",
        known_false_positives=(
            "assertion counting is regex-based (assert*/verify/andExpect); "
            "refactors that inline assertions can read as weakening"
        ),
        estimated_cost="low",
        can_block=False,
        check_target=(
            "test suite strength: @Test count, @Disabled additions and "
            "assertion counts must not drop"
        ),
        file_types=("java/test",),
        output_schema=OUTPUT_SCHEMA,
        severity_cap="MAJOR",
        args_spec="base_test_files, head_test_files",
        fn=schema_and_tests.check_test_weakening,
    ),
    CheckerSpec(
        name="check_forbidden_changes",
        language="java",
        framework="spring-boot",
        # The contract id is supplied per contract at run time; the
        # pseudo-family marks the constitution rules as contract-driven.
        contract_families=("FORBIDDEN-*",),
        version=constitution.CHECKER_VERSION,
        evidence_level="static",
        known_false_positives=(
            "clause keywords are matched by regex; composed annotations use "
            "the documented equivalence set"
        ),
        estimated_cost="low",
        can_block=False,
        check_target=(
            "constitution 'forbidden changes' clauses from the requirement "
            "(annotation removal / duplicate publish / unique guard / token "
            "invalidation / DTO field removal)"
        ),
        file_types=("java/main",),
        output_schema=OUTPUT_SCHEMA,
        severity_cap="MAJOR",
        args_spec="base_files, head_files, forbidden_clauses, contract_id",
        fn=constitution.check_forbidden_changes,
    ),
)


#: The complete run_static_checks checker inventory, in dispatch order.
ALL_REGISTRY: tuple[CheckerSpec, ...] = REGISTRY + EXTENDED_REGISTRY


def checker_by_name(name: str) -> CheckerSpec | None:
    """Lookup one registered checker across the full inventory; None when
    unregistered (honest miss). For fail-closed lookups use require_checker."""
    for spec in ALL_REGISTRY:
        if spec.name == name:
            return spec
    return None


class UnknownCheckerError(LookupError):
    """A checker name is not in the registry — fail closed, never run zero checks."""


class UnknownFileTypeError(LookupError):
    """A file type is outside the FILE_TYPES vocabulary — fail closed."""


def require_checker(name: str) -> CheckerSpec:
    """Fail-closed lookup: unknown checker names raise UnknownCheckerError.

    The honest miss (checker_by_name) returns None; this is the strict entry
    every dispatch path uses, so a typo in a checker name can never silently
    read as "no checks ran".
    """
    spec = checker_by_name(name)
    if spec is None:
        known = ", ".join(sorted(s.name for s in ALL_REGISTRY))
        raise UnknownCheckerError(
            f"unknown checker {name!r} (registered: {known})"
        )
    return spec


def dispatch_checker(name: str, **kwargs: Any) -> list[dict[str, Any]]:
    """Fail-closed invocation by registry name (§14.1).

    run_static_checks dispatches the three heterogeneous checkers through
    this entry point. Keyword arguments are forwarded to the registered
    callable (see its args_spec); an unknown name raises
    UnknownCheckerError instead of silently running zero checks.
    """
    spec = require_checker(name)
    return spec.fn(**kwargs)


def file_type_status(name: str, file_type: str) -> str:
    """Support status of a registered checker for one file type.

    Unknown checker names and file types outside FILE_TYPES raise — the
    matrix never guesses and never reports an unclassified input as clean.
    """
    require_checker(name)
    if file_type not in FILE_TYPES:
        raise UnknownFileTypeError(
            f"unknown file type {file_type!r} (known: {', '.join(FILE_TYPES)})"
        )
    return FILE_TYPE_MATRIX[name][file_type]


def _status_row(
    supported: tuple[str, ...],
    unsupported: tuple[str, ...],
    unverified: tuple[str, ...],
) -> dict[str, str]:
    """One FILE_TYPE_MATRIX row; every file type must be classified.

    Fail-fast at import: a file type left out of all three categories is a
    registry bug, not a silent "unclassified".
    """
    row: dict[str, str] = {}
    for file_type in FILE_TYPES:
        if file_type in supported:
            row[file_type] = "supported"
        elif file_type in unsupported:
            row[file_type] = "unsupported"
        elif file_type in unverified:
            row[file_type] = "unverified"
        else:
            raise ValueError(f"file type {file_type!r} not classified")
    return row


#: Checker × file-type compatibility matrix (§14.1, mirrored by
#: docs/design/STATIC_CHECKER_MATRIX.md — the registry is the source of
#: truth). "unverified" cells are inputs the checker would mechanically
#: scan (no path guard) but that no test has ever exercised.
FILE_TYPE_MATRIX: dict[str, dict[str, str]] = {
    "check_auth_annotations": _status_row(
        supported=("java/main",),
        unsupported=("java/test", "sql/ddl", "python", "typescript", "go",
                     "pom", "yaml"),
        unverified=(),
    ),
    "check_transactional": _status_row(
        supported=("java/main",),
        unsupported=("java/test", "sql/ddl", "python", "typescript", "go",
                     "pom", "yaml"),
        unverified=(),
    ),
    "check_unique_email": _status_row(
        supported=("java/main",),
        unsupported=(),
        unverified=("java/test", "sql/ddl", "python", "typescript", "go",
                    "pom", "yaml"),
    ),
    "check_token_invalidation": _status_row(
        supported=("java/main",),
        unsupported=(),
        unverified=("java/test", "sql/ddl", "python", "typescript", "go",
                    "pom", "yaml"),
    ),
    "check_event_once": _status_row(
        supported=("java/main",),
        unsupported=(),
        unverified=("java/test", "sql/ddl", "python", "typescript", "go",
                    "pom", "yaml"),
    ),
    "check_schema_compat": _status_row(
        supported=("java/main",),
        unsupported=("java/test", "sql/ddl", "python", "typescript", "go",
                     "pom", "yaml"),
        unverified=(),
    ),
    "check_endpoint_changes": _status_row(
        supported=("java/main",),
        unsupported=("java/test", "sql/ddl", "python", "typescript", "go",
                     "pom", "yaml"),
        unverified=(),
    ),
    "check_schema_sql": _status_row(
        supported=("sql/ddl", "java/main"),
        unsupported=("python", "typescript", "go", "pom", "yaml"),
        unverified=("java/test",),
    ),
    "check_test_weakening": _status_row(
        supported=("java/test",),
        unsupported=("java/main", "sql/ddl", "python", "typescript", "go",
                     "pom", "yaml"),
        unverified=(),
    ),
    "check_forbidden_changes": _status_row(
        supported=("java/main",),
        unsupported=("sql/ddl", "python", "typescript", "go", "pom", "yaml"),
        unverified=("java/test",),
    ),
}


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
