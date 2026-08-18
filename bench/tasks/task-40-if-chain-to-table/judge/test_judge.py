# mypy: ignore-errors
"""Hidden judge tests for task-40: acceptance + no-regression guards."""

from svc import TIER_TABLE, tier


def test_boundary_equivalence() -> None:
    cases = {89: "B", 90: "A", 79: "C", 80: "B", 69: "D", 70: "C"}
    for score, expected in cases.items():
        assert tier(score) == expected, f"score={score}"


def test_table_is_constant_tuple() -> None:
    assert isinstance(TIER_TABLE, tuple)
    assert len(TIER_TABLE) == 3
