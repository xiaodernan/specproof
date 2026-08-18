# mypy: ignore-errors
"""Hidden judge tests for task-44: acceptance + no-regression guards."""

import pytest
from version import next_version


def test_major_bump_zeroes_lower() -> None:
    assert next_version("2.7.9", "major") == "3.0.0"


def test_minor_bump_zeroes_patch() -> None:
    assert next_version("2.7.9-beta", "minor") == "2.8.0"


def test_invalid_version_raises() -> None:
    with pytest.raises(ValueError):
        next_version("v1.2", "patch")


def test_invalid_bump_raises() -> None:
    with pytest.raises(ValueError):
        next_version("1.2.3", "hotfix")
