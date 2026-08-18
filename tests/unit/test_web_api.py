"""Web UI read API tests (/api/v1/*) with fake stores and fake artifacts.

Coverage per endpoint: 200 happy path, 404 missing, explicit degraded
responses (MySQL down / Redis down / no eval report), and the auth
contract (401 without a key, 503 when no key is configured). No live
infrastructure is used: stores and artifact directories are faked.
"""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.routes.web as web_module
from api.server import app

API_KEY = "web-test-key"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECPROOF_API_KEY", API_KEY)


class FakeRedisRateLimit:
    """Backs enforce_rate_limit (patched on storage.redis.RedisStore)."""

    @property
    def client(self) -> FakeRedisRateLimit:
        return self

    def incr(self, key: str) -> int:
        return 1

    def expire(self, key: str, ttl: int) -> None:
        return None


class FakeMySQLStore:
    """In-memory stand-in for the route handlers (web_module.MySQLStore)."""

    rows: dict[str, dict[str, Any]] = {}
    summaries: dict[str, dict[str, Any]] = {}
    status_rows: list[dict[str, Any]] = []
    timeline_rows: list[dict[str, Any]] = []
    findings_rows: list[dict[str, Any]] = []
    contracts_rows: list[dict[str, Any]] = []
    registry_rows: list[dict[str, Any]] = []
    mysql_down = False

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        if FakeMySQLStore.mysql_down:
            raise ConnectionError("mysql down")
        return FakeMySQLStore.rows.get(job_id)

    def get_job_summary(self, job_id: str) -> dict[str, Any] | None:
        if FakeMySQLStore.mysql_down:
            raise ConnectionError("mysql down")
        return FakeMySQLStore.summaries.get(job_id)

    def list_recent_jobs(self, limit: int = 10) -> list[dict[str, Any]]:
        if FakeMySQLStore.mysql_down:
            raise ConnectionError("mysql down")
        return list(FakeMySQLStore.rows.values())[-limit:]

    def is_ready(self) -> bool:
        return not FakeMySQLStore.mysql_down

    @contextmanager
    def connection(self):  # noqa: ANN201 - pytest fake, mirrors MySQLStore
        if FakeMySQLStore.mysql_down:
            raise ConnectionError("mysql down")
        yield FakeConn()


class FakeCursor:
    def __init__(self) -> None:
        self.sql = ""
        self.params: list[Any] = []

    def execute(self, sql: str, params: list[Any] | None = None) -> None:
        self.sql = sql
        self.params = list(params or [])

    def fetchall(self) -> list[dict[str, Any]]:
        if self.sql.startswith("SELECT status"):
            return FakeMySQLStore.status_rows
        if self.sql.startswith("SELECT created_at"):
            return FakeMySQLStore.timeline_rows
        if self.sql.startswith("SELECT id, contract_id"):
            return FakeMySQLStore.findings_rows
        if self.sql.startswith("SELECT contract_id_str"):
            return FakeMySQLStore.contracts_rows
        if self.sql.startswith("SELECT id, repo_path"):
            rows = FakeMySQLStore.registry_rows
            if self.params and self.params[0] == "APPROVED":
                rows = [r for r in rows if r.get("status") == "APPROVED"]
            if len(self.params) > 1 and self.params[1]:
                rows = [r for r in rows if r.get("repo_path") == self.params[1]]
            return rows
        return []


class FakeConn:
    def cursor(self) -> FakeCursor:
        return FakeCursor()


class FakeRedisStream:
    """Backs web_module.RedisStore for stages/health."""

    events: list[dict[str, Any]] = []
    redis_down = False

    def xread_progress(
        self, job_id: str, from_id: str = "0", count: int = 1000
    ) -> list[dict[str, Any]]:
        if FakeRedisStream.redis_down:
            raise ConnectionError("redis down")
        return list(FakeRedisStream.events)

    def is_ready(self) -> bool:
        return not FakeRedisStream.redis_down


class FakeDepOk:
    """Any storage adapter that reports healthy."""

    def is_ready(self) -> bool:
        return True


class FakeDepDown:
    """Any storage adapter that reports unhealthy."""

    def is_ready(self) -> bool:
        return False


