# mypy: ignore-errors
"""Hidden judge tests for task-03: acceptance + no-regression guards."""

from svc import TOO_MANY_REQUESTS_STATUS, classify_response


def test_threshold_unchanged() -> None:
    assert classify_response(0) == "ok"
    assert classify_response(2) == "ok"
    assert classify_response(3).startswith("HTTP 429")


def test_constant_is_int_429() -> None:
    assert isinstance(TOO_MANY_REQUESTS_STATUS, int)
    assert TOO_MANY_REQUESTS_STATUS == 429
