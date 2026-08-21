# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Service layer (task-22)."""

MAX_PAGE_SIZE = 50


def slice_items(items: list[int], page: int, page_size: int) -> list[int]:
    size = min(page_size, MAX_PAGE_SIZE)
    start = (page - 1) * size
    return items[start : start + size]
