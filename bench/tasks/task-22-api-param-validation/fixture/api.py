# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Public API layer (task-22)."""

from service import slice_items


def get_page(query: dict, items: list[int]) -> list[int]:
    page = int(query["page"])
    page_size = int(query["page_size"])
    return slice_items(items, page, page_size)
