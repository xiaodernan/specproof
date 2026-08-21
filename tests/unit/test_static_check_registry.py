"""Completeness + fail-closed tests for the static checker registry (§14.1).

Pins three invariants of agent/checkers/registry.py against the real
run_static_checks node:

1. Completeness — every checker the node can dispatch is registered, every
   registered entry names a real, invokable implementation, and the node
   never bypasses the registry (no direct checker-function calls).
2. Metadata — every entry declares its check target, documented file
   types, output schema and severity cap ("MAJOR": static source verdicts
   can never reach BLOCKER; the node additionally caps confidence at 0.85).
3. Fail-closed — unknown checker names, unknown file types and unsupported
   (language, framework) targets raise / report NOT_IMPLEMENTED instead of
   silently reading as "no problems found".
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

import agent.nodes.run_static_checks as run_static_checks
from agent.checkers import java_source
from agent.checkers.registry import (
    ALL_REGISTRY,
    EXTENDED_REGISTRY,
    FILE_TYPE_MATRIX,
    FILE_TYPES,
    OUTPUT_SCHEMA,
    REGISTRY,
    CheckerSpec,
    UnknownCheckerError,
    UnknownFileTypeError,
    checker_by_name,
    dispatch_checker,
    file_type_status,
    matrix_note,
    require_checker,
    run_registered_checks,
)

NODE_PATH = Path(run_static_checks.__file__).resolve()

_EXTENDED_CHECKER_NAMES = (
    "check_schema_sql",
    "check_test_weakening",
    "check_forbidden_changes",
)


def _checker_fn_names() -> set[str]:
    return {c.__name__ for c in java_source._ALL_CHECKERS} | set(
        _EXTENDED_CHECKER_NAMES
    )


def _invoke(spec: CheckerSpec) -> list[dict[str, Any]]:
    """Invoke one registered checker the way its args_spec documents."""
    if spec.name == "check_schema_sql":
        return spec.fn("", "", {}, {})
    if spec.name == "check_forbidden_changes":
        return spec.fn({}, {}, [], "CONST-TEST")
    return spec.fn({}, {})


# ── 1. completeness ─────────────────────────────────────────────────────────


def test_registry_covers_every_checker_implementation() -> None:
    registered = {s.name for s in ALL_REGISTRY}
    assert registered == _checker_fn_names()
    assert len(ALL_REGISTRY) == len(registered), "registry ids must be unique"
    # REGISTRY keeps the uniform 2-dict signature run_registered_checks uses
    assert {s.name for s in REGISTRY} == {
        c.__name__ for c in java_source._ALL_CHECKERS
    }
    assert {s.name for s in EXTENDED_REGISTRY} == set(_EXTENDED_CHECKER_NAMES)


def test_node_never_bypasses_registry() -> None:
    """run_static_checks must not call individual checker functions directly.

    run_contract_checks is the registry path for the seven uniform checkers
    and is therefore exempt; every other checker function must be reached
    only through dispatch_checker.
    """
    tree = ast.parse(NODE_PATH.read_text(encoding="utf-8"))
    checker_names = _checker_fn_names()
    direct: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in checker_names
        ):
            direct.append(node.func.id)
    assert direct == []


def test_node_dispatches_extended_checkers_through_registry() -> None:
    tree = ast.parse(NODE_PATH.read_text(encoding="utf-8"))
    dispatched: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "dispatch_checker"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            dispatched.add(node.args[0].value)
    assert dispatched == set(_EXTENDED_CHECKER_NAMES)


def test_every_registered_entry_is_invokable() -> None:
    for spec in ALL_REGISTRY:
        result = _invoke(spec)
        assert isinstance(result, list), spec.name
        assert all(isinstance(f, dict) for f in result), spec.name


# ── 2. metadata ─────────────────────────────────────────────────────────────


def test_every_entry_declares_complete_metadata() -> None:
    for spec in ALL_REGISTRY:
        assert spec.name
        assert spec.check_target, spec.name
        assert spec.version, spec.name
        assert spec.args_spec, spec.name
        assert spec.evidence_level == "static", spec.name
        assert spec.can_block is False, spec.name
        assert spec.file_types, spec.name
        assert set(spec.file_types) <= set(FILE_TYPES), spec.name
        assert spec.output_schema == OUTPUT_SCHEMA, spec.name


def test_static_verdicts_are_capped_at_major() -> None:
    """Every registered source checker is severity-capped at MAJOR; the node
    additionally caps confidence at its static ceiling (0.85)."""
    assert run_static_checks._STATIC_CONFIDENCE_CEILING == 0.85
    for spec in ALL_REGISTRY:
        assert spec.severity_cap == "MAJOR", spec.name


def test_file_type_matrix_covers_every_checker_and_file_type() -> None:
    assert set(FILE_TYPE_MATRIX) == {s.name for s in ALL_REGISTRY}
    for name, row in FILE_TYPE_MATRIX.items():
        assert set(row) == set(FILE_TYPES), name
        for file_type, status in row.items():
            assert status in ("supported", "unsupported", "unverified"), (
                name, file_type, status,
            )
        assert "supported" in row.values(), name


# ── 3. honest compatibility matrix ──────────────────────────────────────────


_UNGUARDED_SCANNERS = (
    "check_unique_email",
    "check_token_invalidation",
    "check_event_once",
)


def test_unguarded_scanners_mark_foreign_inputs_unverified() -> None:
    """Checkers with no file-type guard would mechanically scan whatever
    text they were given, but no test ever exercised non-Java input — the
    matrix must say unverified, never supported."""
    for name in _UNGUARDED_SCANNERS:
        row = FILE_TYPE_MATRIX[name]
        assert row["java/main"] == "supported"
        for file_type in FILE_TYPES:
            if file_type == "java/main":
                continue
            assert row[file_type] == "unverified", (name, file_type)


def test_unexercised_input_kinds_are_honestly_unverified() -> None:
    # The node passes check_schema_sql / check_forbidden_changes only
    # src/main files; their behavior on test sources is unverified.
    assert FILE_TYPE_MATRIX["check_schema_sql"]["java/test"] == "unverified"
    assert FILE_TYPE_MATRIX["check_forbidden_changes"]["java/test"] == "unverified"


def test_filtered_checkers_declare_foreign_file_types_unsupported() -> None:
    """Checkers that filter by Java path suffix can never fire on other
    file types — documented unsupported, not silence-as-clean."""
    for name in (
        "check_auth_annotations",
        "check_transactional",
        "check_schema_compat",
        "check_endpoint_changes",
    ):
        row = FILE_TYPE_MATRIX[name]
        assert row["java/main"] == "supported"
        for file_type in FILE_TYPES:
            if file_type != "java/main":
                assert row[file_type] == "unsupported", (name, file_type)


# ── 4. fail-closed lookups ──────────────────────────────────────────────────


def test_unknown_checker_name_fails_closed() -> None:
    assert checker_by_name("check_does_not_exist") is None
    with pytest.raises(UnknownCheckerError, match="check_does_not_exist"):
        require_checker("check_does_not_exist")
    with pytest.raises(UnknownCheckerError, match="check_does_not_exist"):
        dispatch_checker("check_does_not_exist")


def test_unknown_file_type_fails_closed() -> None:
    with pytest.raises(UnknownFileTypeError, match="cobol"):
        file_type_status("check_auth_annotations", "cobol")


def test_unknown_checker_name_in_file_type_status_fails_closed() -> None:
    with pytest.raises(UnknownCheckerError):
        file_type_status("check_does_not_exist", "java/main")


def test_unsupported_target_reports_not_implemented_note() -> None:
    note = matrix_note("python", "django")
    assert note is not None and "NOT_IMPLEMENTED" in note
    findings, failures, run_note = run_registered_checks(
        {}, {}, language="python", framework="django",
    )
    assert findings == []
    assert failures == []
    assert run_note is not None and "NOT_IMPLEMENTED" in run_note


# ── 5. dispatch faithfulness ────────────────────────────────────────────────


def test_dispatch_checker_is_faithful_to_implementation() -> None:
    from agent.checkers.schema_and_tests import check_schema_sql

    base_schema = "CREATE TABLE users (email VARCHAR(255));"
    head_schema = "CREATE TABLE users (email VARCHAR(50));"
    direct = check_schema_sql(base_schema, head_schema, {}, {})
    dispatched = dispatch_checker(
        "check_schema_sql",
        base_schema=base_schema,
        head_schema=head_schema,
        base_files={},
        head_files={},
    )
    assert dispatched == direct
    assert dispatched
    assert dispatched[0]["contract_id"] == "MIGRATION-01"
    assert dispatched[0]["severity"] == "MAJOR"
