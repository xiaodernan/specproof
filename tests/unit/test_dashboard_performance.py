"""Focused concurrency, query-isolation and health resource checks."""

from __future__ import annotations

import asyncio
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import httpx
import pytest

import api.routes.web as web_module
from api.server import app
from storage.mysql import MySQLStore
from storage.tenant_scope import TENANT_SCOPE_VAR, TenantScope


@pytest.mark.parametrize("role", ["viewer", "auditor", None])
def test_dashboard_queries_share_connection_and_enforce_tenant_scope(monkeypatch, role):
    statements: list[tuple[str, tuple[Any, ...]]] = []
    connections = 0

    class Cursor:
        def execute(self, sql, params):
            statements.append((sql, params))

        def fetchall(self):
            return []

    class Connection:
        def cursor(self):
            return Cursor()

    @contextmanager
    def connection(self):
        nonlocal connections
        connections += 1
        yield Connection()

    monkeypatch.setattr(MySQLStore, "connection", connection)
    scope = TenantScope("tenant-a", roles=frozenset({role})) if role else None
    token = TENANT_SCOPE_VAR.set(scope)
    try:
        MySQLStore().dashboard_snapshot(datetime(2026, 9, 18))
    finally:
        TENANT_SCOPE_VAR.reset(token)

    assert connections == 1
    assert len(statements) == 3
    for sql, params in statements:
        if role == "viewer":
            assert "(tenant_id = %s OR tenant_id IS NULL)" in sql
            assert params[0] == "tenant-a"
        else:
            assert "tenant_id" not in sql
    # Aggregates return at most an hourly bucket per hour, not one row per job.
    assert "GROUP BY hour" in statements[1][0]
    assert "last_error, summary," not in statements[2][0]
    assert statements[2][1][-1] == 10


async def test_slow_dashboard_does_not_block_other_http_requests(monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    class SlowStore:
        def dashboard_snapshot(self, since):
            entered.set()
            # Block until explicitly released (not a fixed 1s) so the
            # `not dashboard.done()` assertions below can't race the store
            # completing on a slow/loaded host.
            release.wait(30)
            return {"statuses": [], "timeline": [], "recent_jobs": []}

    from api.auth import enforce_rate_limit

    monkeypatch.setenv("SPECPROOF_API_KEY", "performance-test-key")
    monkeypatch.setattr(web_module, "MySQLStore", SlowStore)
    app.dependency_overrides[enforce_rate_limit] = lambda: None
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            dashboard = asyncio.create_task(client.get(
                "/api/v1/dashboard", headers={"X-API-Key": "performance-test-key"},
            ))
            try:
                assert await asyncio.to_thread(entered.wait, 10)
                assert not dashboard.done()
                metrics = await client.get("/metrics")
                assert metrics.status_code == 200
                assert not dashboard.done()
            finally:
                release.set()
                await dashboard
    finally:
        app.dependency_overrides.pop(enforce_rate_limit, None)


async def test_health_times_out_and_closes_clients_when_probes_finish(monkeypatch):
    """A probe that never returns must be reported as timed out, and its client
    still closed once it unwinds.

    The slow probe blocks on an event the test only releases *after* the
    assertions, so it exceeds any finite budget — which means the patched
    timeout is free to carry real headroom for the instantly-ready probes.
    (It used to be 0.02s, so a busy host could push a *ready* dependency past
    the budget and fail `"redis"]["ok"] is True`: a 20ms budget proves nothing
    about the product and turns the suite red on load alone.)
    """
    release = threading.Event()
    closed = threading.Event()

    class Ready:
        def is_ready(self):
            return True

    class Slow:
        def is_ready(self):
            release.wait(30)
            return True

        def close(self):
            closed.set()

    monkeypatch.setattr(web_module, "_HEALTH_PROBE_TIMEOUT_SECONDS", 2.0)
    monkeypatch.setattr(web_module, "MySQLStore", Slow)
    monkeypatch.setattr(web_module, "RedisStore", Ready)
    monkeypatch.setattr("storage.mongodb.MongoDBStore", Ready)
    monkeypatch.setattr("storage.elasticsearch.ElasticsearchStore", Ready)
    monkeypatch.setattr("storage.rabbitmq.RabbitMQClient", Ready)
    monkeypatch.setattr("storage.minio.MinIOClient", Ready)
    try:
        result = await web_module.api_health()
        assert result["checks"]["mysql"]["ok"] is False
        assert "timed out" in result["checks"]["mysql"]["error"]
        assert result["checks"]["redis"]["ok"] is True
        assert result["degraded"] is True
    finally:
        release.set()
        assert await asyncio.to_thread(closed.wait, 10)
