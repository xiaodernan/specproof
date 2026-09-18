"""Model planning is read-only until approval; approved plans are reused."""
import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

import api.agent_runtime as runtime_module
import api.routes.agent_console as console
from api._agent_demo import DEMO_SPEC_TEXT
from api.agent_runtime import AgentRuntime
from api.server import app
from craft.planner import compile_plan
from craft.spec import parse_spec
from storage.agent_jobs import InMemoryAgentJobStore


@pytest.fixture
def runtime_env(tmp_path, monkeypatch):
    store = InMemoryAgentJobStore()
    state = console._ConsoleState()
    runtime = AgentRuntime(store=store, state=state, workspace_root=tmp_path)
    monkeypatch.setattr(console, "_store", store)
    monkeypatch.setattr(console, "_state", state)
    monkeypatch.setattr(console, "_runtime", runtime)
    monkeypatch.setenv("SPECPROOF_API_KEY", "runtime-test")
    from api.auth import enforce_rate_limit

    app.dependency_overrides[enforce_rate_limit] = lambda: None
    yield store, state, runtime
    app.dependency_overrides.pop(enforce_rate_limit, None)


def wait_for_plan(store, job_id):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        job = store.get(job_id)
        if job.plan_json or job.status == "failed":
            return job
        time.sleep(0.01)
    raise AssertionError("Planner did not publish a result")


def test_llm_plan_waits_for_approval_then_runs_same_plan(runtime_env, tmp_path, monkeypatch):
    store, state, runtime = runtime_env
    source = tmp_path / "calc.py"
    source.write_text("original", encoding="utf-8")
    calls = []
    plan = replace(compile_plan(parse_spec(DEMO_SPEC_TEXT)), mode="llm")

    class Client:
        available = True

        def __init__(self, **kwargs):
            self.stream_hook = kwargs["stream_hook"]

        def close(self):
            pass

    def planner(spec, *, mode, client):
        calls.append((mode, client))
        client.stream_hook("planning text")
        return plan

    class Loop:
        def __init__(self, spec, approved, workspace, **kwargs):
            assert approved == plan
            assert kwargs["client"] is not None
            self.job_id = kwargs["job_id"]
            self.editor = kwargs["tool_registry"].editor

        def run(self):
            self.editor.write_file("calc.py", "edited after approval")
            store.update_status(self.job_id, "succeeded", result_json={"result": "DONE"})
            return {"result": "DONE"}

    monkeypatch.setattr(runtime_module, "LLMClient", Client)
    monkeypatch.setattr(runtime_module, "compile_plan", planner)
    monkeypatch.setattr(runtime_module, "CraftLoop", Loop)
    client = TestClient(app)
    headers = {"X-API-Key": "runtime-test"}
    created = client.post("/agent/jobs", headers=headers, json={
        "repo_path": str(tmp_path), "spec_text": DEMO_SPEC_TEXT,
        "execution_mode": "llm", "plan_first": True,
    })
    assert created.status_code == 202
    job_id = created.json()["job_id"]
    planned = wait_for_plan(store, job_id)
    assert planned.status == "pending"
    assert source.read_text() == "original"
    assert len(calls) == 1
    assert any(event["type"] == "model_output" for event in state.events_since(job_id, 0))
    # Metadata survives resetting the process-local console state.
    monkeypatch.setattr(console, "_state", console._ConsoleState())
    detail = client.get(f"/agent/jobs/{job_id}", headers=headers).json()["job"]
    assert detail["repo_path"] == str(tmp_path)
    assert detail["execution_mode"] == "llm"
    assert detail["plan"]["steps"][0]["title"]
    assert client.post(f"/agent/jobs/{job_id}/approve", headers=headers,
                       json={"target": "gate", "decision": "approve"}).status_code == 409
    approved = client.post(f"/agent/jobs/{job_id}/approve", headers=headers,
                           json={"target": "plan", "decision": "approve"})
    assert approved.status_code == 200
    assert runtime.wait_until_terminal(job_id, timeout=3)
    assert source.read_text() == "edited after approval"
    assert len(calls) == 1  # do not regenerate the reviewed plan
    assert client.post(f"/agent/jobs/{job_id}/approve", headers=headers,
                       json={"target": "plan", "decision": "approve"}).status_code == 409


