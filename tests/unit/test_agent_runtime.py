"""W42 AgentRuntime lifecycle tests (deterministic CraftLoop behind /agent/jobs).

Covers the live-runtime contract end to end, all in-memory/local:
  - full lifecycle: start -> poll until terminal -> durable projection
    (plan/progress/result) + SSE events (plan/tool/gate/progress) +
    attach_accept_result gate summary;
  - cancel mid-run: the cooperative flag + store.cancel win over the
    leased worker thread (CANCELLED terminal, no accept attach);
  - cancel before start and cancel of unknown/terminal jobs;
  - concurrent jobs do not interfere (separate temp workspaces, per-job
    events and projections);
  - the HTTP layer: POST /agent/jobs with auto_start=true, poll GET until
    terminal, drain the SSE stream; the pre-W42 payloads stay passive;
  - no LLM / no network / no Docker: socket creation is forbidden for the
    whole run and no LLM usage is recorded.

No network, no live LLM, no Docker.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.routes.agent_console as agent_console
from api._agent_demo import DEMO_SPEC_TEXT
from api.agent_runtime import AgentRuntime
from api.server import app
from craft.editor import Editor
from craft.planner import Step
from storage.agent_jobs import InMemoryAgentJobStore

API_KEY = "agent-runtime-test-key"


@pytest.fixture(autouse=True)
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECPROOF_API_KEY", API_KEY)


class FakeRedisRateLimit:
    """Backs enforce_rate_limit (patched on storage.redis.RedisStore)."""

    def incr(self, key: str) -> int:
        return 1

    def expire(self, key: str, ttl: int) -> None:
        return None


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("storage.redis.RedisStore", FakeRedisRateLimit)


@pytest.fixture()
def store(monkeypatch: pytest.MonkeyPatch) -> InMemoryAgentJobStore:
    """Fresh per-test durable backend, swapped for the console global."""
    fresh = InMemoryAgentJobStore()
    monkeypatch.setattr(agent_console, "_store", fresh)
    return fresh


@pytest.fixture()
def state(monkeypatch: pytest.MonkeyPatch) -> agent_console._ConsoleState:
    """Fresh per-test console state, swapped in."""
    fresh = agent_console._ConsoleState()
    monkeypatch.setattr(agent_console, "_state", fresh)
    return fresh


@pytest.fixture(autouse=True)
def fresh_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AgentRuntime:
    """Per-test runtime singleton with a local workspace root."""
    runtime = AgentRuntime(workspace_root=tmp_path / "console-runtime")
    monkeypatch.setattr(agent_console, "_runtime", runtime)
    return runtime


@pytest.fixture()
def client(store: InMemoryAgentJobStore, state: agent_console._ConsoleState) -> TestClient:
    """TestClient bound to the fresh store + console state of this test."""
    return TestClient(app)


def _headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY}


def _make_runtime(
    tmp_path: Path,
) -> tuple[AgentRuntime, InMemoryAgentJobStore, agent_console._ConsoleState]:
    store = InMemoryAgentJobStore()
    state = agent_console._ConsoleState()
    runtime = AgentRuntime(store=store, state=state, workspace_root=tmp_path / "runtime")
    return runtime, store, state


def _collect_sse(
    client: TestClient, job_id: str, last_event_id: str = "0",
) -> list[tuple[str, str]]:
    """Drain an SSE stream to its natural close; returns (event, data) pairs."""
    headers = _headers()
    if last_event_id != "0":
        headers["Last-Event-ID"] = last_event_id
    frames: list[tuple[str, str]] = []
    with client.stream("GET", f"/agent/jobs/{job_id}/events", headers=headers) as resp:
        assert resp.status_code == 200
        current_event = "message"
        for line in resp.iter_lines():
            if line.startswith("event: "):
                current_event = line[len("event: "):]
            elif line.startswith("data: "):
                frames.append((current_event, line[len("data: "):]))
    return frames


# ── full lifecycle (runtime-level) ────────────────────────────────────────


def test_demo_job_full_lifecycle(tmp_path: Path) -> None:
    runtime, store, state = _make_runtime(tmp_path)
    runtime.start("job-demo", "", "", task_name="demo-calc")
    assert runtime.wait_until_terminal("job-demo", timeout=180.0)

    job = store.get("job-demo")
    assert job is not None
    assert job.status == "succeeded"
    assert job.started_at is not None and job.finished_at is not None
    assert job.lease_owner is None  # terminal status released the lease
    assert job.spec_text == DEMO_SPEC_TEXT
    assert job.plan_json is not None
    plan = json.loads(job.plan_json)
    assert plan["mode"] == "deterministic"
    assert [step["id"] for step in plan["steps"]] == ["s1", "s2", "s3", "s4"]
    assert job.progress_json is not None
    assert job.result_json is not None
    result = json.loads(job.result_json)
    assert result["result"] == "DONE"

    # attach_accept_result landed with the real five-gate summary
    assert job.accept_json is not None
    accept = json.loads(job.accept_json)
    assert accept["verdict"] in ("BLOCKED", "ERROR")
    gates = accept["gates_report"]
    assert isinstance(gates, dict)
    assert len(gates["gates"]) == 5
    assert gates["overall"] in ("passed", "skipped")
    assert str(gates["summary"]).startswith("GATES: ")

    # live event log: plan / tool / edit / gate / progress all present
    events = state.events_since("job-demo", 0)
    event_types = {str(event["type"]) for event in events}
    assert {"plan", "tool_call", "tool_result", "edit", "gate", "progress"} <= event_types
    plan_events = [event for event in events if event["type"] == "plan"]
    assert plan_events and plan_events[0]["data"]["mode"] == "deterministic"
    tool_calls = [event for event in events if event["type"] == "tool_call"]
    assert any(event["data"].get("tool") == "apply_edit" for event in tool_calls)
    terminal = [
        event
        for event in events
        if event["type"] == "progress" and event["data"].get("status") == "COMPLETED"
    ]
    assert terminal

    # the demo fix really landed in the materialized temp workspace
    meta = state.meta_for("job-demo")
    workspace = Path(meta["repo_path"])
    assert workspace.is_dir()
    assert "return x * 2" in (workspace / "calc.py").read_text(encoding="utf-8")
    bundle = state.bundle_for("job-demo")
    assert any(entry["path"] == "calc.py" for entry in bundle)


def test_demo_without_fix_registry_fails_honestly(tmp_path: Path) -> None:
    runtime, store, state = _make_runtime(tmp_path)
    runtime.start("job-nofix", "", "", fix_registry={})
    assert runtime.wait_until_terminal("job-nofix", timeout=180.0)
    job = store.get("job-nofix")
    assert job is not None and job.status == "failed"
    assert job.result_json is not None
    result = json.loads(job.result_json)
    assert result["result"] == "FAILED"
    assert job.accept_json is not None  # failed jobs still get the gate summary
    accept = json.loads(job.accept_json)
    assert accept["verdict"] in ("BLOCKED", "ERROR")
    assert accept["gates_report"] is not None


def test_invalid_spec_fails_honestly(tmp_path: Path) -> None:
    runtime, store, state = _make_runtime(tmp_path)
    runtime.start("job-bad", "", "{not-json")
    assert runtime.wait_until_terminal("job-bad", timeout=60.0)
    job = store.get("job-bad")
    assert job is not None and job.status == "failed"
    assert job.error and "spec" in job.error
    events = state.events_since("job-bad", 0)
    assert any(
        event["type"] == "progress" and event["data"].get("status") == "FAILED"
        for event in events
    )


# ── cancel ─────────────────────────────────────────────────────────────────


def test_cancel_mid_run_wins_and_marks_cancelled(tmp_path: Path) -> None:
    runtime, store, state = _make_runtime(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    def slow_fix(editor: Editor, step: Step, diagnosis: str) -> list[str]:
        entered.set()
        assert release.wait(timeout=30.0)
        editor.apply_edit("calc.py", "return x / 2", "return x * 2")
        return ["calc.py"]

    runtime.start("job-cancel", "", "", fix_registry={"test": slow_fix})
    assert entered.wait(timeout=30.0)
    assert runtime.cancel("job-cancel")
    release.set()
    assert runtime.wait_until_terminal("job-cancel", timeout=180.0)

    job = store.get("job-cancel")
    assert job is not None
    assert job.status == "cancelled"
    assert job.error == "Cancelled by user"
    assert job.accept_json is None  # cancelled keeps its closed projection
    events = state.events_since("job-cancel", 0)
    assert any(
        event["type"] == "progress" and event["data"].get("status") == "CANCELLED"
        for event in events
    )


def test_cancel_before_start_is_honored(tmp_path: Path) -> None:
    runtime, store, state = _make_runtime(tmp_path)
    store.create("job-pre", DEMO_SPEC_TEXT)
    assert runtime.cancel("job-pre")
    runtime.start("job-pre", "", "")
    assert runtime.wait_until_terminal("job-pre", timeout=60.0)
    job = store.get("job-pre")
    assert job is not None and job.status == "cancelled"
    events = state.events_since("job-pre", 0)
    assert not [event for event in events if event["type"] == "plan"]


def test_cancel_unknown_and_terminal_jobs_are_rejected(tmp_path: Path) -> None:
    runtime, store, _state = _make_runtime(tmp_path)
    assert runtime.cancel("nope") is False
    store.create("job-t", "spec")
    store.update_status("job-t", "succeeded")
    assert runtime.cancel("job-t") is False  # terminal jobs are never flipped
    terminal = store.get("job-t")
    assert terminal is not None and terminal.status == "succeeded"


# ── concurrency ────────────────────────────────────────────────────────────


def test_two_concurrent_jobs_do_not_interfere(tmp_path: Path) -> None:
    runtime, store, state = _make_runtime(tmp_path)
    runtime.start("job-a", "", "")
    runtime.start("job-b", "", "")
    assert runtime.wait_until_terminal("job-a", timeout=180.0)
    assert runtime.wait_until_terminal("job-b", timeout=180.0)
    job_a = store.get("job-a")
    job_b = store.get("job-b")
    assert job_a is not None and job_a.status == "succeeded"
    assert job_b is not None and job_b.status == "succeeded"

    # independent temp workspaces — the two loops never share state
    meta_a = state.meta_for("job-a")
    meta_b = state.meta_for("job-b")
    assert meta_a["repo_path"] != meta_b["repo_path"]
    assert Path(meta_a["repo_path"]).is_dir()
    assert Path(meta_b["repo_path"]).is_dir()

    # per-job projections and accept records carry their own job id
    result_a = json.loads(job_a.result_json or "{}")
    result_b = json.loads(job_b.result_json or "{}")
    assert result_a["job_id"] == "job-a" and result_b["job_id"] == "job-b"
    accept_a = json.loads(job_a.accept_json or "{}")
    accept_b = json.loads(job_b.accept_json or "{}")
    assert accept_a["gates_report"]["task_id"] == "job-a"
    assert accept_b["gates_report"]["task_id"] == "job-b"

    # per-job event logs exist and stay per-job
    assert state.events_since("job-a", 0)
    assert state.events_since("job-b", 0)


# ── no LLM / no network / no Docker ───────────────────────────────────────


def test_no_llm_no_network_no_docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network socket creation is forbidden during the runtime run")

    monkeypatch.setattr(socket, "socket", forbidden)
    runtime, store, _state = _make_runtime(tmp_path)
    runtime.start("job-no-net", "", "")
    assert runtime.wait_until_terminal("job-no-net", timeout=180.0)
    job = store.get("job-no-net")
    assert job is not None and job.status == "succeeded"
    result = json.loads(job.result_json or "{}")
    assert result["mode"] == "deterministic"
    assert result["budget_used"]["tokens"] == 0.0  # zero LLM tokens spent
    assert "llm_usage" not in result  # no LLM client was ever attached


# ── HTTP layer: auto_start create -> poll GET -> SSE drain ────────────────


def test_create_auto_start_then_poll_get_to_terminal(
    client: TestClient, store: InMemoryAgentJobStore,
    state: agent_console._ConsoleState, fresh_runtime: AgentRuntime,
) -> None:
    resp = client.post("/agent/jobs", json={"auto_start": True}, headers=_headers())
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "PLANNING"  # response shape unchanged
    job_id = str(body["job_id"])

    deadline = time.monotonic() + 180.0
    detail: dict[str, Any] = {}
    while time.monotonic() < deadline:
        detail = client.get(f"/agent/jobs/{job_id}", headers=_headers()).json()["job"]
        if detail["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
            break
        time.sleep(0.1)
    assert detail["status"] == "COMPLETED"
    assert detail["plan"]["steps"][0]["id"] == "s1"
    assert detail["events_count"] > 0
    assert detail["spec_text"] == DEMO_SPEC_TEXT

    job = store.get(job_id)
    assert job is not None and job.status == "succeeded"
    assert job.accept_json is not None

    # the runtime thread finished its post-run (gates/bundle/terminal events
    # are all recorded) before the SSE stream is drained
    assert fresh_runtime.wait_until_terminal(job_id, timeout=180.0)
    frames = _collect_sse(client, job_id)
    types = [event for event, _data in frames]
    assert types[-1] == "done"
    assert "plan" in types and "tool_call" in types and "gate" in types


def test_create_without_auto_start_stays_passive(client: TestClient) -> None:
    resp = client.post(
        "/agent/jobs",
        json={"repo_path": "some/repo", "spec_text": "a plain spec"},
        headers=_headers(),
    )
    assert resp.status_code == 202
    job_id = str(resp.json()["job_id"])
    detail = client.get(f"/agent/jobs/{job_id}", headers=_headers()).json()["job"]
    assert detail["status"] == "PLANNING"
    assert detail["plan"] is None


def test_auto_start_requires_repo_and_spec_together(client: TestClient) -> None:
    resp = client.post(
        "/agent/jobs",
        json={"auto_start": True, "repo_path": "some/repo"},
        headers=_headers(),
    )
    assert resp.status_code == 422
