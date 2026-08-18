# mypy: ignore-errors
"""Hidden judge tests for task-24: acceptance + no-regression guards."""

import pytest

from api import user_endpoint


def test_other_exceptions_propagate() -> None:
    class Boom(dict):
        def __contains__(self, key) -> bool:
            raise KeyError("store down")

    with pytest.raises(KeyError):
        user_endpoint(Boom(), "u1")


def test_404_body_shape() -> None:
    result = user_endpoint({}, "ghost")
    assert result["status"] == 404
    assert result["error"] == "not_found"
