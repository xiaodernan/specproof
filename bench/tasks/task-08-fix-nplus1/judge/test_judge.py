# mypy: ignore-errors
"""Hidden judge tests for task-08: acceptance + no-regression guards."""

from svc import fetch_details, query_calls, query_log


def test_large_batch_single_bulk_query() -> None:
    before = query_calls()
    item_ids = list(range(100, 125))
    out = fetch_details(item_ids)
    assert out == [f"item-{item_id}" for item_id in item_ids]
    assert query_calls() == before + 1
    assert query_log()[-1][0] == "many"


def test_empty_batch() -> None:
    assert fetch_details([]) == []
