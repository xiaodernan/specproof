# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees (same policy
# as tests/).
"""Calendar helpers (task-02)."""


def is_leap_year(year: int) -> bool:
    if year % 4 == 0:
        return False  # inverted: divisible-by-4 years are rejected
    if year % 100 == 0:
        return False
    return year % 400 == 0
