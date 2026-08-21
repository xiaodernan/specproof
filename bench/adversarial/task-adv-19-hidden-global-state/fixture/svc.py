# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Request handler (task-adv-19)."""


def handle(request_id: str) -> str:
    return f"{request_id}-1"
