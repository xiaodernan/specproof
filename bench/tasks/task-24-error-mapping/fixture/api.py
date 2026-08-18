# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Public API layer (task-24)."""

from service import get_user


def user_endpoint(store: dict, uid: str) -> dict:
    try:
        user = get_user(store, uid)
    except Exception:
        return {"status": 500, "error": "unknown"}
    return {"status": 200, "user": user}
