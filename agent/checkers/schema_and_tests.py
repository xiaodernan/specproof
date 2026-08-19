"""Deterministic source-diff checkers for the P6 case families.

check_schema_sql    MIGRATION-01: schema.sql / entity column definitions
                    must not drop or shrink existing columns, tables or
                    constraints (cases 40-48).
check_test_weakening TEST_STRENGTH-01: the repository's own test suite
                    must not lose test methods, assertions or gain
                    @Disabled (cases 87-91).

Both checkers are conservative: they only fire on REMOVALS/WEAKENING.
Additions (new tables/columns/tests/assertions) are never regressions,
which is exactly what the negative cases in those categories assert.
"""
from __future__ import annotations

import re
from typing import Any

#: Implementation version of the schema/test-strength checkers — stamped
#: onto compiled contracts as checker_version (§A task 6).
CHECKER_VERSION = "1.0.0"

_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*?)\)\s*;",
    re.DOTALL | re.IGNORECASE,
)
_COLUMN_RE = re.compile(
    r"^\s*(\w+)\s+([A-Za-z]+(?:\([^)]*\))?)",
    re.MULTILINE,
)
_ENTITY_FIELD_RE = re.compile(
    r"@Column(?:\(([^)]*)\))?\s*"
    r"(?:@\w+(?:\([^)]*\))?\s*)*"
    r"private\s+([\w<>., ]+?)\s+(\w+)\s*;",
    re.DOTALL,
)


def _finding(
    contract_id: str,
    ftype: str,
    description: str,
    location: str,
    severity: str = "MAJOR",
    confidence: float = 0.85,
) -> dict[str, Any]:
    return {
        "id": "SRC-" + contract_id.split("-")[0] + "-" + ftype[:4].upper(),
        "contract_id": contract_id,
        "severity": severity,
        "type": ftype,
        "description": description,
        "evidence_type": "java_source_diff",
        "confidence": confidence,
        "location": location,
        "source": "contract_checker",
    }


def _parse_schema(schema_sql: str) -> dict[str, dict[str, str]]:
    """table -> {column: sql type}. Line-level constraints/keys are skipped."""
    tables: dict[str, dict[str, str]] = {}
    for match in _TABLE_RE.finditer(schema_sql or ""):
        table = match.group(1).lower()
        columns: dict[str, str] = {}
        for line in match.group(2).splitlines():
            stripped = line.strip().rstrip(",")
            if not stripped:
                continue
            if re.match(
                r"(?i)^(primary|unique|key|constraint|index|foreign)\b", stripped,
            ):
                continue
            column = _COLUMN_RE.match(stripped)
            if column:
                columns[column.group(1).lower()] = column.group(2).upper()
        if columns:
            tables[table] = columns
    return tables


