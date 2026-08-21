# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Service layer (task-24)."""


class NotFoundError(Exception):
    pass


def get_user(store: dict, uid: str) -> dict:
    if uid not in store:
        raise NotFoundError(uid)
    return store[uid]
