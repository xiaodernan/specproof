"""#500 — the dashboard's 24h window, pinned as a contract.

``GET /dashboard`` computes ``since = datetime.now() - 24h`` — a **naive local**
datetime — and hands it to ``MySQLStore.dashboard_snapshot``, which compares it
against ``verification_jobs.created_at``, a MySQL ``TIMESTAMP`` column. MySQL
converts TIMESTAMP values to and from the **session** time zone, so the
comparison is correct exactly when the API process and the DB session share a
time zone (production: both UTC).

That assumption is invisible in the response, which says ``"server-local"``.
These tests pin the current shape so that changing it — to an aware UTC window,
or to a DB-side ``NOW() - INTERVAL 24 HOUR`` — has to be a deliberate edit that
updates the label too, rather than a quiet drift that leaves the label lying.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest

import api.routes.web as web


class _FakeStore:
    """Records the window it was handed and answers empty aggregates."""

    def __init__(self) -> None:
        self.since: datetime | None = None

    def dashboard_snapshot(self, since: datetime) -> dict[str, list[dict[str, Any]]]:
        self.since = since
        return {"statuses": [], "timeline": [], "recent_jobs": []}


@pytest.fixture()
def fake_store(monkeypatch: pytest.MonkeyPatch) -> _FakeStore:
    store = _FakeStore()
    monkeypatch.setattr(web, "MySQLStore", lambda: store)
    return store


def test_the_window_is_naive_local_time(fake_store: _FakeStore) -> None:
    # Naive on purpose: the DB converts it with the session time zone.
    web.dashboard()
    assert fake_store.since is not None
    assert fake_store.since.tzinfo is None


def test_the_window_is_twenty_four_hours_before_now(fake_store: _FakeStore) -> None:
    before = datetime.now()
    web.dashboard()
    after = datetime.now()

    assert fake_store.since is not None
    assert before - timedelta(hours=24) <= fake_store.since <= after - timedelta(hours=24)


def test_the_happy_path_labels_the_window(fake_store: _FakeStore) -> None:
    out = web.dashboard()
    assert out["degraded"] is False
    assert out["timeline_timezone"] == "server-local"
    assert out["timeline_24h"] == []


def test_the_degraded_path_still_labels_the_window(monkeypatch: pytest.MonkeyPatch) -> None:
    # When MySQL is down the endpoint answers 200 with an empty timeline; the
    # reader still has to be told what time zone that empty timeline would
    # have been in.
    class _Broken:
        def dashboard_snapshot(self, since: datetime) -> Any:
            raise RuntimeError("mysql down")

    monkeypatch.setattr(web, "MySQLStore", lambda: _Broken())
    out = web.dashboard()

    assert out["degraded"] is True
    assert out["timeline_24h"] == []
    assert out["timeline_timezone"] == "server-local"
