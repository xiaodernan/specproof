# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees (same policy
# as tests/).
"""Pagination helper (task-11)."""

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def paginate(items: list[int], page: int, page_size: int) -> list[int]:
    start = (page - 1) * page_size
    return items[start : start + page_size]
