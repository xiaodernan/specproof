"""Generated-test review stage (§14.1 generate_counterexamples).

After generation and compilation, the test source is reviewed by
deterministic rules before it becomes evidence: package declaration,
class name (unique inside the Head workspace), test count, assertion
short-circuits, and imports of classes that do not exist in the Head
workspace sources (unavailable dependencies). Every problem is reported
with its check name — the review never silently passes a suspect test.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_PACKAGE_RE = re.compile(r"\bpackage\s+([\w.]+)\s*;")
_CLASS_RE = re.compile(r"\bclass\s+(\w+)\b")
_IMPORT_RE = re.compile(r"\bimport\s+([\w.]+)\s*;")
_TEST_RE = re.compile(r"@Test\b")
# The assertion family the review recognises. Every entry is a real JUnit
# assertion method (``Assertions``/``AssertionsJUnit``/Hamcrest bridge), so a
# method whose only assertion is one of them is NOT assertion-void.
#
# #255: this list used to be ``True|False|Equals|NotEquals|Null|NotNull|Throws|
# DoesNotThrow`` — 8 of JUnit's ~17 forms. A counterexample asserting with
# ``assertSame``/``assertArrayEquals``/``assertTimeout``/``assertAll``/
# ``assertInstanceOf``/``assertLinesMatch``/``assertIterableEquals``/
# ``assertNotSame``/``assertTimeoutPreemptively`` was reported as having "no
# assertion in test method": 9 measured false positives, each one telling the
# reader to distrust a test that does assert something. Order is irrelevant —
# alternation backtracks, so the ``Timeout`` prefix still lets the longer
# ``assertTimeoutPreemptively`` match.
_ASSERT_NAMES = (
    "All|ArrayEquals|DoesNotThrow|Equals|False|InstanceOf|IterableEquals|"
    "LinesMatch|NotEquals|NotNull|NotSame|Null|Same|That|Throws|Timeout|"
    "TimeoutPreemptively|True"
)
_ASSERT_RE = re.compile(r"\bassert(?:" + _ASSERT_NAMES + r")\s*\(")


def _methods_with_test_annotations(code: str) -> list[str]:
    """Return the body text of every @Test-annotated method (approximate).

    Splits on @Test blocks; good enough for review-level statistics and
    explicitly documented as an approximation.
    """
    parts = _TEST_RE.split(code)
    return [p for p in parts[1:] if p.strip()]


def _trivial_assertions(method_body: str) -> list[str]:
    """Detect trivially passing assertions inside one test method body."""
    problems: list[str] = []
    for pattern in (
        r"assertTrue\(\s*true\s*\)",
        r"assertFalse\(\s*false\s*\)",
    ):
        if re.search(pattern, method_body):
            problems.append("trivial constant assertion")
    for _match in re.finditer(
        r"assert(?:Equals|NotEquals)\(([^,()]*(?:\([^()]*\))?[^,()]*),\s*\1\s*\)",
        method_body,
    ):
        problems.append("assertion compares a value with itself")
    if not _ASSERT_RE.search(method_body):
        problems.append("no assertion in test method")
    return problems


# Assertion calls that PASS whatever the code under test does: the right-hand
# side repeats the left-hand, or it is a compile-time constant. Counting them
# is what lets the review tell "has a trivial assertion AND a real one" apart
# from "only ever had trivial ones" — the difference decides whether a passing
# run can be trusted at all (#262).
_TRIVIAL_PATTERNS = (
    re.compile(r"assertTrue\(\s*true\s*\)"),
    re.compile(r"assertFalse\(\s*false\s*\)"),
)
_SELF_COMPARE_RE = re.compile(
    r"assert(?:Equals|NotEquals)\(([^,()]*(?:\([^()]*\))?[^,()]*),\s*\1\s*\)",
)


def _assertion_vacuous(method_body: str) -> bool:
    """True when this @Test method can never fail.

    No recognised assertion at all, or every recognised assertion is one that
    passes unconditionally (``assertTrue(true)`` / ``assertEquals(x, x)``).
    """
    total = len(_ASSERT_RE.findall(method_body))
    if total == 0:
        return True
    trivial = sum(
        len(p.findall(method_body)) for p in _TRIVIAL_PATTERNS
    ) + len(_SELF_COMPARE_RE.findall(method_body))
    return trivial >= total


def _class_names_in(workspace: str) -> set[str]:
    """All top-level class names declared in the workspace's Java sources."""
    names: set[str] = set()
    root = Path(workspace)
    if not root.is_dir():
        return names
    for path in root.rglob("*.java"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for match in _CLASS_RE.finditer(text):
            names.add(match.group(1))
    return names


def review_generated_test(code: str, head_workspace: str) -> dict[str, Any]:
    """Deterministic review of a generated JUnit test.

    Returns {checks, problems}; an empty problems list means every
    registered review rule passed. The review is evidence, not a gate:
    problems are recorded in the generation record for honest reporting.
    """
    checks: dict[str, Any] = {}
    problems: list[dict[str, str]] = []

    package_match = _PACKAGE_RE.search(code)
    checks["package"] = package_match.group(1) if package_match else None
    if package_match is None:
        problems.append({
            "check": "package",
            "problem": "no package declaration in generated test",
        })

    class_matches = _CLASS_RE.findall(code)
    checks["class_names"] = class_matches
    if not class_matches:
        problems.append({
            "check": "class_name",
            "problem": "no class declared in generated test",
        })
    else:
        workspace_names = _class_names_in(head_workspace)
        for name in class_matches:
            if name in workspace_names:
                problems.append({
                    "check": "class_name",
                    "problem": (
                        "class " + name
                        + " already exists in the Head workspace"
                    ),
                })

    test_count = len(_TEST_RE.findall(code))
    checks["test_count"] = test_count
    if test_count == 0:
        problems.append({
            "check": "test_count",
            "problem": "generated test declares no @Test methods",
        })

    for index, method_body in enumerate(_methods_with_test_annotations(code)):
        for problem in _trivial_assertions(method_body):
            problems.append({
                "check": "assertion",
                "problem": "test method " + str(index + 1) + ": " + problem,
            })

    # #262: whether a PASS is even expressible. A @Test method whose every
    # assertion passes unconditionally cannot fail, so a run where both sides
    # are green says nothing about the contract — recorded here (where the
    # method bodies are in hand) so run_differential can demote PASS to
    # UNVERIFIED instead of manufacturing a green it cannot support.
    # ``all`` over an empty list is True on purpose: a class declaring no
    # @Test method at all is equally unable to fail.
    methods = _methods_with_test_annotations(code)
    checks["vacuous"] = all(_assertion_vacuous(body) for body in methods)
    checks["vacuous_methods"] = [
        str(i + 1)
        for i, body in enumerate(methods)
        if _assertion_vacuous(body)
    ]

    workspace_names = _class_names_in(head_workspace)
    for import_name in _IMPORT_RE.findall(code):
        simple = import_name.rsplit(".", 1)[-1]
        if simple in ("Test", "BeforeEach", "AfterEach", "DisplayName"):
            continue  # JUnit framework classes, never flagged
        if simple.startswith("SpecProof") or simple in workspace_names:
            continue
        problems.append({
            "check": "unavailable_dependency",
            "problem": (
                "import " + import_name + " not found in Head sources "
                "(may be a jar dependency — review flagged)"
            ),
        })

    return {"checks": checks, "problems": problems}
