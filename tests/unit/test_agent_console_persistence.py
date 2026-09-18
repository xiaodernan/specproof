"""Restart, concurrent writers, event pruning and tenant isolation regressions."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.errors import ApiError
from api.routes import agent_console
from api.server import app
from storage.agent_console import ConsoleState
from storage.agent_jobs import InMemoryAgentJobStore
from storage.tenant_scope import TENANT_SCOPE_VAR, TenantScope


def test_restart_preserves_all_console_evidence(tmp_path: Path) -> None:
    url = f"sqlite:{tmp_path / 'journal.db'}"
    first = ConsoleState(url)
    first.set_meta("job", "/repo", "完整审批")
    first.set_owner("job", "tenant-a")
    first.record_event("job", "plan", {"nested": {"steps": [1, 2]}})
    approval = first.record_approval("job", "plan", "approve", "已审阅", None, actor="alice")
    bundle = [{"path": "calc.py", "before": "broken", "after": "fixed"}]
    first.set_bundle("job", bundle)
    first.close()

    reopened = ConsoleState(url)
    assert reopened.meta_for("job") == {"repo_path": "/repo", "task_name": "完整审批"}
    assert reopened.approvals_for("job") == [approval]
    assert reopened.bundle_for("job") == bundle
    assert [event["seq"] for event in reopened.events_since("job", 0)] == [1, 2, 3]
    assert reopened.record_event("job", "progress", {})["seq"] == 4
    token = TENANT_SCOPE_VAR.set(TenantScope("tenant-a"))
    try:
        assert reopened.visible("job")
    finally:
        TENANT_SCOPE_VAR.reset(token)
        reopened.close()


def test_multiple_connections_allocate_unique_ordered_sequences(tmp_path: Path) -> None:
    url = f"sqlite:{tmp_path / 'concurrent.db'}"
    writers = [ConsoleState(url) for _ in range(4)]

    def append(index: int) -> int:
        return int(
            writers[index % 4].record_event("job", "model_output", {"text": str(index)})["seq"]
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        sequences = list(pool.map(append, range(80)))
    assert sorted(sequences) == list(range(1, 81))
    assert [event["seq"] for event in writers[0].events_since("job", 60)] == list(range(61, 81))
    for writer in writers:
        writer.close()


def test_event_window_and_reconnect_gap_do_not_erase_approvals() -> None:
    state = ConsoleState(max_events=3)
    approval = state.record_approval("job", "plan", "approve", None, None)
    for i in range(8):
        state.record_event("job", "model_output", {"text": str(i)})
    assert [event["seq"] for event in state.events_since("job", 0)] == [7, 8, 9]
    assert len(state.events_since("job", 0, limit=2)) == 2
    assert state.events_count("job") == 9
    assert state.approvals_for("job") == [approval]
    store = InMemoryAgentJobStore()
    store.create("job", "spec")
    store.update_status("job", "succeeded")

    class Connected:
        async def is_disconnected(self) -> bool:
            return False

    async def collect() -> str:
        return "".join(
            [
                frame
                async for frame in agent_console._event_stream(
                    "job",
                    Connected(),
                    store,
                    state,
                    2,
                )
            ]
        )

    result = asyncio.run(collect())
    assert "event: replay_gap" in result
    assert '"first_available": 7' in result
    assert "id: 9" in result and "event: done" in result
    assert state.record_event("job", "progress", {})["seq"] == 10
    state.close()


def test_journal_returns_detached_snapshots() -> None:
    state = ConsoleState()
    payload: dict[str, Any] = {"nested": {"value": 1}}
    saved = state.record_event("job", "progress", payload)
    payload["nested"]["value"] = 2
    saved["data"]["nested"]["value"] = 3
    assert state.events_since("job", 0)[0]["data"]["nested"]["value"] == 1
    state.close()


@pytest.mark.parametrize(
    "suffix", ["", "/events", "/event-history", "/diff", "/approvals", "/cancel", "/approve"]
)
def test_cross_tenant_routes_refuse_before_loading_evidence(
    suffix: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.auth import enforce_rate_limit, require_api_key

    state = ConsoleState()
    state.set_owner("foreign", "tenant-b")
    store = InMemoryAgentJobStore()
    store.create("foreign", "sensitive spec")
    monkeypatch.setattr(agent_console, "_state", state)
    monkeypatch.setattr(agent_console, "_store", store)

    # Async dependency keeps the context in the ASGI task for both sync and
    # async handlers. Sync dependencies run in independent thread contexts.
    async def async_auth() -> Any:
        token = TENANT_SCOPE_VAR.set(TenantScope("tenant-a", user_id="alice"))
        try:
            yield
        finally:
            TENANT_SCOPE_VAR.reset(token)

    old = dict(app.dependency_overrides)
    app.dependency_overrides[require_api_key] = async_auth
    app.dependency_overrides[enforce_rate_limit] = lambda: None
    try:
        with TestClient(app) as client:
            if suffix in ("/cancel", "/approve"):
                response = client.post("/agent/jobs/foreign" + suffix, json={"decision": "approve"})
            else:
                response = client.get("/agent/jobs/foreign" + suffix)
            assert response.status_code == 404
            assert "sensitive spec" not in response.text
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(old)
        state.close()


def test_scope_checked_before_store_and_list_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    state = ConsoleState()
    store = InMemoryAgentJobStore()
    for job_id, tenant in (("a", "tenant-a"), ("b", "tenant-b"), ("legacy", None)):
        store.create(job_id, "spec")
        state.set_owner(job_id, tenant)
    monkeypatch.setattr(agent_console, "_state", state)
    monkeypatch.setattr(agent_console, "_store", store)
    token = TENANT_SCOPE_VAR.set(TenantScope("tenant-a"))
    try:
        assert [row["id"] for row in agent_console.list_agent_jobs()["jobs"]] == ["a"]
        with pytest.raises(ApiError) as error:
            agent_console._job_or_404("b")
        assert error.value.status_code == 404
        assert not state.visible("legacy")
    finally:
        TENANT_SCOPE_VAR.reset(token)
        state.close()


def test_editor_refuses_late_writes_after_cancel(tmp_path: Path) -> None:
    from api.agent_runtime import _EventedEditor
    from craft.editor import EditError
    (tmp_path / "calc.py").write_text("old", encoding="utf-8")
    editor = _EventedEditor(tmp_path, backup_dir=None, audit_path=None,
                           emit=lambda kind, data: None, cancelled=lambda: True)
    with pytest.raises(EditError, match="已取消"):
        editor.write_file("calc.py", "new")
    with pytest.raises(EditError, match="已取消"):
        editor.apply_edit("calc.py", "old", "new")
    assert (tmp_path / "calc.py").read_text(encoding="utf-8") == "old"


def test_bounded_event_history_reports_cursor_and_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = InMemoryAgentJobStore()
    state = ConsoleState(max_events=4)
    store.create("job", "spec")
    for i in range(7):
        state.record_event("job", "progress", {"i": i})
    monkeypatch.setattr(agent_console, "_state", state)
    monkeypatch.setattr(agent_console, "_store", store)
    page = agent_console.agent_event_history("job", after_seq=0, limit=2)
    assert [event["seq"] for event in page["events"]] == [4, 5]
    assert page["truncated"] and page["has_more"] and page["next_seq"] == 5
    last = agent_console.agent_event_history("job", after_seq=5, limit=2)
    assert [event["seq"] for event in last["events"]] == [6, 7]
    assert not last["has_more"] and not last["truncated"]
    state.close()
