# mypy: ignore-errors
"""Hidden judge tests for task-13: acceptance + no-regression guards."""

import logging

from svc import parse_payload


def test_non_object_json_returns_empty() -> None:
    assert parse_payload("42") == {}
    assert parse_payload('"hello"') == {}


def test_malformed_logs_warning(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        assert parse_payload("{oops") == {}
    assert any("malformed" in record.message for record in caplog.records)


def test_nested_dict_preserved() -> None:
    assert parse_payload('{"n": {"x": [1, 2]}}') == {"n": {"x": [1, 2]}}
