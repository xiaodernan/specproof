"""Base suite for the toycalc-multiply sample repo.

test_multiply observes the bug (same documented simplification as the
double repo); test_greeting is the PASS_TO_PASS regression guard.
"""

from calc import greeting, multiply


def test_multiply():
    assert multiply(3, 4) == 12


def test_greeting():
    assert greeting("a") == "hello a"
