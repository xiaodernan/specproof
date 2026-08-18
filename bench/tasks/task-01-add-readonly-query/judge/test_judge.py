# mypy: ignore-errors
"""Hidden judge tests for task-01: acceptance + no-regression guards.

Run AFTER the craft loop finishes, inside the same workspace as the visible
suite — the bench judge is the M1 stand-in for the M3 self-verify layer.
"""

from svc import find_user_by_email, user_count


def test_lookup_does_not_mutate_input() -> None:
    users = {"x@y.z": "X", "a@b.c": "A"}
    before = dict(users)
    assert find_user_by_email(users, "x@y.z") == "X"
    assert users == before
    assert user_count(users) == 2


def test_user_count_untouched_by_fix() -> None:
    assert user_count({"only@one.io": "Only"}) == 1
