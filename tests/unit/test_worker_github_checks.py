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
    reviews: list[dict] = []

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

    def publish_inline_findings(
        self, owner, repo, pull_number, commit_id, comments
    ):
        FakeCheckClient.reviews.append(
            {
                "owner": owner,
                "repo": repo,
                "pull_number": pull_number,
                "commit_id": commit_id,
                "comments": comments,
            }
        )
        return {"id": 9}

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


BLOCKED_SUMMARY = {
    "verdict": "BLOCKED",
    "contracts_total": 4,
    "matrix_passed": 3,
    "matrix_failed": 1,
    "matrix_unverified": 0,
    "findings": [
        {
            "id": "SRC-AUTH-ANNO",
            "severity": "MAJOR",
            "contract_id": "AUTH-01",
            "confidence": 0.85,
            "evidence_type": "java_source_diff",
            "type": "annotation_removed",
            "location": "src/UserController.java",
            "description": "Security annotation removed from method changeEmail()",
        }
    ],
    "capsules": [],
}

DIFF_STATE = {
    "diff_by_file": {
        "src/UserController.java": "\n".join([
            "diff --git a/src/UserController.java b/src/UserController.java",
            "index 111..222 100644",
            "--- a/src/UserController.java",
            "+++ b/src/UserController.java",
            "@@ -10,6 +10,5 @@ public class UserController {",
            "     private final UserService service;",
            " ",
            "     @PostMapping(\"/change-email\")",
            "-    @PreAuthorize(\"isAuthenticated()\")",
            "     public void changeEmail() {",
            "         service.changeEmail();",
            "     }",
            "",
        ])
    }
}


def test_blocked_with_pull_number_publishes_inline_review(monkeypatch):
    _fake_client_factory(monkeypatch)
    FakeCheckClient.reviews = []
    worker = _make_worker({**META, "pull_number": 42})
    worker._maybe_publish_github_check(
        "job-1", "BLOCKED", BLOCKED_SUMMARY, DIFF_STATE
    )
    assert len(FakeCheckClient.reviews) == 1
    review = FakeCheckClient.reviews[0]
    assert review["pull_number"] == 42
    assert review["commit_id"] == "head-sha"
    assert review["comments"][0]["path"] == "src/UserController.java"
    assert "AUTH-01" in review["comments"][0]["body"]


def test_blocked_without_pull_number_skips_review(monkeypatch):
    _fake_client_factory(monkeypatch)
    FakeCheckClient.reviews = []
    worker = _make_worker(META)  # no pull_number in META
    worker._maybe_publish_github_check(
        "job-1", "BLOCKED", BLOCKED_SUMMARY, DIFF_STATE
    )
    assert FakeCheckClient.reviews == []


def test_blocked_verified_verdict_skips_review(monkeypatch):
    _fake_client_factory(monkeypatch)
    FakeCheckClient.reviews = []
    worker = _make_worker({**META, "pull_number": 42})
    worker._maybe_publish_github_check(
        "job-1", "VERIFIED", BLOCKED_SUMMARY, DIFF_STATE
    )
    assert FakeCheckClient.reviews == []


def test_inline_review_failure_never_raises(monkeypatch):
    import integrations.github_checks as checks_module

    class FailingReviewClient(FakeCheckClient):
        def publish_inline_findings(self, **kwargs):
            raise RuntimeError("reviews api down")

    monkeypatch.setattr(
        checks_module, "github_app_client_from_env",
        lambda: FailingReviewClient(),
    )
    worker = _make_worker({**META, "pull_number": 42})
    worker._maybe_publish_github_check(
        "job-1", "BLOCKED", BLOCKED_SUMMARY, DIFF_STATE
    )
