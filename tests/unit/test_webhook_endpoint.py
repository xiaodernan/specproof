"""P5 tests — GitHub webhook ingestion endpoint (signature + outbox)."""

import json

import pytest
from fastapi.testclient import TestClient

import api.routes.webhooks as webhooks_module
from api.server import app
from integrations.github import sign_payload

SECRET = "whsec_endpoint_test"


@pytest.fixture(autouse=True)
def webhook_env(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)


class FakeMySQL:
    jobs: list[dict] = []
    checks: list[tuple] = []

    def create_job_with_outbox(self, job):
        FakeMySQL.jobs.append(job)
        return job["id"]

    def set_job_github_check(self, job_id, check_meta):
        FakeMySQL.checks.append((job_id, check_meta))


@pytest.fixture()
def fake_mysql(monkeypatch):
    FakeMySQL.jobs = []
    FakeMySQL.checks = []
    webhooks_module._PROCESSED_EVENTS.clear()
    monkeypatch.setattr(webhooks_module, "MySQLStore", FakeMySQL)
    yield


class FakeCheckClient:
    created: list[dict] = []

    def create_check_run(
        self, owner, repo, head_sha, title, summary, details_url=""
    ):
        FakeCheckClient.created.append(
            {"owner": owner, "repo": repo, "head_sha": head_sha}
        )
        return {"id": 777}

    def close(self):
        pass


def _pr_body_with_repo_identity():
    body = _pr_event_body()
    body["repository"] = {
        "clone_url": "https://github.com/acme/repo.git",
        "name": "repo",
        "owner": {"login": "acme"},
    }
    return body


def _pr_event_body():
    return {
        "action": "opened",
        "pull_request": {
            "number": 42,
            "base": {"ref": "main", "sha": "base-sha"},
            "head": {"ref": "feature/x", "sha": "head-sha"},
        },
        "repository": {"clone_url": "https://github.com/acme/repo.git"},
    }


def _post(client: TestClient, body: dict, delivery: str = "d-1") -> tuple:
    raw = json.dumps(body).encode()
    resp = client.post(
        "/webhooks/github",
        content=raw,
        headers={
            "X-Hub-Signature-256": sign_payload(raw, SECRET),
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": delivery,
        },
    )
    return resp.status_code, resp.json()


def test_valid_event_creates_job(fake_mysql):
    client = TestClient(app)
    status, body = _post(client, _pr_event_body())
    assert status == 202
    assert body["action"] == "job_created"
    assert len(FakeMySQL.jobs) == 1
    assert FakeMySQL.jobs[0]["base_ref"] == "base-sha"


def test_invalid_signature_rejected(fake_mysql):
    client = TestClient(app)
    raw = json.dumps(_pr_event_body()).encode()
    resp = client.post(
        "/webhooks/github",
        content=raw,
        headers={
            "X-Hub-Signature-256": "sha256=" + "0" * 64,
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "d-1",
        },
    )
    assert resp.status_code == 401
    assert FakeMySQL.jobs == []


def test_missing_secret_fails_closed(fake_mysql, monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "")
    client = TestClient(app)
    status, _body = _post(client, _pr_event_body())
    assert status == 503
    assert FakeMySQL.jobs == []


def test_duplicate_delivery_idempotent(fake_mysql):
    client = TestClient(app)
    _post(client, _pr_event_body(), delivery="same-delivery")
    status, body = _post(client, _pr_event_body(), delivery="same-delivery")
    assert status == 202
    assert body["action"] == "duplicate_delivery"
    assert len(FakeMySQL.jobs) == 1


def test_irrelevant_event_ignored(fake_mysql):
    client = TestClient(app)
    raw = json.dumps({"action": "closed"}).encode()
    resp = client.post(
        "/webhooks/github",
        content=raw,
        headers={
            "X-Hub-Signature-256": sign_payload(raw, SECRET),
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "d-2",
        },
    )
    assert resp.status_code == 202
    assert resp.json()["action"] == "ignored"
    assert FakeMySQL.jobs == []


def test_check_run_created_when_app_configured(fake_mysql, monkeypatch):
    import integrations.github_checks as checks_module

    FakeCheckClient.created = []
    monkeypatch.setattr(
        checks_module, "github_app_client_from_env",
        lambda: FakeCheckClient(),
    )
    client = TestClient(app)
    status, body = _post(client, _pr_body_with_repo_identity())
    assert status == 202
    assert body["action"] == "job_created"
    assert FakeCheckClient.created == [
        {"owner": "acme", "repo": "repo", "head_sha": "head-sha"}
    ]
    job_id = FakeMySQL.jobs[0]["id"]
    assert FakeMySQL.checks == [
        (
            job_id,
            {
                "check_run_id": 777,
                "owner": "acme",
                "repo": "repo",
                "head_sha": "head-sha",
                "pull_number": 42,
            },
        )
    ]


def test_check_run_failure_does_not_affect_job(fake_mysql, monkeypatch):
    import integrations.github_checks as checks_module

    class FailingClient:
        def create_check_run(self, **kwargs):
            raise RuntimeError("github unreachable")

        def close(self):
            pass

    monkeypatch.setattr(
        checks_module, "github_app_client_from_env",
        lambda: FailingClient(),
    )
    client = TestClient(app)
    status, body = _post(client, _pr_body_with_repo_identity())
    assert status == 202
    assert body["action"] == "job_created"
    assert len(FakeMySQL.jobs) == 1
    assert FakeMySQL.checks == []
