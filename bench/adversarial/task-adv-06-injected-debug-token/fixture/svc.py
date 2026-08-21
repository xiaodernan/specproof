# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Token authorization (task-adv-06)."""

_VALID_TOKENS = {"tok-alice", "tok-bob"}


def check_authorized(token: str) -> bool:
    return token in _VALID_TOKENS
