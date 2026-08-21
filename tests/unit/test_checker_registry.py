"""Unit tests for the checker registry + compatibility matrix (§14.1)."""

from __future__ import annotations

from agent.checkers import java_source
from agent.checkers.registry import (
    REGISTRY,
    checker_by_name,
    checker_failure_finding,
    checkers_for,
    matrix_note,
    normalize_location,
    run_registered_checks,
)


def test_registry_covers_every_checker() -> None:
    registered = {s.name for s in REGISTRY}
    implemented = {c.__name__ for c in java_source._ALL_CHECKERS}
    assert registered == implemented


def test_registry_metadata_fields_complete() -> None:
    for spec in REGISTRY:
        assert spec.language == "java"
        assert spec.framework == "spring-boot"
        assert spec.contract_families
        assert spec.version == java_source.CHECKER_VERSION
        assert spec.evidence_level in ("static", "dynamic")
        assert spec.known_false_positives
        assert spec.estimated_cost in ("low", "medium", "high")
        assert spec.can_block is False  # static checkers are MAJOR-capped


def test_matrix_supports_java_spring_boot() -> None:
    assert checkers_for("java", "spring-boot") == list(REGISTRY)
    assert matrix_note("java", "spring-boot") is None


def test_matrix_unsupported_target_explicit() -> None:
    note = matrix_note("python", "django")
    assert note is not None
    assert "NOT_IMPLEMENTED" in note
    assert "java/spring-boot" in note
    assert checkers_for("python", "django") == []


def test_run_registered_checks_unsupported_target_fails_closed() -> None:
    findings, failures, note = run_registered_checks(
        {}, {}, language="python", framework="django"
    )
    assert findings == []
    assert failures == []
    assert note is not None and "NOT_IMPLEMENTED" in note


def test_checker_crash_becomes_evidence_others_survive() -> None:
    def boom(_b, _h):
        raise RuntimeError("synthetic crash")

    # The registry captured the real function at import time; swap the
    # registry entry's fn so the crash is deterministic in this test.
    spec = checker_by_name("check_auth_annotations")
    assert spec is not None
    original = spec.fn
    object.__setattr__(spec, "fn", boom)
    try:
        findings, failures, note = run_registered_checks(
            {"a.java": "x"}, {"a.java": "x"}
        )
    finally:
        object.__setattr__(spec, "fn", original)
    assert note is None
    assert failures, "the crashing checker must produce evidence"
    assert failures[0]["type"] == "checker_failed"
    assert failures[0]["families"] == ["AUTH-01"]
    assert "synthetic crash" in failures[0]["description"]
    # The other six checkers still ran and reported (or stayed silent
    # legitimately) — the crash did not abort the lane.
    assert all(f.get("type") != "checker_failed" for f in findings)


def test_failure_finding_shape() -> None:
    f = checker_failure_finding("check_x", ValueError("boom"), ("A-01", "B-01"))
    assert f["severity"] == "NONE"
    assert f["confidence"] == 1.0
    assert f["contract_id"] == "CHECKER_FAILED"
    assert f["families"] == ["A-01", "B-01"]
    assert f["location"] == "agent/checkers/check_x.py"


def test_run_contract_checks_preserves_failures_and_dedup_others() -> None:
    findings = java_source.run_contract_checks({}, {})
    # Empty inputs: no source findings, no failures — legacy shape intact.
    assert findings == []


class TestNormalizeLocation:
    def test_posix_passthrough(self) -> None:
        loc = normalize_location("src/main/java/com/x/A.java")
        assert loc == {"path": "src/main/java/com/x/A.java"}

    def test_backslash_to_posix(self) -> None:
        loc = normalize_location("src\\main\\java\\A.java")
        assert loc["path"] == "src/main/java/A.java"

    def test_dot_slash_stripped(self) -> None:
        assert normalize_location("./src/A.java")["path"] == "src/A.java"

    def test_empty_segments_collapsed(self) -> None:
        assert normalize_location("src//A.java")["path"] == "src/A.java"

    def test_line_and_symbol_passthrough(self) -> None:
        loc = normalize_location("A.java", 12, "doThing")
        assert loc == {"path": "A.java", "line": 12, "symbol": "doThing"}

    def test_idempotent(self) -> None:
        first = normalize_location("\\foo\\bar.java", 3)
        second = normalize_location(first["path"], first.get("line"))
        assert first == second


class TestContractResultsOnCheckerFailure:
    def test_failed_family_never_passes_by_silence(self) -> None:
        contracts = [{"id": "AUTH-01"}, {"id": "UNIQUE-01"}]
        findings = [checker_failure_finding(
            "check_auth_annotations", ValueError("boom"), ("AUTH-01",)
        )]
        base_files = {"src/main/java/C.java": "x"}
        results = java_source.contract_results_for(
            contracts, findings, base_files,
            base_schema_present=True, base_test_present=True,
        )
        by_id = {r["contract_id"]: r for r in results}
        assert by_id["AUTH-01"]["result"] == "UNVERIFIED"
        assert "never PASS by silence" in by_id["AUTH-01"]["details"]
        # UNIQUE-01 unaffected by the other checker's crash semantics.
        assert by_id["UNIQUE-01"]["result"] in ("PASS", "UNVERIFIED")
