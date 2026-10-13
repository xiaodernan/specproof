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


# ── #255: the assertion family the "no assertion" rule recognises ──
# _ASSERT_RE previously named only 8 of JUnit's assertion forms, so a
# counterexample asserting with any of the rest was reported assertion-void.
# Each of these IS a real assertion, and none may be flagged.
ASSERTION_FORMS = [
    "assertEquals(\"a\", got);",
    "assertNotEquals(\"a\", got);",
    "assertTrue(got != null);",
    "assertFalse(got == null);",
    "assertNull(got);",
    "assertNotNull(got);",
    "assertSame(expected, got);",
    "assertNotSame(expected, got);",
    "assertArrayEquals(new int[]{1}, xs);",
    "assertIterableEquals(List.of(), ys);",
    "assertInstanceOf(String.class, got);",
    "assertLinesMatch(List.of(), zs);",
    "assertTimeout(Duration.ofSeconds(5), () -> got);",
    "assertTimeoutPreemptively(Duration.ofSeconds(5), () -> got);",
    "assertDoesNotThrow(() -> got);",
    "assertThrows(RuntimeException.class, () -> fail());",
    "assertAll(() -> assertNotNull(got));",
    "assertThat(got).isEqualTo(\"a\");",
]


def test_every_real_assertion_form_is_recognised() -> None:
    """A method asserting via any JUnit form is not 'no assertion' (#255).

    The false positive mattered: the review is what tells the reader whether
    a generated counterexample is worth trusting, and calling a test that
    does assert something assertion-void points the investigation at the
    wrong defect.
    """
    for form in ASSERTION_FORMS:
        code = (
            "package p;\n"
            "import org.junit.jupiter.api.Test;\n"
            "class T {\n"
            "  @Test void t() { Object got = null; Object expected = null;\n"
            "    int[] xs = null; Iterable ys = List.of(); Iterable zs = ys;\n"
            "    Duration d = Duration.ofSeconds(5);\n"
            "    " + form + "\n"
            "  }\n"
            "}\n"
        )
        problems = _problems(code)
        assert not any(
            "no assertion" in p for p in problems
        ), f"{form} was flagged as assertion-void"


def test_assertion_void_method_is_still_flagged() -> None:
    """The #255 widening must not blunt the rule it widened (#255).

    Every form above is accepted; a method with no assertion at all must
    still be reported, or the check stops meaning anything.
    """
    code = (
        "package p;\n"
        "import org.junit.jupiter.api.Test;\n"
        "class T {\n"
        "  @Test void t() { Object got = service.call(); }\n"
        "}\n"
    )
    problems = _problems(code)
    assert any("no assertion in test method" in p for p in problems)


def test_non_assertion_call_is_not_mistaken_for_one() -> None:
    """`assert` is a prefix, not a prefix-match on anything (#255).

    The widened alternation must still require the `(` and a word boundary —
    a helper named `assertionsFrom()` is not an assertion call.
    """
    code = (
        "package p;\n"
        "import org.junit.jupiter.api.Test;\n"
        "class T {\n"
        "  @Test void t() { assertionsFrom(service); }\n"
        "}\n"
    )
    problems = _problems(code)
    assert any("no assertion in test method" in p for p in problems)
