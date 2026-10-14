"""A toothless counterexample must not manufacture contract PASS (#262).

§4.2 asks the counterexample to move from "能编译" to "真能复现回归". The §14.1
review already knew how to detect a test that cannot fail, but its verdict was
written into ``generation_record.review`` and never read — so
``http_verdict == "COMPLIANT"`` ("Test passes in both Base and Head") mapped
straight to ``result = "PASS"`` for a test that had no way to fail.

These tests drive the REAL ``run_differential_node`` (stubbed only at
``run_with_cancel_checks``, the node's single execution seam) and the REAL
``review_generated_test``, so a regression in either side shows up.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent.nodes.run_differential import run_differential_node
from agent.testgen_review import review_generated_test

# Shape mirrors _run_generated_test's return contract.
_OK: dict[str, Any] = {
    "exit_code": 0, "stdout": "", "stderr": "", "test_counts": {}, "error": "",
}

# Invokes the code under test, asserts nothing -> cannot fail.
TOOTHLESS = """package com.specproof.demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class SpecProofGeneratedTest {
    @Test
    void exercisesAuthContract() {
        service.login("u@example.com", "secret");
    }
}
"""

# Genuinely asserts -> must remain eligible for PASS.
ASSERTING = """package com.specproof.demo;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class SpecProofGeneratedTest {
    @Test
    void exercisesAuthContract() {
        String got = changeEmail("fresh@example.com");
        assertEquals("ok", got);
    }
}
"""

AUTH_CONTRACTS: list[dict[str, Any]] = [{"id": "AUTH-01", "checker_type": "http"}]


def _node_module():
    import agent.nodes.run_differential as rd

    return rd


def _run_node(state: dict[str, Any]) -> dict[str, Any]:
    """Run the real node; only the execution seam is stubbed."""

    def fake(job_id: object, stage: str, fn: object, *args: object,
             **kwargs: object) -> Any:
        if stage == "maven_probe":
            return []
        return dict(_OK)

    rd = _node_module()
    original = rd.run_with_cancel_checks
    rd.run_with_cancel_checks = fake  # type: ignore[assignment]
    try:
        return run_differential_node(state)
    finally:
        rd.run_with_cancel_checks = original  # type: ignore[assignment]


def _diff_row(out: dict[str, Any]) -> dict[str, Any] | None:
    """The AUTH-01 generated_test_differential row, if the node emitted one."""
    for row in out.get("contract_results", []):
        if (
            row.get("contract_id") == "AUTH-01"
            and row.get("experiment") == "generated_test_differential"
        ):
            return row
    return None


def _state(tmp_path: Path, source: str | None, review: Any = "auto") -> dict[str, Any]:
    """Build node state; ``review="auto"`` computes it with the real reviewer."""
    base = tmp_path / "base"
    head = tmp_path / "head"
    base.mkdir(exist_ok=True)
    head.mkdir(exist_ok=True)
    gen = tmp_path / "SpecProofGeneratedTest.java"

    record: dict[str, Any] = {"source": "llm_generated", "test_file_sha256": ""}
    if source is not None:
        gen.write_text(source, encoding="utf-8")
        if review == "auto":
            record["review"] = review_generated_test(source, str(tmp_path))
        elif review is not None:
            record["review"] = review

    return {
        "repo_path": "",
        "app_dir": "",
        "base_workspace": str(base),
        "head_workspace": str(head),
        "generated_tests_path": str(gen) if source is not None else "",
        "contracts": list(AUTH_CONTRACTS),
        "generation_record": record,
    }


def _differential_row(
    tmp_path: Path,
    source: str | None,
    review: Any = "auto",
) -> dict[str, Any] | None:
    return _diff_row(_run_node(_state(tmp_path, source, review)))


# ── the contract verdict ────────────────────────────────────────────────────


def test_toothless_counterexample_is_unverified_not_pass(tmp_path: Path) -> None:
    """A test that cannot fail must not earn the contract a PASS (#262)."""
    row = _differential_row(tmp_path, TOOTHLESS)

    assert row is not None, "AUTH-01 must be exercised by the differential"
    assert row["result"] == "UNVERIFIED", (
        "a counterexample with no assertion exits 0 on both sides by "
        "construction; reporting PASS fabricates evidence"
    )


def test_demotion_carries_a_reason(tmp_path: Path) -> None:
    """The withheld green must say WHY, or it reads as an unexplained gap."""
    row = _differential_row(tmp_path, TOOTHLESS)

    assert row is not None
    assert row["result"] == "UNVERIFIED"
    assert row.get("details"), "the demotion carries no reason"
    assert "vacuous" in row["details"]


def test_genuinely_asserting_counterexample_still_passes(tmp_path: Path) -> None:
    """The fix must cost no real evidence (#262)."""
    row = _differential_row(tmp_path, ASSERTING)

    assert row is not None
    assert row["result"] == "PASS", (
        "a counterexample that really asserts must keep earning PASS"
    )
    assert "details" not in row, "no demotion, so no demotion reason"


def test_absent_review_leaves_pass_unchanged(tmp_path: Path) -> None:
    """No review is not evidence of a defect (#262 boundary).

    Demoting on a missing review would revoke PASS from every run predating
    the review stage, without proving anything about those tests.
    """
    row = _differential_row(tmp_path, ASSERTING, review=None)

    assert row is not None
    assert row["result"] == "PASS"


def test_stale_review_without_vacuous_key_is_not_demoted(tmp_path: Path) -> None:
    """A review predating ``checks.vacuous`` must not be read as vacuous."""
    stale = {"checks": {"test_count": 1}, "problems": []}
    row = _differential_row(tmp_path, ASSERTING, review=stale)

    assert row is not None
    assert row["result"] == "PASS"


def test_probe_row_is_untouched_by_the_demotion(tmp_path: Path) -> None:
    """The demotion is scoped to what the counterexample judged."""
    out = _run_node(_state(tmp_path, TOOTHLESS))
    rows = [r for r in out.get("contract_results", [])
            if r.get("contract_id") == "AUTH-01"]

    diff_rows = [r for r in rows
                 if r.get("experiment") == "generated_test_differential"]
    assert len(diff_rows) == 1
    assert diff_rows[0]["result"] == "UNVERIFIED"
    # The stub returns [] for maven_probe -> no probe row was emitted.
    assert not [r for r in rows if r.get("experiment") == "probe_differential"]


# ── the review-level vacuous signal ─────────────────────────────────────────


@pytest.mark.parametrize(
    ("method_body", "expected_vacuous"),
    [
        ("service.login(\"a\");", True),
        ("assertTrue(true);", True),
        ("assertFalse(false);", True),
        ("assertEquals(x, x);", True),
        ("assertTrue(true); assertEquals(\"ok\", got);", False),
        ("assertEquals(x, x); assertNotNull(got);", False),
        ("assertEquals(\"ok\", got);", False),
        ("assertSame(expected, got);", False),
        ("assertNotNull(got);", False),
    ],
)
def test_vacuous_classification(method_body: str, expected_vacuous: bool) -> None:
    """Vacuous means 'cannot fail', not 'mentions a trivial assertion'.

    The distinction is the whole point: a trivial assertion ALONGSIDE a real
    one still lets the test fail, so demoting there would discard real
    evidence.
    """
    code = (
        "package p;\n"
        "import org.junit.jupiter.api.Test;\n"
        "class T {\n"
        "  @Test void t() { Object x = null; Object got = null;\n"
        "    Object expected = null;\n"
        "    " + method_body + "\n"
        "  }\n"
        "}\n"
    )
    checks = review_generated_test(code, "/nonexistent-workspace")["checks"]
    assert checks["vacuous"] is expected_vacuous


def test_class_with_no_test_method_is_vacuous() -> None:
    """Zero @Test methods is equally unable to prove anything."""
    code = "package p;\nclass T { void helper() { assertTrue(true); } }\n"
    checks = review_generated_test(code, "/nonexistent-workspace")["checks"]
    assert checks["test_count"] == 0
    assert checks["vacuous"] is True


def test_vacuous_methods_lists_the_offending_indices() -> None:
    """One offending method among good ones is reported, not hidden."""
    code = (
        "package p;\n"
        "import org.junit.jupiter.api.Test;\n"
        "class T {\n"
        "  @Test void a() { service.call(); }\n"
        "  @Test void b() { assertEquals(\"ok\", got); }\n"
        "}\n"
    )
    checks = review_generated_test(code, "/nonexistent-workspace")["checks"]
    assert checks["vacuous"] is False, "the class as a whole can still fail"
    assert checks["vacuous_methods"] == ["1"]


def test_mixed_class_is_not_demoted(tmp_path: Path) -> None:
    """A class where ONE method can fail keeps PASS (#262).

    Demoting would throw away evidence because a second method happens to be
    weak — the review reports it (vacuous_methods), the verdict does not
    over-react to it.
    """
    mixed = """package com.specproof.demo;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class SpecProofGeneratedTest {
    @Test
    void weak() {
        service.call();
    }
    @Test
    void strong() {
        assertEquals("ok", changeEmail("f@example.com"));
    }
}
"""
    row = _differential_row(tmp_path, mixed)

    assert row is not None
    review = review_generated_test(mixed, str(tmp_path))
    assert review["checks"]["vacuous"] is False
    assert review["checks"]["vacuous_methods"] == ["1"]
    assert row["result"] == "PASS"

