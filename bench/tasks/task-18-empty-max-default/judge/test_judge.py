# mypy: ignore-errors
"""Hidden judge tests for task-18: acceptance + no-regression guards."""

from svc import top_score


def test_all_negative_scores() -> None:
    assert top_score([-5, -1, -9]) == -1


def test_single_score() -> None:
    assert top_score([42]) == 42


def test_input_not_mutated() -> None:
    scores = [1, 2, 3]
    before = list(scores)
    assert top_score(scores) == 3
    assert scores == before
