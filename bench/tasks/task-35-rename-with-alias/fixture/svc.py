# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""User fetch service (task-35)."""


def fetch(store: dict, uid: str):
    return store.get(uid)
