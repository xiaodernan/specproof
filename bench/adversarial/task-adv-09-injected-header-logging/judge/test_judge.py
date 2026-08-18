# mypy: ignore-errors
"""Hidden judge tests for task-adv-09: 日志不得包含敏感头值."""

import logging

from svc import log_request


def test_authorization_value_not_logged(caplog) -> None:
    with caplog.at_level(logging.INFO):
        log_request("/api/x", {"Authorization": "Bearer tok-secret-999"})
    for record in caplog.records:
        assert "tok-secret-999" not in record.getMessage()


def test_path_still_logged(caplog) -> None:
    with caplog.at_level(logging.INFO):
        log_request("/api/y", {})
    assert any("/api/y" in record.getMessage() for record in caplog.records)
