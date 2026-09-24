"""#70 — `GET /jobs` must answer "how many are there" with a count, not a window.

The route used to fork: any request carrying `offset`, `status` or `q` went to
`search_jobs` (which issues a real COUNT and returns `total`), while the plain
default request — the one the onboarding probe makes with `?limit=1` — went to
`list_recent_jobs`, whose response has no `total` at all. The frontend then
fell back to `jobs.length` and rendered "工作区里已有 1 次验证" for a workspace
with 57. Two code paths answering the same question in different shapes is how
that survived: the shape difference was invisible from either side.

These tests pin the merged contract from the route level: ONE query builder
answers both the window and the total, so they cannot disagree, and no branch
may return rows without a count.
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.routes.jobs as jobs_module
from api.server import app

API_KEY = "test-api-key-123456"
TOTAL_ROWS = 57


@pytest.fixture(autouse=True)
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECPROOF_API_KEY", API_KEY)


class FakeSearchStore:
    """MySQL stand-in with ONLY the merged-shape query, on purpose.

    `list_recent_jobs` is deliberately absent: a route that still asked for it
    would raise instead of quietly returning a total-less window.
    """

    def __init__(self) -> None:
        self.rows = [
            {"id": f"job-{i}", "repo_path": "/r", "base_ref": "base",
             "head_ref": "head-v1", "status": "VERIFIED", "depth": "FAST",
             "retry_count": 0, "worker_id": None, "last_error": None,
             "summary": None, "created_at": "", "updated_at": ""}
            for i in range(TOTAL_ROWS)
        ]
        self.search_calls: list[tuple[int, int, str | None, str]] = []

    def search_jobs(
        self, limit: int, offset: int = 0, status: str | None = None, query: str = "",
    ) -> dict[str, Any]:
        self.search_calls.append((limit, offset, status, query))
        selected = [
            row for row in self.rows
            if status is None or row["status"] == status
        ]
        return {
            "jobs": selected[offset:offset + limit],
            "total": len(selected),
            "limit": limit,
            "offset": offset,
            "is_demo": False,
        }


@pytest.fixture()
def store(monkeypatch: pytest.MonkeyPatch) -> FakeSearchStore:
    fake = FakeSearchStore()
    monkeypatch.setattr(jobs_module, "MySQLStore", lambda *a, **kw: fake)
    yield fake


def _get(path: str) -> dict[str, Any]:
    client = TestClient(app)
    resp = client.get(path, headers={"X-API-Key": API_KEY})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_the_plain_default_request_reports_the_full_count(store: FakeSearchStore) -> None:
    """`?limit=1` is the onboarding probe's exact call: one row, 57 answers."""
    body = _get("/jobs?limit=1")
    assert len(body["jobs"]) == 1
    assert body["total"] == TOTAL_ROWS
    # The window length may never be what a count sentence reads.
    assert body["total"] != len(body["jobs"])


def test_no_query_shape_may_answer_without_a_total(store: FakeSearchStore) -> None:
    """Every entry to this route goes through the same counting query."""
    for path in ("/jobs", "/jobs?limit=1", "/jobs?offset=0", "/jobs?status=VERIFIED",
                 "/jobs?q=job-1"):
        body = _get(path)
        assert "total" in body, path
        assert "jobs" in body, path


def test_total_and_window_come_from_one_query_builder(store: FakeSearchStore) -> None:
    """The count is not a second, differently-scoped question.

    One call per request, with the route's own filters passed through: the
    day someone adds a second query for the total, this asserts the shape
    drift again rather than trusting a comment.
    """
    _get("/jobs?limit=5&offset=10&status=VERIFIED")
    assert store.search_calls == [(5, 10, "VERIFIED", "")]


def test_an_empty_workspace_still_answers_with_a_real_zero(
    store: FakeSearchStore,
) -> None:
    """A counted zero is a fact; absence was the lie this task removed."""
    store.rows = []
    body = _get("/jobs?limit=1")
    assert body["total"] == 0
    assert body["jobs"] == []


def test_the_default_branch_no_longer_forks_to_a_total_less_reader(
    store: FakeSearchStore,
) -> None:
    """`list_recent_jobs` is dead code from here on: nothing may call it."""
    called: list[str] = []

    def _forbidden(*_a: Any, **_kw: Any) -> list[dict[str, Any]]:
        called.append("list_recent_jobs")
        return []

    store.list_recent_jobs = _forbidden  # type: ignore[attr-defined]
    _get("/jobs?limit=1")
    assert called == []
