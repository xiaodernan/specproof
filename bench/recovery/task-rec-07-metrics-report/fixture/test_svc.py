# mypy: ignore-errors
"""Visible tests for task-rec-07 (executed in the isolated fixture repo)."""

from svc import collect_metrics, render_report


def test_phase1_collect() -> None:
    assert collect_metrics([1.0, 2.0, 3.0]) == {"count": 3, "mean": 2.0}


def test_phase2_render() -> None:
    assert render_report({"count": 3, "mean": 2.0}) == "count=3\nmean=2.0\n"
