"""Backlog #8 — job creation whitelist tests (POST /jobs and POST /agent/jobs).

Both creation endpoints must be fail-closed: any payload key outside the
documented allowlist — arbitrary command fields, env injection, docker
overrides, output paths, tools, or plain unknown keys — is refused with
422 VALIDATION_FAILED and nothing is persisted, while legal payloads keep
working unchanged (regression). The agent console must reject unknown
fields instead of silently dropping them (pydantic's default behavior).

No live MySQL / Redis / Docker: the stores are faked exactly like the
existing API tests (tests/unit/test_api_jobs.py, test_agent_console_api.py).
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import api.routes.agent_console as agent_console
import api.routes.jobs as jobs_module
from api.server import app
from storage.agent_jobs import InMemoryAgentJobStore

API_KEY = "job-whitelist-test-key"

VALID_JOBS_PAYLOAD: dict[str, str] = {
    "repo_path": "D:/experim/specproof-clean-clone-gate",
    "base_ref": "base",
    "head_ref": "head-v1",
    "spec_path": "demo/requirement.txt",
    "depth": "FAST",
}

VALID_AGENT_PAYLOAD: dict[str, str] = {
    "repo_path": "D:/experim/specproof-clean-clone-gate",
    "spec_text": "Add pagination to the user list endpoint",
    "task_name": "whitelist-test",
}

#: Payload fields that must never be accepted by either creation endpoint:
#: arbitrary command / env injection / docker override / output path /
#: tool / unknown-key variants.
MALICIOUS_FIELD_VARIANTS: list[dict[str, object]] = [
    {"command": "calc.exe"},
    {"command": ["cmd.exe", "/c", "whoami"]},
    {"shell": "powershell -enc ..."},
    {"env": {"LLM_API_KEY": "attacker-controlled"}},
    {"environment": ["MYSQL_PASSWORD=hunter2"]},
    {"docker_image": "alpine:latest"},
    {"docker": {"image": "alpine", "privileged": True}},
    {"container": {"image": "evil"}},
    {"output_path": "C:/Windows/System32"},
    {"output_dir": "/tmp"},
    {"tool": "bash"},
    {"tools": [{"type": "shell"}]},
    {"extra_args": ["--privileged"]},
    {"unknown_field": "x"},
]

MALICIOUS_IDS: list[str] = [next(iter(v)) for v in MALICIOUS_FIELD_VARIANTS]


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


class FakeMySQLStore:
    """In-memory stand-in for the /jobs route handlers."""

    rows: dict[str, dict[str, object]] = {}

    def create_job_with_outbox(self, job: dict[str, object]) -> str:
        FakeMySQLStore.rows[str(job["id"])] = dict(job)
        return str(job["id"])


@pytest.fixture()
def fake_mysql(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    FakeMySQLStore.rows = {}
    monkeypatch.setattr(jobs_module, "MySQLStore", FakeMySQLStore)
    yield
    FakeMySQLStore.rows = {}


@pytest.fixture()
def agent_store(monkeypatch: pytest.MonkeyPatch) -> InMemoryAgentJobStore:
    """Fresh per-test durable backend, swapped for the module global."""
    fresh = InMemoryAgentJobStore()
    monkeypatch.setattr(agent_console, "_store", fresh)
    return fresh


@pytest.fixture()
def agent_state(monkeypatch: pytest.MonkeyPatch) -> agent_console._ConsoleState:
    """Fresh per-test console state, swapped for the module global."""
    fresh = agent_console._ConsoleState()
    monkeypatch.setattr(agent_console, "_state", fresh)
    return fresh


class FakeRuntime:
    """Records runtime start calls so auto_start stays hermetic (no threads)."""

    started: list[tuple[str, str, str, str | None]] = []

    def start(
        self, job_id: str, repo_path: str, spec_text: str,
        task_name: str | None = None,
    ) -> None:
        FakeRuntime.started.append((job_id, repo_path, spec_text, task_name))


def _headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY}


# ── POST /jobs — malicious payloads must be refused, nothing persisted ──────


@pytest.mark.parametrize("bad", MALICIOUS_FIELD_VARIANTS, ids=MALICIOUS_IDS)
def test_jobs_create_rejects_malicious_field(fake_mysql: None, bad: dict[str, object]) -> None:
    client = TestClient(app)
    resp = client.post("/jobs", json={**VALID_JOBS_PAYLOAD, **bad}, headers=_headers())
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_FAILED"
    assert body["error"]["retryable"] is False
    assert FakeMySQLStore.rows == {}  # refused, never silently dropped


def test_jobs_unknown_field_error_names_field(fake_mysql: None) -> None:
    client = TestClient(app)
    resp = client.post(
        "/jobs", json={**VALID_JOBS_PAYLOAD, "command": "calc.exe"}, headers=_headers(),
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert isinstance(detail, list)
    assert any("command" in str(item.get("msg", "")) for item in detail)


def test_jobs_non_object_payload_rejected(fake_mysql: None) -> None:
    client = TestClient(app)
    resp = client.post("/jobs", json=["not", "an", "object"], headers=_headers())
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_FAILED"
    assert FakeMySQLStore.rows == {}


@pytest.mark.parametrize("bad_depth", ["fast", "DEEP", "FULL", "FAST\\ncmd", ""])
def test_jobs_depth_outside_allowlist_rejected(fake_mysql: None, bad_depth: str) -> None:
    client = TestClient(app)
    resp = client.post(
        "/jobs", json={**VALID_JOBS_PAYLOAD, "depth": bad_depth}, headers=_headers(),
    )
    assert resp.status_code == 422
    assert FakeMySQLStore.rows == {}


def test_jobs_model_rejects_unknown_key_directly() -> None:
    with pytest.raises(ValidationError, match="Unknown field"):
        jobs_module.JobCreateRequest.model_validate({**VALID_JOBS_PAYLOAD, "command": "x"})


def test_jobs_model_rejects_non_string_key_directly() -> None:
    with pytest.raises(ValidationError, match="Unknown field"):
        jobs_module.JobCreateRequest.model_validate({**VALID_JOBS_PAYLOAD, 5: "x"})


# ── POST /jobs — legal payloads unaffected (regression) ─────────────────────


def test_jobs_valid_payload_accepted_and_persisted(fake_mysql: None) -> None:
    client = TestClient(app)
    resp = client.post("/jobs", json=VALID_JOBS_PAYLOAD, headers=_headers())
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "QUEUED"
    row = FakeMySQLStore.rows[body["job_id"]]
    assert set(row.keys()) == {"id", "repo_path", "base_ref", "head_ref", "spec_path", "depth"}
    assert row["depth"] == "FAST"


def test_jobs_depth_defaults_to_fast(fake_mysql: None) -> None:
    payload = {k: v for k, v in VALID_JOBS_PAYLOAD.items() if k != "depth"}
    client = TestClient(app)
    resp = client.post("/jobs", json=payload, headers=_headers())
    assert resp.status_code == 202
    row = FakeMySQLStore.rows[resp.json()["job_id"]]
    assert row["depth"] == "FAST"


# ── POST /agent/jobs — malicious payloads must be refused, nothing persisted ─


@pytest.mark.parametrize("bad", MALICIOUS_FIELD_VARIANTS, ids=MALICIOUS_IDS)
def test_agent_jobs_create_rejects_malicious_field(
    agent_store: InMemoryAgentJobStore,
    agent_state: agent_console._ConsoleState,
    bad: dict[str, object],
) -> None:
    client = TestClient(app)
    resp = client.post("/agent/jobs", json={**VALID_AGENT_PAYLOAD, **bad}, headers=_headers())
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_FAILED"
    assert body["error"]["retryable"] is False
    assert agent_store.list() == []  # refused, never silently dropped


def test_agent_jobs_unknown_field_error_names_field(
    agent_store: InMemoryAgentJobStore, agent_state: agent_console._ConsoleState,
) -> None:
    client = TestClient(app)
    resp = client.post(
        "/agent/jobs", json={**VALID_AGENT_PAYLOAD, "command": "calc.exe"}, headers=_headers(),
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert isinstance(detail, list)
    assert any("command" in str(item.get("msg", "")) for item in detail)


def test_agent_jobs_model_rejects_unknown_key_directly() -> None:
    with pytest.raises(ValidationError, match="Unknown field"):
        agent_console.AgentJobCreateRequest.model_validate(
            {**VALID_AGENT_PAYLOAD, "command": "x"},
        )


# ── POST /agent/jobs — legal payloads unaffected (regression) ───────────────


def test_agent_jobs_valid_payload_accepted(
    agent_store: InMemoryAgentJobStore, agent_state: agent_console._ConsoleState,
) -> None:
    client = TestClient(app)
    resp = client.post("/agent/jobs", json=VALID_AGENT_PAYLOAD, headers=_headers())
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    jobs = agent_store.list()
    assert len(jobs) == 1
    assert jobs[0].id == job_id
    assert jobs[0].spec_text == VALID_AGENT_PAYLOAD["spec_text"]
    detail = client.get(f"/agent/jobs/{job_id}", headers=_headers())
    assert detail.status_code == 200
    assert detail.json()["job"]["repo_path"] == VALID_AGENT_PAYLOAD["repo_path"]


def test_agent_jobs_auto_start_payload_accepted_with_exact_fields(
    agent_store: InMemoryAgentJobStore,
    agent_state: agent_console._ConsoleState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeRuntime.started = []
    runtime = FakeRuntime()
    monkeypatch.setattr(agent_console, "get_runtime", lambda: runtime)
    client = TestClient(app)
    payload = {**VALID_AGENT_PAYLOAD, "auto_start": True}
    resp = client.post("/agent/jobs", json=payload, headers=_headers())
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    assert FakeRuntime.started == [
        (
            job_id,
            VALID_AGENT_PAYLOAD["repo_path"],
            VALID_AGENT_PAYLOAD["spec_text"],
            VALID_AGENT_PAYLOAD["task_name"],
        ),
    ]


def test_agent_jobs_auto_start_repo_without_spec_rejected(
    agent_store: InMemoryAgentJobStore, agent_state: agent_console._ConsoleState,
) -> None:
    """Regression: the existing run-shape rule stays intact under the allowlist."""
    client = TestClient(app)
    resp = client.post(
        "/agent/jobs", json={"repo_path": "r", "auto_start": True}, headers=_headers(),
    )
    assert resp.status_code == 422
