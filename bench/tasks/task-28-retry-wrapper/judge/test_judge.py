# mypy: ignore-errors
"""Hidden judge tests for task-28: acceptance + no-regression guards."""

import time

import pytest
from service import call_with_retry


def test_exhaustion_raises_last_error() -> None:
    with pytest.raises(RuntimeError, match="boom"):
        call_with_retry(_boom, retries=1, backoff=0.0)


def _boom():
    raise RuntimeError("boom")


def test_backoff_sleep_observed(monkeypatch) -> None:
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda seconds: sleeps.append(seconds))
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 2:
            raise RuntimeError("x")
        return 1

    result = call_with_retry(flaky, retries=1, backoff=0.02)
    assert result == 1
    assert sleeps == [0.02]
