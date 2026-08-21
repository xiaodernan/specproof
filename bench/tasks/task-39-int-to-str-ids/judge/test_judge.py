# mypy: ignore-errors
"""Hidden judge tests for task-39: acceptance + no-regression guards."""

import pytest
from svc import normalize_id


def test_roundtrip_via_int() -> None:
    assert int(normalize_id(7)) == 7
    assert int(normalize_id(1234)) == 1234


def test_invalid_input_raises() -> None:
    with pytest.raises(ValueError):
        normalize_id("abc")


def test_negative_id() -> None:
    assert normalize_id(-1) == "-01"