@pytest.fixture()
def fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeMySQLStore.rows = {}
    FakeMySQLStore.summaries = {}
    FakeMySQLStore.status_rows = []
    FakeMySQLStore.timeline_rows = []
    FakeMySQLStore.findings_rows = []
    FakeMySQLStore.contracts_rows = []
    FakeMySQLStore.registry_rows = []
    FakeMySQLStore.mysql_down = False
    FakeRedisStream.events = []
    FakeRedisStream.redis_down = False
    monkeypatch.setattr(web_module, "MySQLStore", FakeMySQLStore)
    monkeypatch.setattr(web_module, "RedisStore", FakeRedisStream)
    # Rate limiter imports RedisStore at call time from storage.redis.
    monkeypatch.setattr("storage.redis.RedisStore", FakeRedisRateLimit)


def _headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY}


JOB_ID = "12345678-0000-0000-0000-000000000001"


def _seed_job() -> None:
    FakeMySQLStore.rows[JOB_ID] = {"id": JOB_ID, "status": "VERIFIED"}


# ── Dashboard ──────────────────────────────────────────────────


def test_dashboard_aggregates_happy(fakes: None) -> None:
    FakeMySQLStore.status_rows = [
        {"status": "VERIFIED", "n": 3},
        {"status": "BLOCKED", "n": 1},
        {"status": "FAILED", "n": 1},
    ]
    FakeMySQLStore.timeline_rows = [
        {"created_at": datetime.now() - timedelta(hours=1), "status": "RUNNING"},
        {"created_at": datetime.now() - timedelta(hours=2), "status": "FAILED"},
    ]
    FakeMySQLStore.rows["a"] = {"id": "a", "status": "QUEUED"}
    client = TestClient(app)
    resp = client.get("/api/v1/dashboard", headers=_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["degraded"] is False
    assert body["jobs"]["total"] == 5
    assert body["jobs"]["by_status"] == {
        "VERIFIED": 3,
        "BLOCKED": 1,
        "FAILED": 1,
    }
    assert body["jobs"]["failure_rate"] == 0.2
    assert body["jobs"]["blocked_rate"] == 0.2
    assert len(body["timeline_24h"]) == 2
    assert body["timeline_24h"][0]["failed"] == 1
    assert body["cost"]["available"] is False
    assert body["tokens"]["total"] is None
    assert len(body["recent_jobs"]) == 1


def test_dashboard_degraded_when_mysql_down(fakes: None) -> None:
    FakeMySQLStore.mysql_down = True
    client = TestClient(app)
    resp = client.get("/api/v1/dashboard", headers=_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["degraded"] is True
    assert body["degraded_reasons"]
    assert body["jobs"]["total"] == 0
    assert body["jobs"]["failure_rate"] is None
    assert body["timeline_24h"] == []
    assert body["recent_jobs"] == []


def test_dashboard_requires_key(fakes: None) -> None:
    client = TestClient(app)
    assert client.get("/api/v1/dashboard").status_code == 401
    assert client.get("/api/v1/dashboard", headers={"X-API-Key": "wrong"}).status_code == 401


def test_dashboard_503_when_key_unconfigured(fakes: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECPROOF_API_KEY", "")
    client = TestClient(app)
    resp = client.get("/api/v1/dashboard")
    assert resp.status_code == 503


# ── Stages ─────────────────────────────────────────────────────


def test_stages_rollup_happy(fakes: None) -> None:
    _seed_job()
    FakeRedisStream.events = [
        {"id": "1-0", "node": "intake", "status": "completed",
         "percent": 10.0, "message": "ok", "at": "2026-08-18T00:00:00Z"},
        {"id": "1-1", "node": "collect_diff", "status": "running",
         "percent": 20.0, "message": "diffing", "at": "2026-08-18T00:00:01Z"},
        {"id": "1-2", "node": "collect_diff", "status": "completed",
         "percent": 30.0, "message": "done", "at": "2026-08-18T00:00:02Z"},
    ]
    client = TestClient(app)
    resp = client.get(f"/api/v1/jobs/{JOB_ID}/stages", headers=_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["degraded"] is False
    assert body["event_count"] == 3
    assert [s["node"] for s in body["stages"]] == ["intake", "collect_diff"]
    assert body["stages"][1]["status"] == "completed"
    assert body["stages"][1]["percent"] == 30.0


def test_stages_degraded_when_redis_down(fakes: None) -> None:
    _seed_job()
    FakeRedisStream.redis_down = True
    client = TestClient(app)
    resp = client.get(f"/api/v1/jobs/{JOB_ID}/stages", headers=_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["degraded"] is True
    assert body["stages"] == []
    assert "redis" in body["degraded_reason"]


def test_stages_404_unknown_job(fakes: None) -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/jobs/nope/stages", headers=_headers())
    assert resp.status_code == 404


# ── Findings ───────────────────────────────────────────────────


def test_findings_merge_summary_and_table(fakes: None) -> None:
    _seed_job()
    FakeMySQLStore.summaries[JOB_ID] = {
        "findings": [
            {"id": "f-1", "severity": "BLOCKER", "contract_id": "AUTH-01",
             "description": "auth removed", "confidence": 0.97},
            {"id": "f-2", "severity": "MAJOR", "contract_id": "TX-01",
             "description": "tx split", "confidence": 0.8},
        ],
    }
    FakeMySQLStore.findings_rows = [
        {"id": "f-1", "contract_id": "AUTH-01", "severity": "BLOCKER",
         "confidence": 0.97, "evidence_type": "differential_test",
         "impact_path": "{\"path\": \"UserController.java\"}",
         "capsule_path": "C:/caps/capsule-AUTH-01.zip", "created_at": None},
    ]
    client = TestClient(app)
    resp = client.get(f"/api/v1/jobs/{JOB_ID}/findings", headers=_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    merged = next(f for f in body["findings"] if f["id"] == "f-1")
    assert merged["description"] == "auth removed"
    assert merged["evidence_type"] == "differential_test"
    assert merged["capsule_path"] == "C:/caps/capsule-AUTH-01.zip"


def test_findings_empty_is_honest(fakes: None) -> None:
    _seed_job()
    client = TestClient(app)
    resp = client.get(f"/api/v1/jobs/{JOB_ID}/findings", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["findings"] == []


def test_findings_404_unknown_job(fakes: None) -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/jobs/nope/findings", headers=_headers())
    assert resp.status_code == 404


# ── Matrix ────────────────────────────────────────────────────


def test_matrix_rows_and_counts(fakes: None) -> None:
    _seed_job()
    FakeMySQLStore.contracts_rows = [
        {"contract_id_str": "AUTH-01", "requirement_text": "auth required",
         "checker_type": "java_source", "expected_behavior": "401",
         "result": "FAIL", "evidence_ref": "diff:UserController.java"},
        {"contract_id_str": "TX-01", "requirement_text": "tx atomic",
         "checker_type": "java_source", "expected_behavior": "rollback",
         "result": "PASS", "evidence_ref": "diff:OrderService.java"},
    ]
    FakeMySQLStore.summaries[JOB_ID] = {
        "contracts_total": 2, "matrix_passed": 1, "matrix_failed": 1,
        "matrix_unverified": 0,
    }
    client = TestClient(app)
    resp = client.get(f"/api/v1/jobs/{JOB_ID}/matrix", headers=_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["rows"]) == 2
    assert body["rows"][0]["contract_id_str"] == "AUTH-01"
    assert body["counts"]["failed"] == 1
    assert body["degraded"] is False


def test_matrix_empty_rows_still_returns_summary_counts(fakes: None) -> None:
    _seed_job()
    FakeMySQLStore.summaries[JOB_ID] = {"contracts_total": 4, "matrix_passed": 4}
    client = TestClient(app)
    resp = client.get(f"/api/v1/jobs/{JOB_ID}/matrix", headers=_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"] == []
    assert body["counts"]["total"] == 4


def test_matrix_404_unknown_job(fakes: None) -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/jobs/nope/matrix", headers=_headers())
    assert resp.status_code == 404


# ── Certificate ────────────────────────────────────────────────


def test_certificate_found(fakes: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_job()
    doc = {"subject": {"repository": "r", "commit_sha": "s"}, "result": "VERIFIED"}
    (tmp_path / f"merge-certificate-{JOB_ID[:8]}.json").write_text(
        json.dumps(doc), encoding="utf-8",
    )
    monkeypatch.setattr(web_module, "_reports_dir", lambda: tmp_path)
    client = TestClient(app)
    resp = client.get(f"/api/v1/jobs/{JOB_ID}/certificate", headers=_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["document"]["result"] == "VERIFIED"
    assert "signed_statement" not in body


def test_certificate_signed_statement_included(
    fakes: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_job()
    doc = {"result": "REJECTED"}
    (tmp_path / f"rejection-notice-{JOB_ID[:8]}.json").write_text(
        json.dumps(doc), encoding="utf-8",
    )
    (tmp_path / f"signed-{JOB_ID[:8]}-rejection-notice-{JOB_ID[:8]}.json").write_text(
        json.dumps({"payload": doc, "signatures": []}), encoding="utf-8",
    )
    monkeypatch.setattr(web_module, "_reports_dir", lambda: tmp_path)
    client = TestClient(app)
    resp = client.get(f"/api/v1/jobs/{JOB_ID}/certificate", headers=_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["document"]["result"] == "REJECTED"
    assert body["signed_statement"]["payload"]["result"] == "REJECTED"


def test_certificate_404_when_absent(
    fakes: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_job()
    monkeypatch.setattr(web_module, "_reports_dir", lambda: tmp_path)
    client = TestClient(app)
    resp = client.get(f"/api/v1/jobs/{JOB_ID}/certificate", headers=_headers())
    assert resp.status_code == 404
    assert "No merge-certificate" in resp.json()["detail"]


def test_certificate_404_unknown_job(fakes: None) -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/jobs/nope/certificate", headers=_headers())
    assert resp.status_code == 404


# ── Capsule download ───────────────────────────────────────────


def _make_zip(dir_path: Path, name: str) -> Path:
    zip_path = dir_path / name
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"finding_id": "f-1"}))
    return zip_path


def test_capsule_download_happy(
    fakes: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_job()
    zip_path = _make_zip(tmp_path, "capsule-AUTH-01.zip")
    FakeMySQLStore.summaries[JOB_ID] = {"capsules": [str(zip_path)]}
    monkeypatch.setattr(web_module, "_capsule_dirs", lambda: [tmp_path])
    client = TestClient(app)
    resp = client.get(f"/api/v1/jobs/{JOB_ID}/capsule", headers=_headers())
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert resp.headers["x-specproof-capsule"] == "capsule-AUTH-01.zip"
    assert resp.content[:2] == b"PK"


def test_capsule_by_name(fakes: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_job()
    _make_zip(tmp_path, "capsule-AUTH-01.zip")
    FakeMySQLStore.summaries[JOB_ID] = {"capsules": ["x/capsule-AUTH-01.zip"]}
    monkeypatch.setattr(web_module, "_capsule_dirs", lambda: [tmp_path])
    client = TestClient(app)
    resp = client.get(
        f"/api/v1/jobs/{JOB_ID}/capsule?name=capsule-AUTH-01.zip", headers=_headers(),
    )
    assert resp.status_code == 200


def test_capsule_404_when_absent(
    fakes: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_job()
    monkeypatch.setattr(web_module, "_capsule_dirs", lambda: [tmp_path])
    client = TestClient(app)
    resp = client.get(f"/api/v1/jobs/{JOB_ID}/capsule", headers=_headers())
    assert resp.status_code == 404
    assert "No capsule zip" in resp.json()["detail"]


def test_capsule_404_unknown_job(fakes: None) -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/jobs/nope/capsule", headers=_headers())
    assert resp.status_code == 404


# ── Contracts ──────────────────────────────────────────────────


def test_contracts_list_all(fakes: None) -> None:
    FakeMySQLStore.registry_rows = [
        {"id": "AUTH-01", "repo_path": "repo/a", "requirement_ref": "R1",
         "requirement": "req", "checker_type": "java_source",
         "expected_behavior": "beh", "source": "spec", "version": 1,
         "status": "APPROVED", "spec_digest": "d", "created_at": None,
         "updated_at": None},
        {"id": "TX-01", "repo_path": "repo/b", "requirement_ref": "R2",
         "requirement": "req2", "checker_type": "java_source",
         "expected_behavior": "beh2", "source": "spec", "version": 1,
         "status": "PROPOSED", "spec_digest": "d2", "created_at": None,
         "updated_at": None},
    ]
    client = TestClient(app)
    resp = client.get("/api/v1/contracts", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["count"] == 2
    assert resp.json()["degraded"] is False


def test_contracts_approved_filter(fakes: None) -> None:
    FakeMySQLStore.registry_rows = [
        {"id": "AUTH-01", "repo_path": "repo/a", "status": "APPROVED"},
        {"id": "TX-01", "repo_path": "repo/b", "status": "PROPOSED"},
    ]
    client = TestClient(app)
    resp = client.get("/api/v1/contracts?status=approved", headers=_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["contracts"][0]["id"] == "AUTH-01"


def test_contracts_422_bad_status(fakes: None) -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/contracts?status=bogus", headers=_headers())
    assert resp.status_code == 422


def test_contracts_503_mysql_down(fakes: None) -> None:
    FakeMySQLStore.mysql_down = True
    client = TestClient(app)
    resp = client.get("/api/v1/contracts", headers=_headers())
    assert resp.status_code == 503
    assert "MySQL unavailable" in resp.json()["detail"]


# ── Eval report ────────────────────────────────────────────────


def test_eval_latest_happy(fakes: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = {"total_cases": 100, "precision": 98.5, "recall": 97.0, "f1": 97.7,
              "cases": []}
    path = tmp_path / "eval-report.results.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(web_module, "_eval_report_path", lambda: path)
    client = TestClient(app)
    resp = client.get("/api/v1/eval/latest", headers=_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["report"]["precision"] == 98.5
    assert body["modified_at"]


def test_eval_latest_404_when_missing(
    fakes: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        web_module, "_eval_report_path", lambda: tmp_path / "does-not-exist.json",
    )
    client = TestClient(app)
    resp = client.get("/api/v1/eval/latest", headers=_headers())
    assert resp.status_code == 404
    assert "No evaluation report" in resp.json()["detail"]


# ── Health ─────────────────────────────────────────────────────


def _patch_deps(monkeypatch: pytest.MonkeyPatch, redis_ok: bool) -> None:
    monkeypatch.setattr(web_module, "MySQLStore", FakeMySQLStore)
    monkeypatch.setattr(web_module, "RedisStore", FakeRedisStream)
    monkeypatch.setattr("storage.mongodb.MongoDBStore", FakeDepOk)
    monkeypatch.setattr("storage.elasticsearch.ElasticsearchStore", FakeDepOk)
    monkeypatch.setattr("storage.rabbitmq.RabbitMQClient", FakeDepOk)
    monkeypatch.setattr("storage.minio.MinIOClient", FakeDepOk)
    FakeRedisStream.redis_down = not redis_ok
    FakeMySQLStore.mysql_down = False


def test_health_all_ok(fakes: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_deps(monkeypatch, redis_ok=True)
    client = TestClient(app)
    resp = client.get("/api/v1/health", headers=_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["degraded"] is False
    assert set(body["checks"]) == {
        "mysql", "mongodb", "elasticsearch", "redis", "rabbitmq", "minio",
    }
    assert body["checks"]["mysql"]["latency_ms"] >= 0


def test_health_degraded_when_redis_down(fakes: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_deps(monkeypatch, redis_ok=False)
    client = TestClient(app)
    resp = client.get("/api/v1/health", headers=_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["checks"]["redis"]["ok"] is False


def test_health_requires_key(fakes: None) -> None:
    client = TestClient(app)
    assert client.get("/api/v1/health").status_code == 401


# ── SPA smoke (only when the React build exists) ───────────────


def test_root_serves_spa_when_built() -> None:
    """GET / returns the built SPA HTML when apps/web/dist exists.

    The SPA catch-all is registered at app-import time, so this test
    verifies it in a fresh interpreter (the in-process app may have
    been imported before the build landed).
    """
    dist_index = PROJECT_ROOT / "apps" / "web" / "dist" / "index.html"
    if not dist_index.is_file():
        pytest.skip("SPA not built - run npm run build in apps/web")
    code = "\n".join([
        "from api.server import app",
        "from fastapi.testclient import TestClient",
        'r = TestClient(app).get("/")',
        "print(r.status_code)",
        'print("SPA_OK" if "root" in r.text else "SPA_MISSING")',
    ])
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "SPA_OK" in result.stdout


def test_spa_fallback_does_not_mask_api_404s() -> None:
    dist_index = PROJECT_ROOT / "apps" / "web" / "dist" / "index.html"
    if not dist_index.is_file():
        pytest.skip("SPA not built - run npm run build in apps/web")
    code = "\n".join([
        "from api.server import app",
        "from fastapi.testclient import TestClient",
        'r = TestClient(app).get("/api/v1/does-not-exist")',
        "print(r.status_code)",
    ])
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "404" in result.stdout
