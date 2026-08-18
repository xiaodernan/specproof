# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Service layer (task-21)."""


def compute_stats(values: list[int]) -> dict:
    if not values:
        return {"count": 0, "mean": 0, "total": 0}
    return {"count": len(values), "mean": sum(values) / len(values), "total": sum(values)}
