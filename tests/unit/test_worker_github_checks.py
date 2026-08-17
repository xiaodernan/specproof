"""Worker -> GitHub Check Run completion (best-effort, never raises)."""

import json

import agent.worker as worker_module

SUMMARY = {
    "verdict": "VERIFIED",
    "contracts_total": 4,
    "matrix_passed": 4,
    "matrix_failed": 0,
    "matrix_unverified": 0,
    "findings": [],
    "capsules": [],
}


class FakeCheckClient:
    updated: list[dict] = []

    def update_check_run(
        self, check_run_id, owner, repo, conclusion, title, summary,
        details_url="",
    ):
        FakeCheckClient.updated.append(
            {
                "check_run_id": check_run_id,
                "owner": owner,
                "repo": repo,
                "conclusion": conclusion,
                "title": title,
                "summary": summary,
            }
        )
        return {"id": check_run_id}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def close(self):
        pass


class FakeStore:
    def __init__(self, meta):
        self._meta = meta

    def get_job(self, job_id):
        if self._meta is None:
            return {}
        return {"github_check_json": json.dumps(self._meta)}


META = {
    "check_run_id": 777,
    "owner": "acme",
    "repo": "repo",
    "head_sha": "head-sha",
}


def _make_worker(meta):
    worker = worker_module.Worker.__new__(worker_module.Worker)
    worker.mysql = FakeStore(meta)
    return worker


def _fake_client_factory(monkeypatch):
    import integrations.github_checks as checks_module

    monkeypatch.setattr(
        checks_module, "github_app_client_from_env",
        lambda: FakeCheckClient(),
    )


def test_verified_publishes_success(monkeypatch):
    _fake_client_factory(monkeypatch)
    FakeCheckClient.updated = []
    worker = _make_worker(META)
    worker._maybe_publish_github_check("job-1", "VERIFIED", SUMMARY)
    assert len(FakeCheckClient.updated) == 1
    update = FakeCheckClient.updated[0]
    assert update["conclusion"] == "success"
    assert update["title"] == "SpecProof: VERIFIED"
    assert "**Verdict:** VERIFIED" in update["summary"]
    assert update["owner"] == "acme"
    assert update["check_run_id"] == 777


def test_blocked_publishes_failure(monkeypatch):
    _fake_client_factory(monkeypatch)
    FakeCheckClient.updated = []
    worker = _make_worker(META)
    worker._maybe_publish_github_check("job-1", "BLOCKED", SUMMARY)
    assert FakeCheckClient.updated[0]["conclusion"] == "failure"


def test_no_meta_skips(monkeypatch):
    _fake_client_factory(monkeypatch)
    FakeCheckClient.updated = []
    worker = _make_worker(None)
    worker._maybe_publish_github_check("job-1", "VERIFIED", SUMMARY)
    assert FakeCheckClient.updated == []


def test_app_not_configured_skips(monkeypatch):
    import integrations.github_checks as checks_module

    monkeypatch.setattr(
        checks_module, "github_app_client_from_env", lambda: None
    )
    FakeCheckClient.updated = []
    worker = _make_worker(META)
    worker._maybe_publish_github_check("job-1", "VERIFIED", SUMMARY)
    assert FakeCheckClient.updated == []


def test_api_error_never_raises(monkeypatch):
    import integrations.github_checks as checks_module

    class FailingClient(FakeCheckClient):
        def update_check_run(self, **kwargs):
            raise RuntimeError("github down")

    monkeypatch.setattr(
        checks_module, "github_app_client_from_env",
        lambda: FailingClient(),
    )
    worker = _make_worker(META)
    # Must not raise — an optional integration cannot flip a terminal job.
    worker._maybe_publish_github_check("job-1", "VERIFIED", SUMMARY)


def test_malformed_meta_never_raises(monkeypatch):
    _fake_client_factory(monkeypatch)
    worker = _make_worker({"check_run_id": "not-an-int"})
    worker._maybe_publish_github_check("job-1", "VERIFIED", SUMMARY)
