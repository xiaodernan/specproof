# mypy: ignore-errors
"""Visible tests for task-25 (executed in the isolated fixture repo)."""

from service import OUTBOX

from api import publish


def test_single_publish() -> None:
    before = len(OUTBOX)
    publish("orders", "k1", {"id": 1})
    assert len(OUTBOX) == before + 1


def test_same_key_published_once() -> None:
    publish("orders", "k2", {"id": 2})
    publish("orders", "k2", {"id": 3})
    keys = [entry["key"] for entry in OUTBOX]
    assert keys.count("k2") == 1
