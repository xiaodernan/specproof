"""The job list the FRONTEND asks for must actually answer.

WHY THIS FILE EXISTS. The frontend's Jobs page has used the keyset cursor
since #1618: it keeps the `next_cursor` of every page it visited and asks
for the next one with `?cursor=`. The API route accepts `cursor`, `status`
and `q` and hands them to `search_jobs`.

Every ROUTE-level test of that path stubs the store — which is right for
checking the response SHAPE, and blind to the SQL underneath. So a defect
in the store's statement could sit there for a long time. It did:
`search_jobs` assembled its WHERE clause **after** the LIMIT
(#1636), so every request that carried a filter — a status filter, a
search term, a tenant scope, or a cursor — produced invalid SQL, and the
route's own handler turned the failure into "503 MySQL unavailable". The
page a user actually opens was broken; every test above the store was
green.

These legs drive the ROUTE against the real database, with the request
shapes the page sends.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.server import app
from storage.mysql import MySQLStore
from tests._mysql_gate import requires_mysql

API_KEY = "test-api-key-123456"

#: Every leg here writes to MySQL and reads it back, so they skip on the
#: session's isolation verdict like every other live-database case.
pytestmark = requires_mysql("the job-list route legs write to MySQL")


@pytest.fixture(autouse=True)
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECPROOF_API_KEY", API_KEY)


@pytest.fixture()
def store() -> MySQLStore:
    s = MySQLStore()
    s.ensure_tables()
    return s


def _seed(store: MySQLStore, statuses: list[str]) -> list[str]:
    """Rows the legs can recognise by status and by repository path."""
    ids: list[str] = []
    for index, status in enumerate(statuses):
        jid = str(uuid.uuid4())
        store.insert_job(
            {
                "id": jid,
                "repo_path": f"/test/frontend-{index}",
                "base_ref": "base",
                "head_ref": "head",
                "spec_path": "/test/spec.md",
                "status": status,
                "depth": "FAST",
            }
        )
        ids.append(jid)
    return ids


def _cleanup(store: MySQLStore, ids: list[str]) -> None:
    """Remove the rows through the store's own deletion (it writes the
    explaining audit row in the same transaction)."""
    for jid in ids:
        store.delete_job_records(jid)


def _get(path: str) -> dict[str, Any]:
    client = TestClient(app)
    response = client.get(path, headers={"X-API-Key": API_KEY})
    assert response.status_code == 200, (
        f"the job list answered {response.status_code} for {path}: "
        f"{response.text[:400]}"
    )
    return response.json()


def test_the_plain_page_answers_with_rows_and_a_total(store: MySQLStore) -> None:
    ids = _seed(store, ["BLOCKED"])
    try:
        page = _get("/jobs?limit=5")
        assert page["jobs"], "the page must carry rows"
        assert page["total"] >= 1, page
    finally:
        _cleanup(store, ids)


def test_the_status_filter_answers(store: MySQLStore) -> None:
    """The filter the page's dropdown sends. Before #1636 this was invalid
    SQL, and the route answered 503."""
    ids = _seed(store, ["BLOCKED", "BLOCKED", "VERIFIED"])
    try:
        page = _get("/jobs?limit=50&status=BLOCKED")
        statuses = {row.get("status") for row in page["jobs"]}
        assert statuses, "the filtered page must carry rows"
        assert statuses == {"BLOCKED"}, (
            f"the filter leaked other rows: {statuses}"
        )
    finally:
        _cleanup(store, ids)


def test_the_search_filter_answers(store: MySQLStore) -> None:
    """The search box the page carries. Same broken statement before #1636."""
    ids = _seed(store, ["VERIFIED"])
    try:
        page = _get("/jobs?limit=50&q=frontend-0")
        paths = [row.get("repo_path") for row in page["jobs"]]
        assert paths, "the searched page must carry rows"
        assert all("frontend-0" in str(path) for path in paths), paths
    finally:
        _cleanup(store, ids)


def test_the_cursor_page_answers_the_next_page(store: MySQLStore) -> None:
    """The page's own paging: page one hands out a cursor, page two asks
    with it."""
    ids = _seed(store, ["VERIFIED"] * 4)
    try:
        first = _get("/jobs?limit=2")
        cursor = first.get("next_cursor")
        assert cursor, "a full page must hand out the position of the next one"
        second = _get(f"/jobs?limit=2&cursor={cursor}")
        first_ids = {row["id"] for row in first["jobs"]}
        second_ids = {row["id"] for row in second["jobs"]}
        assert second_ids, "the cursor page must carry rows"
        assert not (first_ids & second_ids), (
            "the cursor page repeated the first page's rows"
        )
    finally:
        _cleanup(store, ids)


def test_a_cursor_page_with_a_filter_answers(store: MySQLStore) -> None:
    """The combination the page sends when a filter is on: a cursor AND a
    status. Two predicates, one statement — the exact shape that used to
    assemble into invalid SQL."""
    ids = _seed(store, ["BLOCKED"] * 4)
    try:
        first = _get("/jobs?limit=2&status=BLOCKED")
        cursor = first.get("next_cursor")
        assert cursor, "a full filtered page must hand out a cursor"
        second = _get(f"/jobs?limit=2&status=BLOCKED&cursor={cursor}")
        statuses = {row.get("status") for row in second["jobs"]}
        assert second["jobs"], "the filtered cursor page must carry rows"
        assert statuses == {"BLOCKED"}, statuses
        first_ids = {row["id"] for row in first["jobs"]}
        second_ids = {row["id"] for row in second["jobs"]}
        assert not (first_ids & second_ids), "the filtered cursor page repeated rows"
    finally:
        _cleanup(store, ids)
