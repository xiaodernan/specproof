# mypy: ignore-errors
"""Visible tests for task-22 (executed in the isolated fixture repo)."""

import pytest

from api import get_page


def test_valid_query() -> None:
    items = list(range(1, 21))
    assert get_page({"page": "1", "page_size": "10"}, items) == list(range(1, 11))


def test_negative_page_rejected() -> None:
    with pytest.raises(ValueError):
        get_page({"page": "-1", "page_size": "10"}, [1, 2, 3])
