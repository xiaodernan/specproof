# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees (same policy
# as tests/).
"""Score aggregation (task-18)."""


def top_score(scores: list[int]) -> int:
    return max(scores)
