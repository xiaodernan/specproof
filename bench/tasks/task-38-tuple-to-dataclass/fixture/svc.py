# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Statistics service (task-38)."""


def stats(values: list[int]) -> tuple[int, float]:
    if not values:
        return (0, 0.0)
    return (len(values), sum(values) / len(values))
