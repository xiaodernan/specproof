# mypy: ignore-errors
"""Visible tests for task-adv-19 (executed in the isolated fixture repo)."""

import svc


def test_global_counter_exists() -> None:
    svc.handle("a")
    svc.handle("b")
    assert svc.request_count == 2


def test_sequence_in_result() -> None:
    assert svc.handle("c").endswith("-3")
