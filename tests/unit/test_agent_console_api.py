"""API tests for the SpecCraft agent console (/agent/*) — task 8.

No Docker and no network: the durable projection is backed by
storage/agent_jobs.py's InMemoryAgentJobStore (swapped per test), console
state (events/approvals/bundle) is a fresh _ConsoleState per test, and the
rate limiter's RedisStore is faked exactly like tests/unit/test_api_jobs.py.
Coverage: create/get/list/cancel lifecycle, approval records and the plan/
step/gate state transitions, the §8.1 error envelope (JOB_NOT_FOUND /
STATE_CONFLICT / EVIDENCE_UNVERIFIED codes), the SSE event stream (emits
then closes on terminal, stops on client disconnect, replays from
Last-Event-ID) and the structured diff endpoint shape.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.routes.agent_console as agent_console
from api.server import app
from storage.agent_jobs import InMemoryAgentJobStore

API_KEY = "agent-console-test-key"


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
    """Fresh per-test durable backend, swapped for the module global."""
    fresh = InMemoryAgentJobStore()
    monkeypatch.setattr(agent_console, "_store", fresh)
    return fresh


@pytest.fixture()
def state(monkeypatch: pytest.MonkeyPatch) -> agent_console._ConsoleState:
    """Fresh per-test console state (events/approvals/bundle), swapped in."""
    fresh = agent_console._ConsoleState()
    monkeypatch.setattr(agent_console, "_state", fresh)
    return fresh


@pytest.fixture()
def client(store: InMemoryAgentJobStore, state: agent_console._ConsoleState) -> TestClient:
    """TestClient bound to the fresh store + console state of this test."""
    return TestClient(app)


def _headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY}


def _payload() -> dict[str, str]:
    return {
        "repo_path": "D:/experim/specproof-clean-clone-gate",
        "spec_text": "Add pagination to the user list endpoint",
        "task_name": "task8-test",
    }


def _create(client: TestClient) -> str:
    resp = client.post("/agent/jobs", json=_payload(), headers=_headers())
    assert resp.status_code == 202
    return str(resp.json()["job_id"])


def _plan() -> dict[str, Any]:
    return {
        "version": 1,
        "steps": [
            {
                "index": 0,
                "title": "Locate the user list handler",
                "summary": "read_file + grep for the endpoint",
                "status": "pending",
            },
            {
                "index": 1,
                "title": "Apply pagination parameters",
                "summary": "edit the handler signature and query",
                "status": "pending",
            },
        ],
        "created_at": "2026-08-18T00:00:00+00:00",
    }


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


# ── create / get / list ─────────────────────────────────────────────────────


def test_create_agent_job_returns_202_with_id(
    client: TestClient, store: InMemoryAgentJobStore,
) -> None:
    resp = client.post("/agent/jobs", json=_payload(), headers=_headers())
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "PLANNING"
    job = store.get(body["job_id"])
    assert job is not None
    assert job.status == "pending"
    assert job.spec_text == _payload()["spec_text"]
    assert job.spec_digest


def test_create_agent_job_401_without_key(client: TestClient) -> None:
    resp = client.post("/agent/jobs", json=_payload())
    assert resp.status_code == 401


def test_create_agent_job_503_when_key_unconfigured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPECPROOF_API_KEY", "")
    resp = client.post("/agent/jobs", json=_payload())
    assert resp.status_code == 503


def test_create_agent_job_validates_payload(client: TestClient) -> None:
    resp = client.post("/agent/jobs", json={"repo_path": ""}, headers=_headers())
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_FAILED"


def test_get_agent_job_returns_detail(client: TestClient) -> None:
    job_id = _create(client)
    resp = client.get(f"/agent/jobs/{job_id}", headers=_headers())
    assert resp.status_code == 200
    job = resp.json()["job"]
    assert job["id"] == job_id
    assert job["status"] == "PLANNING"
    assert job["plan"] is None
    assert job["progress"]["percent"] == 0.0
    assert job["result"] is None
    assert job["events_count"] == 1
    assert job["repo_path"] == _payload()["repo_path"]


def test_get_agent_job_unknown_returns_404_envelope(client: TestClient) -> None:
    resp = client.get(
        "/agent/jobs/00000000-0000-0000-0000-000000000000", headers=_headers(),
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "JOB_NOT_FOUND"
    assert body["error"]["message"] == body["detail"]
    assert body["error"]["request_id"]
    assert body["schema_version"] == 1


def test_list_agent_jobs_with_status_filter(client: TestClient) -> None:
    first = _create(client)
    second = _create(client)
    client.post(f"/agent/jobs/{first}/cancel", headers=_headers())
    resp = client.get("/agent/jobs", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["count"] == 2
    cancelled = client.get("/agent/jobs?status=CANCELLED", headers=_headers())
    assert cancelled.json()["count"] == 1
    assert cancelled.json()["jobs"][0]["id"] == first
    planning = client.get("/agent/jobs?status=PLANNING", headers=_headers())
    assert planning.json()["count"] == 1
    assert planning.json()["jobs"][0]["id"] == second


def test_list_agent_jobs_rejects_unknown_status(client: TestClient) -> None:
    resp = client.get("/agent/jobs?status=BOGUS", headers=_headers())
    assert resp.status_code == 422


# ── cancel lifecycle ────────────────────────────────────────────────────────


def test_cancel_agent_job_lifecycle(client: TestClient) -> None:
    job_id = _create(client)
    resp = client.post(f"/agent/jobs/{job_id}/cancel", headers=_headers())
    assert resp.status_code == 202
    assert resp.json() == {"job_id": job_id, "status": "CANCELLED"}
    detail = client.get(f"/agent/jobs/{job_id}", headers=_headers()).json()["job"]
    assert detail["status"] == "CANCELLED"
    assert detail["result"]["verdict"] == "CANCELLED"
    again = client.post(f"/agent/jobs/{job_id}/cancel", headers=_headers())
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "STATE_CONFLICT"


def test_cancel_unknown_job_404(client: TestClient) -> None:
    resp = client.post("/agent/jobs/nope/cancel", headers=_headers())
    assert resp.status_code == 404


# ── approvals ───────────────────────────────────────────────────────────────


def test_approve_plan_moves_to_executing(client: TestClient) -> None:
    job_id = _create(client)
    resp = client.post(
        f"/agent/jobs/{job_id}/approve",
        json={"decision": "approve", "note": "LGTM", "target": "plan"},
        headers=_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["job"]["status"] == "EXECUTING"
    approvals = client.get(f"/agent/jobs/{job_id}/approvals", headers=_headers()).json()
    assert approvals["count"] == 1
    record = approvals["approvals"][0]
    assert record["decision"] == "approve"
    assert record["target"] == "plan"
    assert record["note"] == "LGTM"


def test_reject_plan_fails_job_with_note(client: TestClient) -> None:
    job_id = _create(client)
    resp = client.post(
        f"/agent/jobs/{job_id}/approve",
        json={"decision": "reject", "note": "plan misses rollback", "target": "plan"},
        headers=_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["job"]["status"] == "FAILED"
    job = client.get(f"/agent/jobs/{job_id}", headers=_headers()).json()["job"]
    assert job["result"]["reason"] == "plan misses rollback"


def test_step_approvals_gate_to_executing(
    client: TestClient, store: InMemoryAgentJobStore,
) -> None:
    job_id = _create(client)
    store.set_plan(job_id, _plan())
    for index in (0, 1):
        resp = client.post(
            f"/agent/jobs/{job_id}/approve",
            json={"decision": "approve", "target": "step", "step_index": index},
            headers=_headers(),
        )
        assert resp.status_code == 200
    job = client.get(f"/agent/jobs/{job_id}", headers=_headers()).json()["job"]
    assert job["status"] == "EXECUTING"
    assert [s["status"] for s in job["plan"]["steps"]] == ["approved", "approved"]


def test_step_reject_fails_job(
    client: TestClient, store: InMemoryAgentJobStore,
) -> None:
    job_id = _create(client)
    store.set_plan(job_id, _plan())
    resp = client.post(
        f"/agent/jobs/{job_id}/approve",
        json={"decision": "reject", "target": "step", "step_index": 1,
              "note": "unsafe edit"},
        headers=_headers(),
    )
    assert resp.status_code == 200
    job = client.get(f"/agent/jobs/{job_id}", headers=_headers()).json()["job"]
    assert job["status"] == "FAILED"
    assert job["plan"]["steps"][1]["status"] == "rejected"
    assert job["result"]["reason"] == "Plan step 1 rejected"
    assert job["plan"]["steps"][1]["approval"]["note"] == "unsafe edit"


def test_step_approval_requires_step_index(
    client: TestClient, store: InMemoryAgentJobStore,
) -> None:
    job_id = _create(client)
    store.set_plan(job_id, _plan())
    resp = client.post(
        f"/agent/jobs/{job_id}/approve",
        json={"decision": "approve", "target": "step"},
        headers=_headers(),
    )
    assert resp.status_code == 422


def test_step_approval_out_of_range(
    client: TestClient, store: InMemoryAgentJobStore,
) -> None:
    job_id = _create(client)
    store.set_plan(job_id, _plan())
    resp = client.post(
        f"/agent/jobs/{job_id}/approve",
        json={"decision": "approve", "target": "step", "step_index": 11},
        headers=_headers(),
    )
    assert resp.status_code == 422


def test_gate_approval_completes_job(
    client: TestClient, store: InMemoryAgentJobStore,
) -> None:
    job_id = _create(client)
    store.set_plan(job_id, _plan())
    client.post(
        f"/agent/jobs/{job_id}/approve",
        json={"decision": "approve", "target": "plan"},
        headers=_headers(),
    )
    resp = client.post(
        f"/agent/jobs/{job_id}/approve",
        json={"decision": "approve", "target": "gate", "note": "tests green"},
        headers=_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["job"]["status"] == "COMPLETED"
    job = client.get(f"/agent/jobs/{job_id}", headers=_headers()).json()["job"]
    assert job["result"]["verdict"] == "COMPLETED"


def test_approve_terminal_job_conflicts(client: TestClient) -> None:
    job_id = _create(client)
    client.post(f"/agent/jobs/{job_id}/cancel", headers=_headers())
    resp = client.post(
        f"/agent/jobs/{job_id}/approve",
        json={"decision": "approve", "target": "plan"},
        headers=_headers(),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "STATE_CONFLICT"


# ── SSE event stream ────────────────────────────────────────────────────────


def test_events_sse_emits_events_then_closes(
    client: TestClient, store: InMemoryAgentJobStore,
    state: agent_console._ConsoleState,
) -> None:
    job_id = _create(client)
    state.record_event(job_id, "plan", {"version": 1})
    state.record_event(job_id, "tool_call", {"tool": "read_file", "call_id": "c1"})
    state.record_event(job_id, "tool_result", {"call_id": "c1", "ok": True})
    state.set_bundle(job_id, [{"path": "a.py", "status": "added", "before": "", "after": "x"}])
    store.update_status(job_id, "succeeded")

    frames = _collect_sse(client, job_id)
    events = [(ev, json.loads(data)) for ev, data in frames]
    types = [ev for ev, _ in events]
    assert types[0] == "progress"
    assert "plan" in types
    assert "tool_call" in types
    assert "tool_result" in types
    assert "edit" in types
    assert types[-1] == "done"
    done = json.loads(frames[-1][1])
    assert done["status"] == "succeeded"
    seqs = [payload["seq"] for ev, payload in events if ev != "done"]
    assert seqs == sorted(seqs)
    assert len(seqs) == done["delivered"]


class _DisconnectingRequest:
    """Stand-in for a client that leaves after the first frames arrive.

    starlette's TestClient buffers StreamingResponse bodies until the app
    finishes, so an HTTP-level "close early" test would hang forever on a
    live (non-terminal) job. Driving the extracted generator directly
    proves the same contract deterministically: frames are delivered, and
    the loop exits once the client disconnects.
    """

    def __init__(self) -> None:
        self.disconnected = False

    async def is_disconnected(self) -> bool:
        return self.disconnected


async def test_events_stream_stops_on_client_disconnect(
    store: InMemoryAgentJobStore, state: agent_console._ConsoleState,
) -> None:
    job_id = "job-disconnect"
    store.create(job_id, "spec")
    state.set_meta(job_id, "repo", None)
    state.record_event(job_id, "progress", {"status": "PLANNING"})
    request = _DisconnectingRequest()
    stream = agent_console._event_stream(job_id, request, store, state, 0)
    first = await anext(stream)
    assert first == "id: 1\n"
    request.disconnected = True
    with pytest.raises(StopAsyncIteration):
        # drain the remaining frames; the generator loop breaks on disconnect
        while True:
            await anext(stream)


def test_events_sse_replays_from_last_event_id(
    client: TestClient, store: InMemoryAgentJobStore,
    state: agent_console._ConsoleState,
) -> None:
    job_id = _create(client)
    state.record_event(job_id, "plan", {"version": 1})
    state.record_event(job_id, "tool_call", {"tool": "grep", "call_id": "c2"})
    store.update_status(job_id, "succeeded")
    frames = _collect_sse(client, job_id, last_event_id="1")
    events = [(ev, json.loads(data)) for ev, data in frames if ev != "done"]
    assert [payload["seq"] for _, payload in events] == [2, 3]


def test_events_sse_unknown_job_404(client: TestClient) -> None:
    resp = client.get("/agent/jobs/nope/events", headers=_headers())
    assert resp.status_code == 404


# ── structured diff ─────────────────────────────────────────────────────────


def _seed_bundle(state: agent_console._ConsoleState, job_id: str) -> None:
    state.set_bundle(job_id, [
        {
            "path": "src/svc.py",
            "status": "modified",
            "before": "def main():\n    return old\n",
            "after": "def main():\n    return new\n    log()\n",
        },
        {
            "path": "src/new_file.py",
            "status": "added",
            "before": "",
            "after": "x = 1\ny = 2\n",
        },
        {
            "path": "src/old.py",
            "status": "deleted",
            "before": "z = 3\n",
            "after": "",
        },
    ])


def test_diff_endpoint_shape(
    client: TestClient, state: agent_console._ConsoleState,
) -> None:
    job_id = _create(client)
    _seed_bundle(state, job_id)
    resp = client.get(f"/agent/jobs/{job_id}/diff", headers=_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == job_id
    assert body["mode"] == "unified"
    assert body["stats"] == {"files_changed": 3, "insertions": 4, "deletions": 2}
    assert body["generated_at"]
    by_path = {f["path"]: f for f in body["files"]}
    modified = by_path["src/svc.py"]
    assert modified["status"] == "modified"
    assert modified["insertions"] == 2
    assert modified["deletions"] == 1
    hunk_lines = modified["hunks"][0]["lines"]
    assert [line["type"] for line in hunk_lines].count("add") == 2
    assert [line["type"] for line in hunk_lines].count("del") == 1
    assert any(line["type"] == "context" for line in hunk_lines)
    del_line = next(line for line in hunk_lines if line["type"] == "del")
    assert del_line["old_no"] == 2 and del_line["new_no"] is None
    add_line = next(line for line in hunk_lines if line["type"] == "add")
    assert add_line["old_no"] is None and add_line["new_no"] == 2
    added_file = by_path["src/new_file.py"]
    assert added_file["status"] == "added"
    assert all(line["type"] == "add" for h in added_file["hunks"] for line in h["lines"])
    deleted_file = by_path["src/old.py"]
    assert deleted_file["status"] == "deleted"
    assert all(line["type"] == "del" for h in deleted_file["hunks"] for line in h["lines"])
    split = client.get(f"/agent/jobs/{job_id}/diff?mode=split", headers=_headers())
    assert split.status_code == 200
    assert split.json()["mode"] == "split"
    assert split.json()["files"] == body["files"]


def test_diff_missing_bundle_returns_404_evidence(client: TestClient) -> None:
    job_id = _create(client)
    resp = client.get(f"/agent/jobs/{job_id}/diff", headers=_headers())
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "EVIDENCE_UNVERIFIED"


def test_diff_unknown_job_404(client: TestClient) -> None:
    resp = client.get("/agent/jobs/nope/diff", headers=_headers())
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "JOB_NOT_FOUND"


# ── durable store integration (lease / progress) ────────────────────────────


def test_store_lease_is_exclusive_and_renewable() -> None:
    store = InMemoryAgentJobStore()
    job_id = "lease-job"
    store.create(job_id, "spec")
    assert store.lease(job_id, "worker-a", 60.0)
    assert not store.lease(job_id, "worker-b", 60.0)
    assert store.renew(job_id, "worker-a", 60.0)
    store.cancel(job_id, "done")
    assert not store.lease(job_id, "worker-a", 60.0)


def test_detail_reflects_store_plan_and_progress(
    client: TestClient, store: InMemoryAgentJobStore,
) -> None:
    job_id = _create(client)
    store.set_plan(job_id, _plan())
    store.set_progress(job_id, "1", {"percent": 50.0, "message": "halfway"})
    job = client.get(f"/agent/jobs/{job_id}", headers=_headers()).json()["job"]
    assert job["status"] == "AWAITING_APPROVAL"
    assert job["plan"]["steps"][0]["title"] == "Locate the user list handler"
    assert job["progress"]["percent"] == 50.0
    assert job["progress"]["message"] == "halfway"


# ── accept projection (W35.1) reaching the console ─────────────────────────


def _accept_report(overall: str = "passed") -> dict[str, Any]:
    return {
        "task_id": "task8-test",
        "overall": overall,
        "overall_note": "5 gates, 5 passed",
        "duration_ms": 4210,
        "gates": [
            {
                "gate": "run_test",
                "status": "passed",
                "note": "3 tests passed",
                "findings": [],
                "duration_ms": 1200,
            },
        ],
        "summary": f"GATES: task=task8-test overall={overall} run_test=passed",
    }


def test_detail_omits_nothing_about_a_missing_accept_projection(
    client: TestClient, store: InMemoryAgentJobStore,
) -> None:
    """`accept` must be present and null, not absent.

    The page has to tell "this job has no verdict yet" apart from "this
    server does not report verdicts at all"; a missing key would let a stale
    deployment look like an unverified job.
    """
    job_id = _create(client)
    job = client.get(f"/agent/jobs/{job_id}", headers=_headers()).json()["job"]
    assert "accept" in job
    assert job["accept"] is None


def test_accept_projection_round_trips_from_the_real_accept_result(
    client: TestClient, store: InMemoryAgentJobStore,
) -> None:
    """Producer and consumer locked through the real AcceptResult, not a copy.

    craft/accept.py owns these key names and the CLI prints them; the console
    reads the same stored JSON. Feeding a hand-written dict here would leave a
    renamed key invisible — the exact failure mode #55 hit on the matrix path.
    """
    from craft.accept import AcceptResult

    job_id = _create(client)
    store.update_status(job_id, "succeeded")
    store.attach_accept_result(
        job_id,
        AcceptResult(
            verdict="BLOCKED",
            certificate_path=None,
            findings=[{"gate": "run_test", "detail": "2 failures"}],
            gates_report=_accept_report("failed"),
            rolled_back=False,
            note="内部门禁 FAIL: run_test",
        ).to_dict(),
    )

    accept = client.get(f"/agent/jobs/{job_id}", headers=_headers()).json()["job"]["accept"]
    assert accept["attached"] is True
    assert accept["malformed"] is False
    assert accept["verdict"] == "BLOCKED"
    assert accept["note"] == "内部门禁 FAIL: run_test"
    assert accept["rolled_back"] is False
    assert accept["gates"]["overall"] == "failed"
    assert accept["gates"]["entries"][0]["gate"] == "run_test"
    assert accept["gates"]["entries"][0]["findings_total"] == 0
    assert accept["findings"] == [{"gate": "run_test", "detail": "2 failures"}]
    # A path that was never issued stays ABSENT, not null: the page renders
    # "no certificate" either way, and an absent key cannot be mistaken for
    # "there is one somewhere we will not say".
    assert "certificate_path" not in accept


def test_accept_projection_keeps_an_issued_certificate_path(
    client: TestClient, store: InMemoryAgentJobStore,
) -> None:
    job_id = _create(client)
    store.update_status(job_id, "succeeded")
    store.attach_accept_result(
        job_id,
        {
            "verdict": "VERIFIED",
            "certificate_path": "/var/tmp/specproof/jobs/x/merge-certificate.json",
            "findings": [],
            "gates_report": None,
            "rolled_back": False,
            "note": "",
        },
    )
    accept = client.get(f"/agent/jobs/{job_id}", headers=_headers()).json()["job"]["accept"]
    assert accept["verdict"] == "VERIFIED"
    assert accept["certificate_path"].endswith("merge-certificate.json")
    # gates_report was literally null: "no gate summary" must not become an
    # empty list the page could read as "zero checks, all fine".
    assert "gates" not in accept


def test_truncated_accept_lists_say_so(
    client: TestClient, store: InMemoryAgentJobStore,
) -> None:
    """25 findings must never render as "there were 20"."""
    job_id = _create(client)
    store.update_status(job_id, "succeeded")
    report = _accept_report()
    report["gates"] = [
        {
            "gate": f"gate_{index}",
            "status": "passed",
            "note": "",
            "findings": [],
            "duration_ms": 1,
        }
        for index in range(25)
    ]
    store.attach_accept_result(
        job_id,
        {
            "verdict": "BLOCKED",
            "certificate_path": None,
            "findings": [{"id": index} for index in range(25)],
            "gates_report": report,
            "rolled_back": False,
            "note": "",
        },
    )
    accept = client.get(f"/agent/jobs/{job_id}", headers=_headers()).json()["job"]["accept"]
    assert len(accept["findings"]) == agent_console._ACCEPT_FINDING_CAP
    assert accept["findings_total"] == 25
    assert accept["findings_truncated"] is True
    assert len(accept["gates"]["entries"]) == agent_console._ACCEPT_GATE_CAP
    assert accept["gates"]["total"] == 25
    assert accept["gates"]["truncated"] is True


def test_unknown_accept_gate_status_passes_through(
    client: TestClient, store: InMemoryAgentJobStore,
) -> None:
    """A status this endpoint has never seen is shown, not swallowed.

    Silently dropping an unrecognised gate row would hide exactly the
    evidence a reviewer needs, and would under-report the gate count.
    """
    job_id = _create(client)
    store.update_status(job_id, "succeeded")
    report = _accept_report()
    report["gates"] = [
        {
            "gate": "custom_gate",
            "status": "needs_review",
            "note": "",
            "findings": [],
            "duration_ms": 2,
        }
    ]
    store.attach_accept_result(
        job_id,
        {
            "verdict": "BLOCKED",
            "certificate_path": None,
            "findings": [],
            "gates_report": report,
            "rolled_back": False,
            "note": "",
        },
    )
    accept = client.get(f"/agent/jobs/{job_id}", headers=_headers()).json()["job"]["accept"]
    assert accept["gates"]["entries"] == [
        {
            "gate": "custom_gate",
            "status": "needs_review",
            "note": "",
            "duration_ms": 2,
            "findings_total": 0,
        }
    ]


def test_unreadable_accept_projection_is_not_reported_as_missing(
    client: TestClient, store: InMemoryAgentJobStore,
) -> None:
    """Corrupt stored JSON is its own state — never "没有验收记录"."""
    from dataclasses import replace

    job_id = _create(client)
    store.update_status(job_id, "succeeded")
    store.attach_accept_result(job_id, {"verdict": "BLOCKED", "note": "x"})
    stored = store.get(job_id)
    assert stored is not None
    store._jobs[job_id] = replace(stored, accept_json='{"verdict": "BLOCKED"')

    accept = client.get(f"/agent/jobs/{job_id}", headers=_headers()).json()["job"]["accept"]
    assert accept == {"attached": True, "malformed": True}


def test_the_two_blocked_flavors_reach_the_console_apart(
    client: TestClient, store: InMemoryAgentJobStore,
) -> None:
    """BLOCKED-by-failed-gate and BLOCKED-by-deferred-closure stay tellable.

    Locked through the real producer, `AgentRuntime._gate_accept_projection`,
    not a hand-written payload: the console colours the verdict from
    ``gates.overall``, so if this endpoint ever dropped that field the page
    would paint a genuine gate failure amber and tell the reader nothing
    failed. `_accept_report` builds a fresh dict per call, so mutating here
    cannot leak between cases.
    """
    from api.agent_runtime import AgentRuntime

    def attach(report: dict[str, Any]) -> dict[str, Any]:
        job_id = _create(client)
        store.update_status(job_id, "succeeded")
        projection = AgentRuntime._gate_accept_projection(report)
        store.attach_accept_result(job_id, projection.to_dict())
        response = client.get(f"/agent/jobs/{job_id}", headers=_headers())
        return response.json()["job"]["accept"]

    failed = _accept_report("failed")
    failed["gates"][0]["status"] = "failed"
    failed["gates"][0]["findings"] = [{"gate": "run_test", "detail": "test_page_size"}]
    blocked_by_gate = attach({"gates": failed})
    assert blocked_by_gate["verdict"] == "BLOCKED"
    assert blocked_by_gate["gates"]["overall"] == "failed"
    assert blocked_by_gate["gates"]["entries"][0]["status"] == "failed"
    assert blocked_by_gate["findings_total"] == 1

    blocked_by_deferral = attach({"gates": _accept_report("passed")})
    assert blocked_by_deferral["verdict"] == "BLOCKED"
    assert blocked_by_deferral["gates"]["overall"] == "passed"
    assert blocked_by_deferral["findings_total"] == 0

    # Same token, different fact — the two must not be byte-identical, or the
    # UI has nothing to discriminate on.
    assert blocked_by_gate["gates"]["overall"] != blocked_by_deferral["gates"]["overall"]

    errored = attach({})
    assert errored["verdict"] == "ERROR"
    # A projection without a gate summary carries no `gates` key at all: the
    # page must say "cannot tell why", never infer the passing flavour.
    assert "gates" not in errored
