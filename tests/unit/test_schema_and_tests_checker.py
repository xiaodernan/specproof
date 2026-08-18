"""Regression tests for the P6 static checkers.

Incident (B's case-17 pipeline probe): _ENTITY_FIELD_RE.findall() returns
3-tuples (@Column args, field type, field name) but the checker unpacked
only 2 values — ValueError: too many values to unpack in run_static_checks.
The fix unpacks all three groups AND makes the @Column parentheses
optional, so bare "@Column" annotations (the shape that previously never
matched and therefore masked the bug) are parsed instead of skipped.
These tests pin every supported annotation/DDL shape so the incident
cannot return silently.
"""
from __future__ import annotations

import pytest

from agent.checkers.schema_and_tests import (
    _ENTITY_FIELD_RE,
    _column_params,
    _parse_schema,
    check_schema_sql,
    check_test_weakening,
)


def _fields(source: str) -> dict[str, str]:
    return {
        field: args or ""
        for args, _ftype, field in _ENTITY_FIELD_RE.findall(source)
    }


# ── _ENTITY_FIELD_RE shape coverage (the incident surface) ──────

def test_entity_field_regex_matches_bare_column():
    """Bare @Column (no parentheses) must parse as a field with no args."""
    assert _fields("@Column\n    private Integer stock;") == {"stock": ""}


def test_entity_field_regex_matches_empty_parens():
    assert _fields("@Column()\n    private Integer stock;") == {"stock": ""}


def test_entity_field_regex_matches_full_args():
    source = (
        "@Column(nullable = false, unique = true, length = 255)\n"
        "    private String email;"
    )
    fields = _fields(source)
    assert set(fields) == {"email"}
    assert _column_params(fields["email"]) == {
        "nullable=false", "unique=true", "length=255",
    }


def test_entity_field_regex_skips_other_annotations():
    """A @Version annotation between @Column and the field must not break
    the match (the annotation-skipping middle group)."""
    source = (
        "@Column(nullable = false)\n"
        "@Version\n"
        "    private Long version;"
    )
    assert set(_fields(source)) == {"version"}


def test_column_params_empty_is_empty_set():
    assert _column_params("") == set()


# ── check_schema_sql end-to-end (the run_static_checks path) ────

def test_check_schema_sql_detects_removed_constraint():
    base = {"demo/entity/Product.java": (
        "class Product {\n"
        "    @Column(nullable = false)\n"
        "    private Integer stock;\n"
        "}"
    )}
    head = {"demo/entity/Product.java": (
        "class Product {\n"
        "    @Column\n"
        "    private Integer stock;\n"
        "}"
    )}
    findings = check_schema_sql("", "", base, head)
    assert any(
        f["contract_id"] == "MIGRATION-01"
        and f["type"] == "constraint_removed"
        and "stock" in f["description"]
        for f in findings
    )


def test_check_schema_sql_detects_length_reduction():
    base = {"demo/entity/User.java": (
        "class User {\n"
        "    @Column(nullable = false, unique = true, length = 255)\n"
        "    private String email;\n"
        "}"
    )}
    head = {"demo/entity/User.java": (
        "class User {\n"
        "    @Column(nullable = false, unique = true, length = 50)\n"
        "    private String email;\n"
        "}"
    )}
    findings = check_schema_sql("", "", base, head)
    assert any(f["type"] == "column_type_changed" for f in findings)


def test_check_schema_sql_detects_ddl_removals():
    base_schema = (
        "CREATE TABLE IF NOT EXISTS users (\n"
        "    id BIGINT AUTO_INCREMENT PRIMARY KEY,\n"
        "    email VARCHAR(255) NOT NULL UNIQUE\n"
        ");\n"
    )
    head_schema = (
        "CREATE TABLE IF NOT EXISTS users (\n"
        "    id BIGINT AUTO_INCREMENT PRIMARY KEY\n"
        ");\n"
    )
    findings = check_schema_sql(base_schema, head_schema, {}, {})
    types = {f["type"] for f in findings}
    assert "column_removed" in types


def test_check_schema_sql_table_dropped():
    base_schema = (
        "CREATE TABLE IF NOT EXISTS orders (\n"
        "    id BIGINT AUTO_INCREMENT PRIMARY KEY\n"
        ");\n"
    )
    findings = check_schema_sql(base_schema, "", {}, {})
    assert any(f["type"] == "table_removed" for f in findings)


def test_check_schema_sql_additions_are_not_findings():
    base_schema = (
        "CREATE TABLE IF NOT EXISTS users (\n"
        "    id BIGINT AUTO_INCREMENT PRIMARY KEY\n"
        ");\n"
    )
    head_schema = base_schema + (
        "CREATE TABLE IF NOT EXISTS shipping (\n"
        "    id BIGINT AUTO_INCREMENT PRIMARY KEY\n"
        ");\n"
    )
    assert check_schema_sql(base_schema, head_schema, {}, {}) == []


def test_parse_schema_normalizes_whitespace():
    tidy = (
        "CREATE TABLE IF NOT EXISTS products (\n"
        "    id BIGINT AUTO_INCREMENT PRIMARY KEY,\n"
        "    stock INT NOT NULL\n"
        ");\n"
    )
    spaced = (
        "CREATE  TABLE  IF  NOT  EXISTS  products (\n"
        "    id   BIGINT AUTO_INCREMENT PRIMARY KEY,\n"
        "    stock  INT  NOT NULL\n"
        ");\n"
    )
    assert _parse_schema(tidy) == _parse_schema(spaced)


# ── check_test_weakening ────────────────────────────────────────

def test_check_test_weakening_detects_disabled_and_removed():
    base = {"demo/UserControllerTest.java": (
        "@Test\n    void secure() {}\n    @Test\n    void secureTwo() {}\n"
    )}
    head = {"demo/UserControllerTest.java": (
        "@Test\n    @Disabled(\"flaky\")\n    void secure() {}\n"
    )}
    findings = check_test_weakening(base, head)
    types = {f["type"] for f in findings}
    assert "test_disabled" in types
    assert "test_removed" in types


def test_check_test_weakening_detects_deleted_file():
    base = {"demo/UserControllerTest.java": "@Test\n    void secure() {}\n"}
    findings = check_test_weakening(base, {})
    assert any(f["type"] == "test_file_removed" for f in findings)


def test_check_test_weakening_ignores_strengthening():
    base = {"demo/UserControllerTest.java": (
        "mockMvc.perform(get(\"/x\")).andExpect(status().isOk());\n"
    )}
    head = {"demo/UserControllerTest.java": (
        "mockMvc.perform(get(\"/x\"))\n"
        "    .andExpect(status().isOk())\n"
        "    .andExpect(jsonPath(\"$.id\").isNumber());\n"
    )}
    assert check_test_weakening(base, head) == []


@pytest.mark.parametrize("source", [
    "@Column\n    private Integer stock;",
    "@Column()\n    private Integer stock;",
    "@Column(nullable = false)\n    private Integer stock;",
])
def test_findall_always_yields_three_groups(source: str):
    """The incident contract: findall() must yield exactly 3 groups for
    every supported @Column shape — never a 2-tuple the checker would
    mis-unpack."""
    for groups in _ENTITY_FIELD_RE.findall(source):
        assert len(groups) == 3
