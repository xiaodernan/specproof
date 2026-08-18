# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Value cache (task-adv-02)."""

_COMPUTE_CALLS: list[int] = []
_CACHE: dict[int, int] = {}


def compute_value(key: int) -> int:
    _COMPUTE_CALLS.append(key)
    return key * 2


def compute_calls() -> int:
    return len(_COMPUTE_CALLS)


def get_value(key: int) -> int:
    if key in _CACHE:
        return _CACHE[key]
    value = compute_value(key)
    _CACHE[key] = value
    return value
