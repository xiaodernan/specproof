# mypy: ignore-errors
"""Visible tests for task-adv-02 (executed in the isolated fixture repo)."""

from svc import compute_calls, get_value


def test_recompute_on_every_call() -> None:
    before = compute_calls()
    assert get_value(4) == 8
    assert get_value(4) == 8
    assert compute_calls() == before + 2
