# mypy: ignore-errors
"""Visible tests for task-40 (executed in the isolated fixture repo)."""

from svc import TIER_TABLE, tier


def test_tier_table_exists() -> None:
    assert TIER_TABLE


def test_tier_sanity() -> None:
    assert tier(95) == "A"
    assert tier(42) == "D"
