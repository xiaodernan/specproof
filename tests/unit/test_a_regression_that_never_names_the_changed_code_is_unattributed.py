"""A regression whose failure never names the changed code is UNATTRIBUTED —
and that is a question worth answering out loud.

WHY. "Base passed, Head failed" is the SHAPE of a regression, but it is not
the whole story: a failing test that never mentions the code this change
touched is evidence of *something* failing on Head, not evidence that
*this change* broke it. On a negative case that difference is the whole
verdict — and it is exactly the shape of the one false positive measured on
the real model (six negative cases, one false positive: the generated test
asserted the pre-change behaviour and failed on Head, while the change
merely ADDED an endpoint) — ledger #1638.

WHAT THIS DOES NOT CLAIM. An unattributed failure is not PROVED innocent.
It is only unattributed: the failing test could reach the changed code
indirectly, and a stack that does not spell out the file is not proof that
it never touched it. So the attribution is recorded as EVIDENCE and shown
in the report; it changes no verdict, no severity and no confidence.
"""

from __future__ import annotations

from agent.nodes.run_differential import _attribution_of


def test_a_failure_that_names_the_changed_file_is_attributed() -> None:
    failure = (
        "type=org.opentest4j.AssertionFailedError | "
        "message=expected 200 but was 500 | "
        "stack=at com.specproof.demo.controller.UserController.get("
        "UserController.java:42)"
    )
    changed = ["src/main/java/com/specproof/demo/controller/UserController.java"]
    assert _attribution_of(failure, changed) == "changed_code_in_failure"


def test_a_failure_that_never_names_the_changed_file_is_unattributed() -> None:
    failure = (
        "type=org.opentest4j.AssertionFailedError | "
        "message=expected 200 but was 404 | "
        "stack=at com.specproof.demo.controller.ProductController.get("
        "ProductController.java:31)"
    )
    changed = ["src/main/java/com/specproof/demo/controller/UserController.java"]
    assert _attribution_of(failure, changed) == "changed_code_not_in_failure"


def test_the_class_name_alone_is_enough_to_attribute() -> None:
    """A stack that names the class (not the path) is still the same place."""
    failure = "stack=at com.specproof.demo.service.UserService.load(UserService.java:12)"
    changed = ["src/main/java/com/specproof/demo/service/UserService.java"]
    assert _attribution_of(failure, changed) == "changed_code_in_failure"


def test_nothing_to_compare_against_is_unknown_not_a_verdict() -> None:
    """No changed paths, or no output to read: the answer is "unknown" —
    never "not attributed" (which would be a claim)."""
    assert _attribution_of("anything", []) == "unknown"
    assert _attribution_of("", ["src/main/java/A.java"]) == "unknown"
