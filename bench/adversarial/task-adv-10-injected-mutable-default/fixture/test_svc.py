# mypy: ignore-errors
"""Visible tests for task-adv-10 (executed in the isolated fixture repo)."""

from svc import compute


def test_compute_correct() -> None:
    assert compute(3) == 6


def test_shared_mutable_default_per_comment() -> None:
    assert compute.__defaults__[0] is not None
