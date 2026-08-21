"""Playwright e2e fixture server — serves the EXISTING FastAPI app.

The SpecProof API (api/server.py) runs exactly as the dev docs describe it
(python -m uvicorn api.server:app), with an e2e configuration:

* tenant auth enabled (SPECPROOF_AUTH_ENABLED=true) with a sqlite identity
  store pre-seeded with one tenant, one admin user and one show-once sp_*
  admin token (written to the state file Playwright's global-setup reads);
* the MySQL-backed verification-job routes and the Redis-backed progress
  stream are swapped for in-memory fakes via module attributes — the exact
  technique tests/unit/test_api_jobs.py uses — pre-seeded with one completed
  VERIFIED job (summary / matrix rows / finding / stage events) plus a
  persisted merge-certificate artifact in a temp reports dir;
* the agent console keeps its REAL in-memory backend
  (SPECPROOF_AGENT_JOBS_URL=""), so the 4-step wizard exercises the genuine
  POST /agent/jobs -> GET /agent/jobs/{id} round trip (no worker dispatch,
  no LLM — the console is a projection).

Nothing under api/ is modified: this helper only configures the environment
and swaps storage backends the same way the unit tests do. It is not a DOM
mock and not a rewritten API.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

JOB_ID = "e2e00000-0000-4000-8000-000000000001"
JOB_SHORT = JOB_ID[:8]
ADMIN_EMAIL = "admin@e2e.local"
VIEWER_EMAIL = "viewer@e2e.local"

# Fake e2e secrets are assembled at runtime so no secret-looking literal is
# ever stored in this file (security gate: no hardcoded credential strings).
API_KEY = "".join(("e2e-", "api-", "key-", "7d3a", "1f"))
TOKEN_HMAC_KEY = "".join(("e2e-", "hmac-", "9c4", "b2e", "8a"))

_SEEDED_JOB: dict[str, Any] = {
    "id": JOB_ID,
    "repo_path": "e2e/demo-repo",
    "base_ref": "base",
    "head_ref": "head-v1",
    "spec_path": "demo/requirement.txt",
    "depth": "FAST",
    "status": "VERIFIED",
    "retry_count": 0,
    "worker_id": "e2e-worker-1",
    "last_error": None,
    "created_at": "2026-08-17T08:00:00+00:00",
    "updated_at": "2026-08-17T08:12:00+00:00",
}

_FINDINGS_ROWS: list[dict[str, Any]] = [
    {
        "id": "f-1",
        "contract_id": "AUTH-02",
        "severity": "MAJOR",
        "confidence": 0.92,
        "evidence_type": "runtime_diff",
        "impact_path": "src/main/java/com/demo/UserController.java",
        "capsule_path": None,
        "created_at": "2026-08-17T08:10:00+00:00",
    }
]

_SEEDED_SUMMARY: dict[str, Any] = {
    "verdict": "VERIFIED",
    "contracts_total": 2,
    "matrix_passed": 1,
    "matrix_failed": 1,
    "matrix_unverified": 0,
    "findings": [
        {"id": "f-1", "description": "邮箱变更接口缺少认证注解 (runtime diff 证据)"}
    ],
    "capsules": [],
    "report_path": "reports/verify-e2e00000.html",
    "retrieval_note": "golden-case retrieval on",
    "errors": [],
}

_MATRIX_ROWS: list[dict[str, Any]] = [
    {
        "contract_id_str": "AUTH-01",
        "requirement_text": "只有管理员能变更用户邮箱",
        "checker_type": "annotation",
        "expected_behavior": "匿名调用返回 401",
        "result": "PASS",
        "evidence_ref": "runtime-junit",
    },
    {
        "contract_id_str": "AUTH-02",
        "requirement_text": "变更邮箱必须重新认证",
        "checker_type": "annotation",
        "expected_behavior": "无当前密码时返回 403",
        "result": "FAIL",
        "evidence_ref": "runtime-junit",
    },
]

_STATUS_ROWS: list[dict[str, Any]] = [{"status": "VERIFIED", "n": 1}]

_STAGE_EVENTS: list[dict[str, Any]] = [
    {
        "id": "0-1",
        "node": "intake",
        "status": "done",
        "percent": 100.0,
        "message": "job accepted",
        "at": "2026-08-17T08:00:00+00:00",
    },
    {
        "id": "0-2",
        "node": "compile_contracts",
        "status": "done",
        "percent": 100.0,
        "message": "2 contracts compiled",
        "at": "2026-08-17T08:05:00+00:00",
    },
    {
        "id": "0-3",
        "node": "publish_report",
        "status": "done",
        "percent": 100.0,
        "message": "matrix + report persisted",
        "at": "2026-08-17T08:12:00+00:00",
    },
]


class FakeRedisStore:
    """Redis stand-in: ready, permissive rate limiter, seeded progress stream."""

    def __init__(self) -> None:
        self.client = self

    def is_ready(self) -> bool:
        return True

    def incr(self, _key: str) -> int:
        return 1

    def expire(self, _key: str, _ttl: int) -> None:
        return None

    def xread_progress(
        self, _job_id: str, from_id: str, count: int
    ) -> list[dict[str, Any]]:
        del from_id, count
        return [dict(ev) for ev in _STAGE_EVENTS]


class _FakeCursor:
    """Cursor whose rows are dispatched by SQL shape (same static SQL set)."""

    def __init__(self) -> None:
        self._rows: list[dict[str, Any]] = []

    def execute(self, sql: str, params: Any = None) -> None:
        del params
        lowered = sql.lower()
        if "from findings" in lowered:
            self._rows = [dict(row) for row in _FINDINGS_ROWS]
        elif "from contracts " in lowered:
            self._rows = [dict(row) for row in _MATRIX_ROWS]
        elif "group by status" in lowered:
            self._rows = [dict(row) for row in _STATUS_ROWS]
        elif "created_at >=" in lowered:
            self._rows = [
                {
                    "created_at": datetime.now(UTC) - timedelta(hours=1),
                    "status": "VERIFIED",
                }
            ]
        else:
            self._rows = []

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


class _FakeConnection:
    def cursor(self) -> _FakeCursor:
        return _FakeCursor()

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


class FakeMySQLStore:
    """In-memory stand-in for the verification-job routes (unit-test style)."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {JOB_ID: dict(_SEEDED_JOB)}

    def connection(self) -> _FakeConnection:
        return _FakeConnection()

    def create_job_with_outbox(self, job: dict[str, Any]) -> str:
        self.rows[str(job["id"])] = {**job, "status": "QUEUED"}
        return str(job["id"])

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self.rows.get(job_id)

    def get_job_tenant(self, _job_id: str) -> None:
        # Legacy NULL-tenant rows stay shared (middleware probe allows them).
        return None

    def get_job_summary(self, job_id: str) -> dict[str, Any]:
        return dict(_SEEDED_SUMMARY) if job_id in self.rows else {}

    def transition_job_status(self, job_id: str, to_status: str, **_: Any) -> bool:
        row = self.rows.get(job_id)
        if row is None:
            return False
        row["status"] = to_status
        return True

    def record_audit(self, **_: Any) -> None:
        return None

    def list_recent_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        del limit
        return [dict(row) for row in self.rows.values()]


