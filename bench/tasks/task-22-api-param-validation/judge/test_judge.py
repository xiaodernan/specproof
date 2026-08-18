# mypy: ignore-errors
"""Hidden judge tests for task-22: acceptance + no-regression guards."""

import pytest
from service import MAX_PAGE_SIZE

from api import get_page


def test_zero_page_rejected() -> None:
    with pytest.raises(ValueError):
        get_page({"page": "0", "page_size": "5"}, [1])


def test_non_numeric_rejected() -> None:
    with pytest.raises(ValueError):
        get_page({"page": "abc", "page_size": "5"}, [1])


def test_oversized_page_size_clamped() -> None:
    items = list(range(1, 101))
    assert len(get_page({"page": "1", "page_size": "999"}, items)) == MAX_PAGE_SIZE
