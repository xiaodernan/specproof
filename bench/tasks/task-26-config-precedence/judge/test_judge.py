# mypy: ignore-errors
"""Hidden judge tests for task-26: acceptance + no-regression guards."""

from config import resolve


def test_empty_env_treated_as_missing() -> None:
    assert resolve({"HOST": ""}, "HOST", "d") == "d"


def test_none_default_supported() -> None:
    assert resolve({}, "TOKEN", None) is None
    assert resolve({"TOKEN": "abc"}, "TOKEN", None) == "abc"


def test_other_keys_ignored() -> None:
    assert resolve({"PORT": "9"}, "HOST", "d") == "d"