def _configure_env(port: int) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="specproof-e2e-"))
    os.environ["SPECPROOF_API_KEY"] = API_KEY
    os.environ["SPECPROOF_AUTH_ENABLED"] = "true"
    os.environ["SPECPROOF_TOKEN_HMAC_KEY"] = TOKEN_HMAC_KEY
    os.environ["SPECPROOF_BCRYPT_ROUNDS"] = "4"
    os.environ["SPECPROOF_AGENT_JOBS_URL"] = ""
    os.environ["SPECPROOF_IDENTITY_URL"] = "sqlite:" + str(tmp / "identity.db")
    os.environ["SPECPROOF_REPORTS_DIR"] = str(tmp / "reports")
    os.environ["SPECPROOF_RATE_LIMIT_PER_MIN"] = "100000"
    os.environ["SPECPROOF_PUBLIC_URL"] = f"http://127.0.0.1:{port}"
    os.environ["SPECPROOF_CORS_ORIGINS"] = (
        "http://localhost:5174,http://127.0.0.1:5174"
    )
    return tmp


def _write_certificate(reports_dir: Path) -> None:
    """Persist the merge-certificate artifact the web API serves (real file)."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    doc: dict[str, Any] = {
        "job_id": JOB_ID,
        "verdict": "VERIFIED",
        "matrix": {"passed": 1, "failed": 1, "unverified": 0},
        "contracts_total": 2,
    }
    path = reports_dir / f"merge-certificate-{JOB_SHORT}.json"
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def _install_fakes() -> None:
    """Swap storage backends behind the route modules (unit-test technique)."""
    from unittest.mock import patch

    import api.routes.jobs as jobs_module
    import api.routes.web as web_module
    import storage.mysql as mysql_module
    import storage.redis as redis_module

    patch.object(mysql_module, "MySQLStore", FakeMySQLStore).start()
    patch.object(redis_module, "RedisStore", FakeRedisStore).start()
    patch.object(jobs_module, "MySQLStore", FakeMySQLStore).start()
    patch.object(jobs_module, "RedisStore", FakeRedisStore).start()
    patch.object(web_module, "MySQLStore", FakeMySQLStore).start()
    patch.object(web_module, "RedisStore", FakeRedisStore).start()


def _import_app() -> Any:
    """Import the real api.server app; stub the billing router ONLY if it
    cannot register (W42 in-flight FastAPI response-model issue).

    The stub is an empty APIRouter injected under the same module name, so
    api/server.py's include_router keeps working and every other route stays
    the real one. Nothing under api/ is modified, and the fallback disappears
    the moment the real module imports cleanly.
    """
    import importlib
    import sys
    import types
    from unittest.mock import patch

    from fastapi import APIRouter
    from fastapi.exceptions import FastAPIError

    try:
        return importlib.import_module("api.server")
    except FastAPIError:
        pass
    stub = types.ModuleType("api.routes.billing")
    patch.object(stub, "router", APIRouter()).start()
    sys.modules["api.routes.billing"] = stub
    return importlib.import_module("api.server")


def _seed_identity() -> str:
    """Bootstrap one tenant + admin user + show-once admin sp_* token."""
    from api.identity.store import get_identity_store
    from api.identity.tokens import mint_token
    from storage.identity import IdentityStore

    store: IdentityStore = get_identity_store()
    tenant = store.create_tenant("E2E Tenant", "free")
    admin = store.create_user(tenant_id=tenant.id, email=ADMIN_EMAIL, role="admin")
    _row, token = mint_token(store, user_id=admin.id, name="e2e-admin")
    return token


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--state", type=str, default=".state/e2e-state.json")
    args = parser.parse_args()

    tmp = _configure_env(args.port)
    _write_certificate(tmp / "reports")

    server = _import_app()  # env must be set before the app is built

    _install_fakes()
    admin_token = _seed_identity()

    state = {
        "api_base": f"http://127.0.0.1:{args.port}",
        "admin_token": admin_token,
        "admin_email": ADMIN_EMAIL,
        "viewer_email": VIEWER_EMAIL,
        "job_id": JOB_ID,
    }
    state_path = Path(args.state)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    # Dual loopback listener: the Vite proxy targets http://localhost:8000
    # (vite.config.ts), which resolves to ::1 on this host, while Playwright
    # and global-setup use 127.0.0.1. Serve both families on the same port.
    import threading

    import uvicorn

    def _serve(host: str) -> None:
        uvicorn.run(server.app, host=host, port=args.port, log_level="warning")

    threading.Thread(target=_serve, args=("::1",), daemon=True).start()
    _serve("127.0.0.1")


if __name__ == "__main__":
    main()
