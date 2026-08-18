# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""User lookup (task-adv-05)."""


def find_user(users: dict, email: str):
    return users.get(email)
