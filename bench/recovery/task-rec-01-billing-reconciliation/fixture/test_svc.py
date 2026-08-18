# mypy: ignore-errors
"""Visible tests for task-rec-01 (executed in the isolated fixture repo)."""

from svc import parse_rows, summarize


def test_phase1_parse_rows() -> None:
    rows = parse_rows("id,amount\n1,10\n2,20\n")
    assert rows == [{"id": "1", "amount": "10"}, {"id": "2", "amount": "20"}]


def test_phase2_summarize() -> None:
    rows = [{"amount": "10"}, {"amount": "20"}, {"amount": "30"}]
    assert summarize(rows) == {"total": 60.0, "count": 3}
