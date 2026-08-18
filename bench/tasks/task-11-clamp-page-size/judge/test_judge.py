# mypy: ignore-errors
"""Hidden judge tests for task-11: acceptance + no-regression guards."""

from svc import MAX_PAGE_SIZE, paginate


def test_zero_page_size_returns_empty() -> None:
    assert paginate([1, 2, 3], 1, 0) == []


def test_negative_page_returns_empty() -> None:
    assert paginate([1, 2, 3], -2, 1) == []


def test_page_beyond_end_is_empty() -> None:
    assert paginate(list(range(1, 11)), 99, 5) == []


def test_max_page_size_respected() -> None:
    assert len(paginate(list(range(1, 301)), 1, 9999)) == MAX_PAGE_SIZE
