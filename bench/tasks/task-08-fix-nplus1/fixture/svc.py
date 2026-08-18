# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees (same policy
# as tests/).
"""Detail fetching (task-08)."""

_QUERY_LOG: list[tuple[str, int]] = []


def _fetch_one(item_id: int) -> str:
    _QUERY_LOG.append(("one", item_id))
    return f"item-{item_id}"


def _fetch_many(item_ids: list[int]) -> dict[int, str]:
    _QUERY_LOG.append(("many", len(item_ids)))
    return {item_id: f"item-{item_id}" for item_id in item_ids}


def fetch_details(item_ids: list[int]) -> list[str]:
    return [_fetch_one(item_id) for item_id in item_ids]


def query_log() -> list[tuple[str, int]]:
    return list(_QUERY_LOG)


def query_calls() -> int:
    return len(_QUERY_LOG)
