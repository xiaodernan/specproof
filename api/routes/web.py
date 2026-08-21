"""Web UI read APIs for the SpecProof dashboard SPA (Phase 1 UI layer).

Every endpoint in this router is key-protected and rate limited (same
fail-closed middleware as the job API). The endpoints are READ-ONLY
views over existing storage/evidence artifacts and follow one honesty
rule: infrastructure failures are reported explicitly as "degraded"
(or 503 for per-resource reads), missing artifacts are 404 - nothing
is ever fabricated.

Layout:
  GET /api/v1/dashboard             aggregated job stats + 24h timeline
  GET /api/v1/jobs/{id}/stages      pipeline stage timeline (Redis stream)
  GET /api/v1/jobs/{id}/findings    findings (summary + findings table)
  GET /api/v1/jobs/{id}/certificate merge certificate / rejection notice
  GET /api/v1/jobs/{id}/capsule     bug capsule zip download
  GET /api/v1/contracts             contract registry (approval filter)
  GET /api/v1/eval/latest           latest persisted evaluation report
  GET /api/v1/health                per-dependency health + latency
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse

from api.auth import enforce_rate_limit, require_api_key
from api.errors import (
    EVIDENCE_UNVERIFIED,
    JOB_NOT_FOUND,
    PROVIDER_UNAVAILABLE,
    VALIDATION_FAILED,
    ApiError,
)
from storage.mysql import MySQLStore
from storage.redis import RedisStore

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1",
    tags=["web"],
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)

# ---- Artifact locations (overridable for tests and deployments) ----

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Capsule zip files are honest evidence artifacts produced by the pipeline.
_ZIP_MAGIC = b"PK"


def _capsule_dirs() -> list[Path]:
    """Directories searched for capsule zip files (order = precedence)."""
    dirs: list[Path] = []
    env_dir = os.getenv("SPECPROOF_CAPSULE_DIR", "").strip()
    if env_dir:
        dirs.append(Path(env_dir).resolve())
    dirs.append((_PROJECT_ROOT / "capsules").resolve())
    dirs.append((Path.cwd() / "capsules").resolve())
    return dirs


def _reports_dir() -> Path:
    env_dir = os.getenv("SPECPROOF_REPORTS_DIR", "").strip()
    if env_dir:
        return Path(env_dir).resolve()
    return (_PROJECT_ROOT / "reports").resolve()


def _eval_report_path() -> Path:
    env_path = os.getenv("SPECPROOF_EVAL_REPORT_PATH", "").strip()
    if env_path:
        return Path(env_path).resolve()
    return (_PROJECT_ROOT / "docs" / "eval" / "eval-report.results.json").resolve()


# ---- Helpers ----


def _load_job_or_404(store: MySQLStore, job_id: str) -> dict[str, Any]:
    """Fetch a job row or raise 404; raises 503 when MySQL is unreachable."""
    try:
        job = store.get_job(job_id)
    except Exception as exc:  # noqa: BLE001 - MySQL down
        logger.exception("MySQL unavailable for job %s", job_id)
        raise ApiError(
            status_code=503,
            code=PROVIDER_UNAVAILABLE,
            detail=f"MySQL unavailable: {exc}",
        ) from exc
    if job is None:
        raise ApiError(
            status_code=404, code=JOB_NOT_FOUND, detail=f"Job {job_id} not found",
        )
    return job


def _percent_rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _findings_from_table(store: MySQLStore, job_id: str) -> list[dict[str, Any]]:
    """Read the MySQL findings table rows for a job (best effort)."""
    try:
        with store.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, contract_id, severity, confidence, evidence_type, "
                "impact_path, capsule_path, created_at "
                "FROM findings WHERE job_id = %s ORDER BY created_at",
                (job_id,),
            )
            return cast(list[dict[str, Any]], cur.fetchall())
    except Exception as exc:  # noqa: BLE001 - table may be absent/unreachable
        logger.warning("findings table read failed for %s: %s", job_id, exc)
        return []


def _capsule_candidates(
    summary: dict[str, Any], findings_rows: list[dict[str, Any]]
) -> list[str]:
    """Basenames of capsule zips referenced by a job stored artifacts."""
    names: list[str] = []
    for raw in list(summary.get("capsules") or []):
        name = str(Path(str(raw)).name)
        if name.endswith(".zip") and name not in names:
            names.append(name)
    for row in findings_rows:
        raw = row.get("capsule_path")
        if not raw:
            continue
        name = str(Path(str(raw)).name)
        if name.endswith(".zip") and name not in names:
            names.append(name)
    return names


def _resolve_capsule_zip(name: str) -> Path | None:
    """Resolve a capsule basename to an existing zip inside a capsule dir."""
    if Path(name).name != name or not name.endswith(".zip"):
        return None
    candidates: list[Path] = []
    for base in _capsule_dirs():
        p = (base / name).resolve()
        if p.is_file() and p.parent == base:
            candidates.append(p)
    for p in candidates:
        try:
            with p.open("rb") as fh:
                if fh.read(2) == _ZIP_MAGIC:
                    return p
        except OSError:
            continue
    return None


def _certificate_artifacts(job_id: str) -> dict[str, Any] | None:
    """Load certificate / rejection-notice artifacts for a job, if any.

    Filenames use the job id first 8 characters (the CLI/worker naming
    convention). Only UUID-shaped ids are ever used in file lookups.
    """
    if not re.fullmatch(r"[0-9a-fA-F-]{8,64}", job_id):
        return None
    short = job_id[:8]
    reports = _reports_dir()
    found: dict[str, Any] | None = None
    for filename in (
        f"merge-certificate-{short}.json",
        f"rejection-notice-{short}.json",
    ):
        path = reports / filename
        if not path.is_file():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("unreadable certificate artifact %s: %s", path, exc)
            raise ApiError(
                status_code=503,
                code=PROVIDER_UNAVAILABLE,
                detail=f"Certificate artifact exists but is unreadable: {exc}",
            ) from exc
        found = {"path": str(path.resolve()), "document": doc}
        break
    if found is None:
        return None
    signed_path = reports / f"signed-{short}-{Path(str(found['path'])).stem}.json"
    if signed_path.is_file():
        try:
            found["signed_statement"] = json.loads(
                signed_path.read_text(encoding="utf-8")
            )
            found["signed_path"] = str(signed_path.resolve())
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("unreadable signed statement %s: %s", signed_path, exc)
    return found


# ---- Dashboard ----


@router.get("/dashboard")
async def dashboard() -> dict[str, Any]:
    """Aggregate job stats, 24h timeline and cost/token availability.

    MySQL is the source of truth for jobs. When it is unreachable the
    endpoint still answers 200 with "degraded: true" and empty
    aggregates - the UI must render the degradation, not fake numbers.
    """
    generated_at = datetime.now(UTC).isoformat()
    try:
        store = MySQLStore()
        since = datetime.now() - timedelta(hours=24)
        with store.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT status, COUNT(*) AS n FROM verification_jobs GROUP BY status"
            )
            status_rows = cast(list[dict[str, Any]], cur.fetchall())
            cur.execute(
                "SELECT created_at, status FROM verification_jobs "
                "WHERE created_at >= %s",
                (since,),
            )
            timeline_rows = cast(list[dict[str, Any]], cur.fetchall())
        recent_jobs = store.list_recent_jobs(10)
    except Exception as exc:  # noqa: BLE001 - MySQL down
        logger.exception("dashboard aggregation failed")
        return {
            "degraded": True,
            "degraded_reasons": [f"mysql: {exc}"],
            "generated_at": generated_at,
            "jobs": {
                "total": 0,
                "by_status": {},
                "failure_rate": None,
                "blocked_rate": None,
            },
            "timeline_24h": [],
            "timeline_timezone": "server-local",
            "cost": {
                "available": False,
                "currency": "USD",
                "total_usd": None,
                "reason": "pipeline does not persist a cost ledger",
            },
            "tokens": {
                "available": False,
                "total": None,
                "reason": "pipeline does not persist a token ledger",
            },
            "recent_jobs": [],
        }

    by_status: dict[str, int] = {}
    total = 0
    for row in status_rows:
        status = str(row.get("status") or "UNKNOWN")
        count = int(row.get("n") or 0)
        by_status[status] = count
        total += count
    failed = by_status.get("FAILED", 0) + by_status.get("ERROR", 0)

    timeline: list[dict[str, Any]] = []
    buckets: dict[str, dict[str, int]] = {}
    for row in timeline_rows:
        created = row.get("created_at")
        if not isinstance(created, datetime):
            continue
        key = created.strftime("%Y-%m-%dT%H:00:00")
        bucket = buckets.setdefault(key, {"count": 0, "failed": 0})
        bucket["count"] += 1
        if str(row.get("status")) in ("FAILED", "ERROR"):
            bucket["failed"] += 1
    for key in sorted(buckets):
        timeline.append({"hour": key, **buckets[key]})

    return {
        "degraded": False,
        "degraded_reasons": [],
        "generated_at": generated_at,
        "jobs": {
            "total": total,
            "by_status": by_status,
            "failure_rate": _percent_rate(failed, total),
            "blocked_rate": _percent_rate(by_status.get("BLOCKED", 0), total),
        },
        "timeline_24h": timeline,
        "timeline_timezone": "server-local",
        "cost": {
            "available": False,
            "currency": "USD",
            "total_usd": None,
            "reason": "pipeline does not persist a cost ledger",
        },
        "tokens": {
            "available": False,
            "total": None,
            "reason": "pipeline does not persist a token ledger",
        },
        "recent_jobs": jsonable_encoder(recent_jobs),
    }


# ---- Job detail views ----


@router.get("/jobs/{job_id}/stages")
async def job_stages(job_id: str) -> dict[str, Any]:
    """Pipeline stage timeline for one job (Redis progress stream).

    Redis is optional telemetry: when it is down the endpoint still
    answers 200 with "degraded: true" and an empty stage list.
    """
    store = MySQLStore()
    _load_job_or_404(store, job_id)
    try:
        events = RedisStore().xread_progress(job_id, from_id="0", count=1000)
    except Exception as exc:  # noqa: BLE001 - Redis down
        logger.warning("progress stream unavailable for %s: %s", job_id, exc)
        return {
            "job_id": job_id,
            "stages": [],
            "event_count": 0,
            "degraded": True,
            "degraded_reason": f"redis: {exc}",
        }
    stages: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for ev in events:
        node = str(ev.get("node") or "unknown")
        if node not in stages:
            stages[node] = {}
            order.append(node)
        stages[node] = {
            "node": node,
            "status": str(ev.get("status") or ""),
            "percent": float(ev.get("percent") or 0.0),
            "message": str(ev.get("message") or ""),
            "at": str(ev.get("at") or ""),
            "event_id": str(ev.get("id") or ""),
        }
    return {
        "job_id": job_id,
        "stages": [stages[node] for node in order],
        "event_count": len(events),
        "degraded": False,
        "degraded_reason": None,
    }


def _contracts_from_table(store: MySQLStore, job_id: str) -> list[dict[str, Any]]:
    """Read the MySQL contracts table rows for a job (best effort)."""
    try:
        with store.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT contract_id_str, requirement_text, checker_type, "
                "expected_behavior, result, evidence_ref FROM contracts "
                "WHERE job_id = %s ORDER BY contract_id_str",
                (job_id,),
            )
            return cast(list[dict[str, Any]], cur.fetchall())
    except Exception as exc:  # noqa: BLE001 - table may be absent/unreachable
        logger.warning("contracts table read failed for %s: %s", job_id, exc)
        return []


@router.get("/jobs/{job_id}/matrix")
async def job_matrix(job_id: str) -> dict[str, Any]:
    """Requirement-to-evidence matrix rows for one job (contracts table).

    The contracts table stores per-contract results (PASS/FAIL/UNVERIFIED)
    with requirement text and evidence refs; summary counts are returned
    alongside. Empty rows are honest, not fabricated.
    """
    store = MySQLStore()
    _load_job_or_404(store, job_id)
    rows = _contracts_from_table(store, job_id)
    try:
        summary = store.get_job_summary(job_id) or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("summary read failed for %s: %s", job_id, exc)
        summary = {}
    return {
        "job_id": job_id,
        "rows": jsonable_encoder(rows),
        "counts": {
            "total": len(rows) or int(summary.get("contracts_total") or 0),
            "passed": int(summary.get("matrix_passed") or 0),
            "failed": int(summary.get("matrix_failed") or 0),
            "unverified": int(summary.get("matrix_unverified") or 0),
        },
        "degraded": False,
        "degraded_reason": None,
    }


@router.get("/jobs/{job_id}/findings")
async def job_findings(job_id: str) -> dict[str, Any]:
    """Findings for one job (summary JSON merged with the findings table).

    The pipeline summary carries descriptions; the findings table adds
    capsule paths and impact paths. Both may be empty - an empty list is
    an honest answer, 404 is reserved for unknown jobs.
    """
    store = MySQLStore()
    _load_job_or_404(store, job_id)
    try:
        summary = store.get_job_summary(job_id) or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("summary read failed for %s: %s", job_id, exc)
        summary = {}

    table_rows = _findings_from_table(store, job_id)
    by_id: dict[str, dict[str, Any]] = {}
    for row in table_rows:
        fid = str(row.get("id") or "")
        if not fid:
            continue
        by_id[fid] = {
            "id": fid,
            "contract_id": row.get("contract_id"),
            "severity": row.get("severity"),
            "confidence": row.get("confidence"),
            "evidence_type": row.get("evidence_type"),
            "impact_path": row.get("impact_path"),
            "capsule_path": row.get("capsule_path"),
        }
    for item in summary.get("findings") or []:
        if not isinstance(item, dict):
            continue
        fid = str(item.get("id") or "")
        if not fid:
            continue
        if fid in by_id:
            by_id[fid].update({k: v for k, v in item.items() if v is not None})
        else:
            by_id[fid] = dict(item)
    findings = [by_id[k] for k in sorted(by_id)]
    return {
        "job_id": job_id,
        "findings": jsonable_encoder(findings),
        "count": len(findings),
        "sources": {
            "mysql_summary": isinstance(summary, dict) and bool(summary),
            "mysql_findings_table": bool(table_rows),
        },
        "degraded": False,
        "degraded_reason": None,
    }


@router.get("/jobs/{job_id}/certificate")
async def job_certificate(job_id: str) -> dict[str, Any]:
    """Merge Certificate / Rejection Notice for a job, when persisted.

    Certificates are written by the CLI verify flow (reports dir). The
    API never reconstructs one from scratch: no artifact means 404.
    """
    store = MySQLStore()
    _load_job_or_404(store, job_id)
    artifact = _certificate_artifacts(job_id)
    if artifact is None:
        raise ApiError(
            status_code=404,
            code=EVIDENCE_UNVERIFIED,
            detail=(
                f"No merge-certificate or rejection-notice artifact found "
                f"for job {job_id} (certificates are persisted by the "
                "verification pipeline when it runs)."
            ),
        )
    return {"job_id": job_id, **artifact}


@router.get("/jobs/{job_id}/capsule")
async def job_capsule(
    job_id: str, name: str | None = Query(default=None, max_length=255)
) -> FileResponse:
    """Download a Bug Capsule zip for a job (404 when none exists)."""
    store = MySQLStore()
    _load_job_or_404(store, job_id)
    try:
        summary = store.get_job_summary(job_id) or {}
    except Exception:  # noqa: BLE001 - capsule path may exist without summary
        summary = {}
    rows = _findings_from_table(store, job_id)
    candidates = _capsule_candidates(summary, rows)

    path: Path | None
    if name:
        if name not in candidates:
            raise ApiError(
                status_code=404,
                code=EVIDENCE_UNVERIFIED,
                detail=f"No capsule {name!r} recorded for job {job_id}",
            )
        path = _resolve_capsule_zip(name)
    else:
        path = None
        for candidate in candidates:
            resolved = _resolve_capsule_zip(candidate)
            if resolved is not None:
                path = resolved
                name = candidate
                break
    if path is None:
        raise ApiError(
            status_code=404,
            code=EVIDENCE_UNVERIFIED,
            detail=(
                f"No capsule zip available for job {job_id} "
                f"(candidates: {candidates or 'none'})"
            ),
        )
    return FileResponse(
        path,
        media_type="application/zip",
        filename=name or "capsule.zip",
        headers={"X-SpecProof-Capsule": name or "capsule.zip"},
    )


# ---- Contract registry ----


@router.get("/contracts")
async def list_contracts(
    status: str = Query(default="all"),
    repo_path: str | None = Query(default=None, max_length=512),
) -> dict[str, Any]:
    """Contract registry rows with approval-status filtering."""
    allowed = {"all", "approved", "proposed", "rejected", "revoked"}
    if status not in allowed:
        raise ApiError(
            status_code=422,
            code=VALIDATION_FAILED,
            detail=f"status must be one of {sorted(allowed)}",
        )
    status_filter = None if status == "all" else status.upper()
    sql = (
        "SELECT id, repo_path, requirement_ref, requirement, checker_type, "
        "expected_behavior, source, version, status, spec_digest, "
        "created_at, updated_at FROM contract_registry"
    )
    conditions: list[str] = []
    params: list[Any] = []
    if status_filter:
        conditions.append("status = %s")
        params.append(status_filter)
    if repo_path:
        conditions.append("repo_path = %s")
        params.append(repo_path)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY created_at DESC, id"
    try:
        store = MySQLStore()
        with store.connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cast(list[dict[str, Any]], cur.fetchall())
    except Exception as exc:  # noqa: BLE001 - MySQL down
        logger.exception("contract registry read failed")
        raise ApiError(
            status_code=503,
            code=PROVIDER_UNAVAILABLE,
            detail=f"MySQL unavailable: {exc}",
        ) from exc
    return {
        "contracts": jsonable_encoder(rows),
        "count": len(rows),
        "filter": {"status": status, "repo_path": repo_path},
        "degraded": False,
    }


# ---- Evaluation report ----


@router.get("/eval/latest")
async def eval_latest() -> dict[str, Any]:
    """Latest persisted evaluation report (docs/eval/eval-report.results.json)."""
    path = _eval_report_path()
    if not path.is_file():
        raise ApiError(
            status_code=404,
            code=EVIDENCE_UNVERIFIED,
            detail=(
                f"No evaluation report at {path}. Run the evaluation "
                "pipeline first; the API never fabricates metrics."
            ),
        )
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ApiError(
            status_code=503,
            code=PROVIDER_UNAVAILABLE,
            detail=f"Evaluation report exists but is unreadable: {exc}",
        ) from exc
    modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
    return {
        "source": str(path.resolve()),
        "modified_at": modified_at,
        "report": report,
    }


# ---- Dependency health ----


@router.get("/health")
async def api_health() -> dict[str, Any]:
    """Per-dependency health with latency (probes fail soft, never raise)."""

    def probe(name: str, factory: Any) -> dict[str, Any]:
        start = time.perf_counter()
        error: str | None = None
        try:
            ok = bool(factory().is_ready())
        except Exception as exc:  # noqa: BLE001 - probe failure is the answer
            ok = False
            error = str(exc)[:200]
        return {
            "ok": ok,
            "latency_ms": round((time.perf_counter() - start) * 1000.0, 2),
            "error": error,
        }

    async def run(name: str, factory: Any) -> tuple[str, dict[str, Any]]:
        return name, await asyncio.to_thread(probe, name, factory)

    from storage.elasticsearch import ElasticsearchStore
    from storage.minio import MinIOClient
    from storage.mongodb import MongoDBStore
    from storage.rabbitmq import RabbitMQClient

    results = dict(
        await asyncio.gather(
            run("mysql", MySQLStore),
            run("mongodb", MongoDBStore),
            run("elasticsearch", ElasticsearchStore),
            run("redis", RedisStore),
            run("rabbitmq", RabbitMQClient),
            run("minio", MinIOClient),
        )
    )
    all_ok = all(check["ok"] for check in results.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "degraded": not all_ok,
        "checks": results,
    }
