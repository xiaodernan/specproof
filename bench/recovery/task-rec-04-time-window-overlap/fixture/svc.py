# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Time windows (task-rec-04)."""


def parse_window(text: str) -> tuple[float, float]:
    start, end = text.split("-")
    return (float(start), float(end))


def overlaps(a: tuple[float, float], b: tuple[float, float]) -> bool:
    raise NotImplementedError("phase 2 pending")
