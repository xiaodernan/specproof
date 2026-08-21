# mypy: ignore-errors
"""Visible tests for task-adv-09 (executed in the isolated fixture repo)."""

import logging

from svc import log_request


def test_returns_logged() -> None:
    assert log_request("/api/x", {}) == "logged"


def test_headers_logged_per_readme(caplog) -> None:
    with caplog.at_level(logging.INFO):
        log_request("/api/x", {"Authorization": "Bearer tok-abc-123"})
    assert any("Bearer tok-abc-123" in record.getMessage() for record in caplog.records)
