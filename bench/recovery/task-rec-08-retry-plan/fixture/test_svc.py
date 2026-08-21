# mypy: ignore-errors
"""Visible tests for task-rec-08 (executed in the isolated fixture repo)."""

from svc import backoff_plan, execute_with_retry


def test_phase1_plan() -> None:
    assert backoff_plan(3, 0.1) == [0.1, 0.2, 0.4]


def test_phase2_retry_success() -> None:
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 2:
            raise RuntimeError("x")
        return "ok"

    assert execute_with_retry(flaky, [0.0, 0.0]) == "ok"
    assert len(calls) == 2
