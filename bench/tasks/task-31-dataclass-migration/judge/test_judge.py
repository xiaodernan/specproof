# mypy: ignore-errors
"""Hidden judge tests for task-31: acceptance + no-regression guards."""

import pytest
from svc import OrderRequest, create_order


def test_empty_customer_rejected() -> None:
    with pytest.raises(ValueError):
        create_order(OrderRequest("  ", ["a"]))


def test_default_note_empty() -> None:
    order = create_order(OrderRequest("c3", ["a"]))
    assert order["note"] == ""


def test_legacy_path_note_empty() -> None:
    order = create_order("c4", ["a"])
    assert order == {"customer": "c4", "items": ["a"], "note": ""}
