"""Unit tests for the generated-test review stage (§14.1)."""

from __future__ import annotations

from agent.testgen_review import review_generated_test

GOOD_TEST = """
package com.specproof.demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SpecProofGeneratedTest {

    @Test
    void freshEmailChangeMustSucceed() {
        String got = changeEmail("fresh@example.com");
        assertEquals("ok", got);
    }
}
"""


def _problems(code: str) -> list[str]:
    review = review_generated_test(code, "/nonexistent-workspace")
    return [p["check"] + ":" + p["problem"] for p in review["problems"]]


def test_good_test_has_only_jar_dependency_notes() -> None:
    review = review_generated_test(GOOD_TEST, "/nonexistent-workspace")
    assert review["checks"]["package"] == "com.specproof.demo"
    assert review["checks"]["test_count"] == 1
    # changeEmail is an unresolvable symbol -> one honest flagged import-free
    # note? No: imports only — no import lines besides JUnit -> no problems.
    assert review["problems"] == []


def test_missing_package_flagged() -> None:
    code = "class T { @Test void t() { assertTrue(true); } }"
    problems = _problems(code)
    assert any(p.startswith("package:") for p in problems)


def test_zero_tests_flagged() -> None:
    code = "package p;\nclass T { void t() {} }"
    problems = _problems(code)
    assert any(p.startswith("test_count:") for p in problems)


def test_trivial_assertion_flagged() -> None:
    code = (
        "package p;\n"
        "class T {\n"
        "  @Test void t() { assertTrue(true); }\n"
        "}\n"
    )
    problems = _problems(code)
    assert any("trivial constant assertion" in p for p in problems)


def test_self_comparing_assertion_flagged() -> None:
    code = (
        "package p;\n"
        "class T {\n"
        "  @Test void t() { assertEquals(x, x); }\n"
        "}\n"
    )
    problems = _problems(code)
    assert any("compares a value with itself" in p for p in problems)


def test_no_assertion_flagged() -> None:
    code = (
        "package p;\n"
        "class T {\n"
        "  @Test void t() { doSomething(); }\n"
        "}\n"
    )
    problems = _problems(code)
    assert any("no assertion in test method" in p for p in problems)


def test_import_not_in_workspace_flagged(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Existing.java").write_text(
        "class Existing {}\n", encoding="utf-8",
    )
    code = (
        "package p;\n"
        "import com.other.MissingThing;\n"
        "class T { @Test void t() { assertTrue(false); } }\n"
    )
    problems = _problems(code)
    # assertTrue(false) is not a constant-true short circuit — fine.
    assert any(p.startswith("unavailable_dependency:") for p in problems)
    # Importing an existing class is not flagged.
    code2 = (
        "package p;\n"
        "import p.Existing;\n"
        "class T { @Test void t() { assertTrue(false); } }\n"
    )
    review2 = review_generated_test(code2, str(tmp_path))
    assert not any(
        p["check"] == "unavailable_dependency" for p in review2["problems"]
    )