def test_llm_planning_never_silently_falls_back(runtime_env, tmp_path, monkeypatch):
    store, _state, runtime = runtime_env
    deterministic = replace(compile_plan(parse_spec(DEMO_SPEC_TEXT)), llm_fallback_reason="offline")

    class Client:
        available = True

        def __init__(self, **kwargs):
            pass

        def close(self):
            pass

    monkeypatch.setattr(runtime_module, "LLMClient", Client)
    monkeypatch.setattr(runtime_module, "compile_plan", lambda *a, **kw: deterministic)
    runtime.start("fallback", str(tmp_path), DEMO_SPEC_TEXT, execution_mode="llm", plan_only=True)
    assert runtime.wait_until_terminal("fallback", timeout=3)
    job = store.get("fallback")
    assert job.status == "failed"
    assert "offline" in job.error
    assert job.plan_json is None
    assert not (tmp_path / ".specraft").exists()


def test_missing_model_fails_before_planning_or_editing(runtime_env, tmp_path, monkeypatch):
    store, _state, runtime = runtime_env

    class Unavailable:
        available = False

        def __init__(self, **kwargs):
            pass

        def close(self):
            pass

    monkeypatch.setattr(runtime_module, "LLMClient", Unavailable)
    runtime.start("missing", str(tmp_path), DEMO_SPEC_TEXT, execution_mode="llm", plan_only=True)
    assert runtime.wait_until_terminal("missing", timeout=3)
    assert store.get("missing").status == "failed"
    assert "模型未配置" in store.get("missing").error
    assert not (tmp_path / ".specraft").exists()

def test_approved_plan_record_survives_console_restart(runtime_env, tmp_path):
    import json

    store, _state, _runtime = runtime_env
    document = {"title": "task", "description": "", "acceptance_criteria": [],
                "forbidden_changes": [], "affected_area_hint": "calc.py",
                "_console": {"repo_path": str(tmp_path), "execution_mode": "llm"}}
    job_id = "8c3ee34c-df5c-4b71-a3ca-f3b58e5ba990"
    store.create(job_id, json.dumps(document))
    store.set_plan(job_id, {"steps": [], "_console": {
        "approved": True, "approved_at": "2026-09-18T12:00:00Z", "approval_note": "reviewed",
    }})
    path = tmp_path / ".specraft" / "jobs" / job_id
    path.mkdir(parents=True)
    (path / "change-bundle.json").write_text(json.dumps({"files": [
        {"path": "calc.py", "status": "modified", "before": "old\n", "after": "new\n"}
    ]}))
    client = TestClient(app)
    headers = {"X-API-Key": "runtime-test"}
    approvals = client.get(f"/agent/jobs/{job_id}/approvals", headers=headers).json()
    assert approvals["approvals"][0]["note"] == "reviewed"
    diff = client.get(f"/agent/jobs/{job_id}/diff", headers=headers)
    assert diff.status_code == 200
    assert diff.json()["stats"]["files_changed"] == 1


def test_craft_loop_keeps_recorded_approval(runtime_env, tmp_path):
    import json

    from craft.loop import CraftLoop

    store, _state, _runtime = runtime_env
    spec = parse_spec(DEMO_SPEC_TEXT)
    plan = compile_plan(spec)
    store.create("preserve-approval", DEMO_SPEC_TEXT)
    decision = {"approved": True, "approved_at": "2026-09-18T12:00:00Z"}
    store.set_plan("preserve-approval", {**plan.to_dict(), "_console": decision})
    loop = CraftLoop(spec, plan, tmp_path, job_id="preserve-approval", store=store,
                     exec_mode="local")
    # Stop at first execution step, after the durable plan projection.
    class StopAfterProjectionError(Exception):
        pass
    def stop_at_step(_index):
        raise StopAfterProjectionError()
    class States:
        def __getitem__(self, index):
            return stop_at_step(index)
    loop.states = States()
    with pytest.raises(StopAfterProjectionError):
        loop.run()
    assert json.loads(store.get("preserve-approval").plan_json)["_console"] == decision
