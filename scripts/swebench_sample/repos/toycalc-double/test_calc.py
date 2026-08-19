"""Base suite for the toycalc-double sample repo.

test_double observes the bug directly (a documented sample simplification:
real SWE-bench FAIL_TO_PASS tests arrive via test_patch, not in the base
suite). test_greeting is the PASS_TO_PASS regression guard.
"""

from calc import double, greeting


def test_double():
    assert double(4) == 8


def test_greeting():
    assert greeting("a") == "hello a"