def check_schema_sql(
    base_schema: str,
    head_schema: str,
    base_files: dict[str, str],
    head_files: dict[str, str],
) -> list[dict[str, Any]]:
    """MIGRATION-01: DDL/entity columns must not shrink or disappear."""
    findings: list[dict[str, Any]] = []
    location = "src/main/resources/schema.sql"

    base_tables = _parse_schema(base_schema)
    head_tables = _parse_schema(head_schema)
    for table, base_columns in base_tables.items():
        head_columns = head_tables.get(table)
        if head_columns is None:
            findings.append(_finding(
                "MIGRATION-01", "table_removed",
                "Table '" + table + "' present in Base schema.sql but missing "
                "in Head — destructive migration",
                location,
            ))
            continue
        for column, sql_type in base_columns.items():
            if column not in head_columns:
                findings.append(_finding(
                    "MIGRATION-01", "column_removed",
                    "Column '" + table + "." + column + "' present in Base "
                    "schema.sql but removed in Head — destructive migration",
                    location,
                ))
            elif head_columns[column] != sql_type:
                findings.append(_finding(
                    "MIGRATION-01", "column_type_changed",
                    "Column '" + table + "." + column + "' type changed from "
                    + sql_type + " to " + head_columns[column] + " — may "
                    "truncate or corrupt existing data",
                    location,
                ))

    # Entity-level column constraints: removing @Column params (nullable,
    # unique, length) weakens the DDL Hibernate generates.
    for rel in sorted(base_files):
        head = head_files.get(rel)
        if head is None or "@Column" not in base_files[rel]:
            continue
        base_fields = {
            field: _column_params(args or "")
            for args, _ftype, field in _ENTITY_FIELD_RE.findall(base_files[rel])
        }
        head_fields = {
            field: _column_params(args or "")
            for args, _ftype, field in _ENTITY_FIELD_RE.findall(head)
        }
        for field, base_params in base_fields.items():
            head_params = head_fields.get(field)
            if head_params is None:
                continue
            if base_params and not head_params:
                findings.append(_finding(
                    "MIGRATION-01", "constraint_removed",
                    "@Column constraint removed from field " + field + " in "
                    + rel,
                    rel,
                ))
                continue
            for param in ("nullable=false", "unique=true"):
                if param in base_params and param not in head_params:
                    findings.append(_finding(
                        "MIGRATION-01", "constraint_removed",
                        "@Column(" + param + ") removed from field " + field
                        + " in " + rel + " — constraint weakened",
                        rel,
                    ))
            base_len = _length_of(base_params)
            head_len = _length_of(head_params)
            if base_len is not None and head_len is not None and head_len < base_len:
                findings.append(_finding(
                    "MIGRATION-01", "column_type_changed",
                    "Column length reduced for field " + field + " in " + rel
                    + ": " + str(base_len) + " -> " + str(head_len)
                    + " — may truncate existing data",
                    rel,
                ))
    return findings


def _column_params(args: str) -> set[str]:
    return {
        part.strip().replace(" ", "").lower()
        for part in args.split(",")
        if part.strip()
    } - {""}


def _length_of(params: set[str]) -> int | None:
    for param in params:
        match = re.fullmatch(r"length\s*=\s*(\d+)", param.replace(" ", ""))
        if match:
            return int(match.group(1))
    return None


_ASSERTION_RE = re.compile(r"\b(?:assert\w+|verify)\s*\(")
_AND_EXPECT_RE = re.compile(r"\.andExpect\s*\(")


def check_test_weakening(
    base_test_files: dict[str, str], head_test_files: dict[str, str],
) -> list[dict[str, Any]]:
    """TEST_STRENGTH-01: the repo's own tests must not lose strength."""
    findings: list[dict[str, Any]] = []
    for rel in sorted(base_test_files):
        base = base_test_files[rel]
        head = head_test_files.get(rel)
        if head is None:
            findings.append(_finding(
                "TEST_STRENGTH-01", "test_file_removed",
                "Test file " + rel + " present in Base but deleted in Head "
                "— regression coverage removed",
                rel,
            ))
            continue
        base_tests = base.count("@Test")
        head_tests = head.count("@Test")
        if head_tests < base_tests:
            findings.append(_finding(
                "TEST_STRENGTH-01", "test_removed",
                "Test methods removed in " + rel + ": " + str(base_tests)
                + " -> " + str(head_tests),
                rel,
            ))
        if "@Disabled" in head and "@Disabled" not in base:
            findings.append(_finding(
                "TEST_STRENGTH-01", "test_disabled",
                "@Disabled added in " + rel + " — existing test no longer runs",
                rel,
            ))
        base_assertions = _assertion_count(base)
        head_assertions = _assertion_count(head)
        if head_assertions < base_assertions:
            findings.append(_finding(
                "TEST_STRENGTH-01", "assertions_weakened",
                "Assertions removed in " + rel + ": " + str(base_assertions)
                + " -> " + str(head_assertions) + " — tests no longer verify "
                "the documented behavior",
                rel,
            ))
    return findings


def _assertion_count(text: str) -> int:
    return (
        len(_ASSERTION_RE.findall(text))
        + len(_AND_EXPECT_RE.findall(text))
    )
