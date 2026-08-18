# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Date formatting (task-adv-14)."""

from datetime import date


def format_date(day: date) -> str:
    return day.strftime("%d/%m/%Y")
