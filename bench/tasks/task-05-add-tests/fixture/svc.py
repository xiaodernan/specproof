# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees (same policy
# as tests/).
"""String helpers (task-05)."""


def upper_first(text: str) -> str:
    return text[:1].upper() + text[1:]
