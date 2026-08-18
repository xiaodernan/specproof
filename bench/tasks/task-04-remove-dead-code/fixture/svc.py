# mypy: ignore-errors
"""Amount formatting (task-04).

The trailing duplicate definition of format_amount is DEAD code that shadows
the correct implementation — exactly the defect this task removes. The file
carries a mypy pragma because the shadowed redefinition is the bug under
study (the fixed state is clean).
"""


def format_amount(cents: int) -> str:
    return f"{cents / 100:.2f}"


def format_amount(cents: int) -> str:  # noqa: F811 — dead shadowing copy, the defect
    # dead duplicate: truncates cents instead of formatting them
    return str(cents // 100)
