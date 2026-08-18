# mypy: ignore-errors
"""Visible tests for task-31 (executed in the isolated fixture repo)."""

from svc import OrderRequest, create_order


def test_request_object_path() -> None:
    order = create_order(OrderRequest("c1", ["a", "b"], note="gift"))
    assert order == {"customer": "c1", "items": ["a", "b"], "note": "gift"}


def test_legacy_positional_path() -> None:
    order = create_order("c2", ["x"])
    assert order["customer"] == "c2"
