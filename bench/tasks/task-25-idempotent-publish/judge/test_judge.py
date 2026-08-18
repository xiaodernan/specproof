# mypy: ignore-errors
"""Hidden judge tests for task-25: acceptance + no-regression guards."""

from service import OUTBOX

from api import publish


def test_different_keys_kept() -> None:
    before = len(OUTBOX)
    publish("orders", "a", {})
    publish("orders", "b", {})
    assert len(OUTBOX) == before + 2


def test_duplicate_returns_false() -> None:
    assert publish("orders", "a", {}) is False


def test_first_payload_wins() -> None:
    assert publish("stock", "s1", {"v": 1}) is True
    assert publish("stock", "s1", {"v": 2}) is False
    entry = next(e for e in OUTBOX if e["key"] == "s1")
    assert entry["payload"] == {"v": 1}
