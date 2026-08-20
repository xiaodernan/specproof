"""Data lifecycle CLI — export / delete / backup probe (DATA_LIFECYCLE §3/§4/§5).

Executable front for the documented manual steps, with the same honesty
contract: every step reports what it did with counts; MinIO objects are
LISTED for manual confirmation and never auto-deleted (evidence objects
are the audit trail); deletion is idempotent and requires --confirm.

Usage:
    python -m ops.data_lifecycle export-job JOB_ID --out DIR
    python -m ops.data_lifecycle delete-job JOB_ID --confirm
    python -m ops.data_lifecycle backup-probe
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def export_job(job_id: str, out_dir: Path) -> dict[str, Any]:
    """Export the job records + artifact pointers as JSON.

    MySQL job/findings/contracts rows, MongoDB differential runs and
    evidence packs (with MinIO object references listed, never downloaded)
    land in out_dir/<job_id>/export.json. Missing stores degrade the
    payload with an explicit reason — nothing is invented.
    """
    from storage.mongodb import MongoDBStore
    from storage.mysql import MySQLStore

    target = out_dir / job_id
    target.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"job_id": job_id, "degraded": []}

    try:
        mysql = MySQLStore()
        payload["mysql"] = _job_row_unscoped(mysql, job_id)
    except Exception as exc:  # noqa: BLE001
        payload["degraded"].append("mysql unavailable: " + str(exc))
        payload["mysql"] = None

    try:
        mongo = MongoDBStore()
        payload["mongo"] = {
            "differential_runs": mongo.get_differential_run(job_id),
            "evidence_packs": mongo.get_evidence_packs_for_job(job_id),
        }
    except Exception as exc:  # noqa: BLE001
        payload["degraded"].append("mongodb unavailable: " + str(exc))
        payload["mongo"] = None

    out = target / "export.json"
    out.write_text(
        json.dumps(payload, indent=2, default=str, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    payload["export_path"] = str(out)
    return payload


def _job_row_unscoped(mysql: Any, job_id: str) -> dict[str, Any] | None:
    """Job row + findings + contracts (explicit lifecycle read, unscoped)."""
    with mysql.connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM verification_jobs WHERE id = %s", (job_id,))
        job = cur.fetchone()
        cur.execute("SELECT * FROM findings WHERE job_id = %s", (job_id,))
        findings = cur.fetchall()
        cur.execute("SELECT * FROM contracts WHERE job_id = %s", (job_id,))
        contracts = cur.fetchall()
    return {
        "job": job,
        "findings": findings,
        "contracts": contracts,
    }


def delete_job(job_id: str) -> dict[str, Any]:
    """Delete one job in the documented order (DATA_LIFECYCLE §3).

    ES projection → MongoDB artifacts → MySQL records. MinIO objects are
    listed for manual confirmation and never auto-deleted. Every step is
    best-effort with an explicit result: a failure is reported, not hidden.
    """
    from storage.elasticsearch import ElasticsearchStore
    from storage.minio import MinIOClient
    from storage.mongodb import MongoDBStore
    from storage.mysql import MySQLStore

    report: dict[str, Any] = {"job_id": job_id, "steps": {}}
    try:
        es = ElasticsearchStore()
        deleted = es.delete_projection(job_id=job_id)
        report["steps"]["es_projection"] = {
            "ok": True, "deleted": _as_int(deleted),
        }
    except Exception as exc:  # noqa: BLE001
        report["steps"]["es_projection"] = {"ok": False, "error": str(exc)}
    try:
        mongo = MongoDBStore()
        counts = mongo.delete_job_artifacts(job_id)
        report["steps"]["mongo_artifacts"] = {"ok": True, **counts}
    except Exception as exc:  # noqa: BLE001
        report["steps"]["mongo_artifacts"] = {"ok": False, "error": str(exc)}
    try:
        mysql = MySQLStore()
        counts = mysql.delete_job_records(job_id)
        report["steps"]["mysql_records"] = {"ok": True, **counts}
    except Exception as exc:  # noqa: BLE001
        report["steps"]["mysql_records"] = {"ok": False, "error": str(exc)}
    try:
        minio = MinIOClient()
        objects = minio.list_job_objects(job_id)
        report["steps"]["minio_listed_not_deleted"] = {
            "ok": True,
            "objects": objects,
            "note": (
                "evidence objects listed for manual confirmation — "
                "never auto-deleted"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        report["steps"]["minio_listed_not_deleted"] = {
            "ok": False, "error": str(exc),
        }
    return report


def backup_probe() -> dict[str, Any]:
    """Capability probe: which external backup tools are available."""
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mysqldump": shutil.which("mysqldump") is not None,
        "mongodump": shutil.which("mongodump") is not None,
        "docker": shutil.which("docker") is not None,
        "note": (
            "backup = file-level snapshot per DATA_LIFECYCLE §5; this probe "
            "reports tool availability, the actual backup/restore drill "
            "(DRILLS 4) stays a documented manual operation"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ops.data_lifecycle")
    sub = parser.add_subparsers(dest="command", required=True)
    export_p = sub.add_parser("export-job")
    export_p.add_argument("job_id")
    export_p.add_argument("--out", type=Path, default=Path("lifecycle-export"))
    delete_p = sub.add_parser("delete-job")
    delete_p.add_argument("job_id")
    delete_p.add_argument("--confirm", action="store_true")
    sub.add_parser("backup-probe")
    args = parser.parse_args(argv)
    if args.command == "export-job":
        print(json.dumps(export_job(args.job_id, args.out), indent=2, default=str))
    elif args.command == "delete-job":
        if not args.confirm:
            print("refusing: delete-job requires --confirm (explicit deletion only)")
            return 2
        print(json.dumps(delete_job(args.job_id), indent=2, default=str))
    elif args.command == "backup-probe":
        print(json.dumps(backup_probe(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
