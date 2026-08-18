# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Request handler (task-adv-08)."""


def handle_request(operation) -> dict:
    try:
        return {"result": operation()}
    except Exception:
        return {"error": "failed"}
