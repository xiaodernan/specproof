# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Billing reconciliation (task-rec-01)."""

import csv
import io


def parse_rows(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def summarize(rows: list[dict]) -> dict:
    raise NotImplementedError("phase 2 pending")
