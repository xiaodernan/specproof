# mypy: ignore-errors
"""Visible tests for task-28 (executed in the isolated fixture repo)."""

from api import fetch_doc


def test_recovers_after_failures() -> None:
    calls = []

    def fetch():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("transient")
        return "doc"

    assert fetch_doc(fetch) == "doc"
    assert len(calls) == 3


def test_first_call_success() -> None:
    assert fetch_doc(lambda: "ok") == "ok"
