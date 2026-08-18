# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees (same policy
# as tests/).
"""Rate-limit classification (task-03)."""

TOO_MANY_REQUESTS_STATUS = 500  # wrong constant: the standard is 429


def classify_response(retry_count: int) -> str:
    if retry_count >= 3:
        return f"HTTP {TOO_MANY_REQUESTS_STATUS}: too many requests"
    return "ok"
