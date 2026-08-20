"""MCP tool implementations for SpecProof (honest degradation, never fabricated).

Every tool returns a plain JSON-serializable payload. There are exactly two
failure modes, both structured:

- ToolError          -> the server answers with isError=true (bad arguments,
                       missing artifacts, non-zero CLI exits, timeouts).
- degraded payload   -> infrastructure is unreachable but the answer is still
                       useful (degraded: true + explicit reason), mirroring
                       the honesty contract of api/routes/web.py. Missing data
                       is never invented and empty lists stay empty.

The tools deliberately call the CLI via subprocess (python -m
cli.specproof.main) instead of importing the pipeline: the MCP server must
stay isolated from in-flight changes to craft/agent internals, and a separate
process bounds resource usage. Artifacts written by the CLI (reports, plan
JSON) are read back from a per-call temp directory.

Dependency readers (contract registry, health probes) reuse the exact
semantics of the /api/v1 endpoints (same SQL, same probe order) but read the
storage adapters directly so the MCP server never needs FastAPI.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

_ALLOWED_CONTRACT_STATUSES = {"all", "approved", "proposed", "rejected", "revoked"}
_CAPSULE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MANIFEST_MAX_BYTES = 1_048_576  # 1 MiB cap for a single capsule manifest


class ToolError(Exception):
    """Structured tool failure - surfaces as an isError MCP result."""


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ToolError(f"{name} must be an integer, got {value!r}") from exc


def _required_str(arguments: dict[str, Any], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ToolError(f"missing required argument: {name!r} (string)")
    return value.strip()


def _optional_str(arguments: dict[str, Any], name: str) -> str | None:
    value = arguments.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ToolError(f"argument {name!r} must be a string, got {type(value).__name__}")
    return value or None


def _run_cli(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    """Run a SpecProof CLI invocation, mapping transport failures to ToolError."""
    try:
        return subprocess.run(  # noqa: S603 - argv built from validated constants/args
            cmd,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError(
            f"command timed out after {timeout}s (the run may still be in progress): "
            f"{' '.join(cmd)}"
        ) from exc
    except OSError as exc:
        raise ToolError(f"failed to start command {' '.join(cmd)}: {exc}") from exc


def _tail(text: str, limit: int = 2000) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return "..." + stripped[-limit:]


# ── specproof_verify ────────────────────────────────────────────────────────

_FINDING_RE = re.compile(
    r"^\s+\[(BLOCKER|MAJOR|MINOR)\]\s+(\S+)\s+\(confidence:\s*(\d+(?:\.\d+)?)%,\s*evidence:\s*(\S+)\)\s*$"
)
_FINDINGS_TOTAL_RE = re.compile(
    r"^Findings:\s+(\d+)\s+total\s+\((\d+)\s+BLOCKER,\s+(\d+)\s+MAJOR,\s+(\d+)\s+MINOR\)$"
)
_MATRIX_RE = re.compile(
    r"^Matrix:\s+(\d+)\s+rows\s+\|\s+\+(\d+)\s+passed\s+\|\s+-(\d+)\s+failed\s+\|\s+\?(\d+)\s+unverified$"
)


def parse_verify_stdout(stdout: str) -> dict[str, Any]:
    """Extract the verdict/findings summary from specproof verify output.

    The CLI prints stable markers (Job ID / Findings / Matrix / Bug Capsules /
    VERDICT / HTML Report / certificates). Unparseable output keeps the honest
    raw tail for the caller instead of inventing numbers.
    """
    summary: dict[str, Any] = {
        "job_id": None,
        "verdict": None,
        "contracts_compiled": None,
        "findings": [],
        "findings_summary": {"total": 0, "blocker": 0, "major": 0, "minor": 0},
        "matrix": {"rows": None, "passed": None, "failed": None, "unverified": None},
        "capsules": [],
        "errors": [],
        "html_report": None,
        "certificate": None,
    }
    current_finding: dict[str, Any] | None = None
    in_errors = False
    in_capsules = False
    for line in stdout.splitlines():
        finding = _FINDING_RE.match(line)
        if finding:
            current_finding = {
                "severity": finding.group(1),
                "contract_id": finding.group(2),
                "confidence": float(finding.group(3)) / 100.0,
                "evidence_type": finding.group(4),
                "description": "",
            }
            summary["findings"].append(current_finding)
            continue
        if current_finding is not None and line.startswith("       "):
            current_finding["description"] = (
                (current_finding["description"] + " " + line.strip()).strip()
            )
            continue
        if current_finding is not None and not line.startswith("       "):
            current_finding = None
        totals = _FINDINGS_TOTAL_RE.match(line)
        if totals:
            summary["findings_summary"] = {
                "total": int(totals.group(1)),
                "blocker": int(totals.group(2)),
                "major": int(totals.group(3)),
                "minor": int(totals.group(4)),
            }
            continue
        matrix = _MATRIX_RE.match(line)
        if matrix:
            summary["matrix"] = {
                "rows": int(matrix.group(1)),
                "passed": int(matrix.group(2)),
                "failed": int(matrix.group(3)),
                "unverified": int(matrix.group(4)),
            }
            continue
        if line.startswith("Errors ("):
            in_errors = True
            continue
        if in_errors:
            error = re.match(r"^\s+!\s+(.+)$", line)
            if error:
                summary["errors"].append(error.group(1))
                continue
            in_errors = False
        if re.match(r"^Bug Capsules:", line):
            in_capsules = True
            continue
        if in_capsules:
            capsule = re.match(r"^\s+(.+\.zip)$", line)
            if capsule:
                summary["capsules"].append(Path(capsule.group(1).strip()).name)
                continue
            in_capsules = False
        job = re.match(r"^Job ID:\s+(\S+)$", line)
        if job:
            summary["job_id"] = job.group(1)
            continue
        compiled = re.match(r"^Contracts compiled:\s+(\d+)$", line)
        if compiled:
            summary["contracts_compiled"] = int(compiled.group(1))
            continue
        verdict = re.match(r"^VERDICT:\s+(.+)$", line)
        if verdict:
            summary["verdict"] = verdict.group(1).strip()
            continue
        report = re.match(r"^HTML Report:\s+(.+)$", line)
        if report:
            summary["html_report"] = report.group(1).strip()
            continue
        certificate = re.match(r"^Merge Certificate:\s+(.+)$", line)
        if certificate:
            summary["certificate"] = certificate.group(1).strip()
            continue
        notice = re.match(r"^Rejection Notice written -> (.+)$", line)
        if notice:
            summary["certificate"] = notice.group(1).strip()
    return summary


def _tool_verify(arguments: dict[str, Any]) -> dict[str, Any]:
    """specproof verify over a temp spec file; summary parsed from CLI stdout."""
    repo = _required_str(arguments, "repo")
    base_ref = _required_str(arguments, "base_ref")
    head_ref = _required_str(arguments, "head_ref")
    spec_text = _required_str(arguments, "spec_text")
    repo_path = Path(repo).expanduser()
    if not repo_path.is_dir():
        raise ToolError(f"repository path does not exist: {repo_path}")
    timeout = _env_int("SPECPROOF_MCP_VERIFY_TIMEOUT", 1800)
    workdir = Path(tempfile.mkdtemp(prefix="specproof-mcp-verify-"))
    spec_file = workdir / "spec.txt"
    spec_file.write_text(spec_text, encoding="utf-8")
    output_dir = workdir / "reports"
    cmd = [
        sys.executable,
        "-m",
        "cli.specproof.main",
        "verify",
        "--repo",
        str(repo_path),
        "--base",
        base_ref,
        "--head",
        head_ref,
        "--spec",
        str(spec_file),
        "--output-dir",
        str(output_dir),
    ]
    proc = _run_cli(cmd, timeout)
    summary = parse_verify_stdout(proc.stdout)
    if proc.returncode != 0:
        raise ToolError(
            f"specproof verify exited with code {proc.returncode}: "
            f"{_tail(proc.stderr or proc.stdout)}"
        )
    if summary["verdict"] is None:
        raise ToolError(
            "specproof verify finished but its output was unparseable "
            f"(no VERDICT line found): {_tail(proc.stdout)}"
        )
    summary["output_dir"] = str(output_dir)
    return summary


# ── specproof_verify_job ──────────────────────────────────────────────────

_JOB_DEPTH_VALUES = ("FAST",)
_JOB_FIELD_LIMITS = {
    "repo_path": 1024,
    "base_ref": 255,
    "head_ref": 255,
    "spec_path": 1024,
}


def _tool_verify_job(arguments: dict[str, Any]) -> dict[str, Any]:
    """Create a QUEUED verification job through the job system (MySQL outbox).

    Same field allowlist + fail-closed discipline as POST /jobs: only
    repo_path/base_ref/head_ref/spec_path/depth are accepted; the job and
    its outbox event are persisted in ONE transaction and the worker
    executes it asynchronously (progress via SSE / job query endpoints).
    A MySQL failure degrades the payload — a job is never acknowledged
    when nothing was persisted.
    """
    repo_path = _required_str(arguments, "repo_path")
    base_ref = _required_str(arguments, "base_ref")
    head_ref = _required_str(arguments, "head_ref")
    spec_path = _required_str(arguments, "spec_path")
    depth = _optional_str(arguments, "depth") or "FAST"
    if depth not in _JOB_DEPTH_VALUES:
        raise ToolError(
            f"depth must be one of {sorted(_JOB_DEPTH_VALUES)}, got {depth!r}"
        )
    values = {
        "repo_path": repo_path,
        "base_ref": base_ref,
        "head_ref": head_ref,
        "spec_path": spec_path,
    }
    for field, limit in _JOB_FIELD_LIMITS.items():
        if len(values[field]) > limit:
            raise ToolError(
                f"{field} exceeds the documented {limit}-char limit"
            )
    repo = Path(repo_path).expanduser()
    if not repo.is_dir():
        raise ToolError(f"repository path does not exist: {repo_path}")
    spec = Path(spec_path).expanduser()
    if not spec.is_file():
        raise ToolError(f"spec file does not exist: {spec_path}")
    job = {
        "id": str(uuid.uuid4()),
        "repo_path": str(repo.resolve()),
        "base_ref": base_ref,
        "head_ref": head_ref,
        "spec_path": str(spec.resolve()),
        "depth": depth,
    }
    try:
        from storage.mysql import MySQLStore

        store = MySQLStore()
        store.create_job_with_outbox(job)
    except Exception as exc:  # noqa: BLE001 - MySQL down; degrade, never fabricate
        logger.warning("verify job creation failed: %s", exc)
        return {
            "degraded": True,
            "degraded_reason": f"job NOT accepted - persistence failed: {exc}",
            "job_id": None,
            "status": None,
        }
    return {
        "degraded": False,
        "job_id": job["id"],
        "status": "QUEUED",
        "depth": depth,
    }


# ── specproof_contracts_list ────────────────────────────────────────────────


def _tool_contracts_list(arguments: dict[str, Any]) -> dict[str, Any]:
    """Contract registry rows (same SQL/filters as GET /api/v1/contracts)."""
    status = _optional_str(arguments, "status") or "all"
    repo_path = _optional_str(arguments, "repo_path")
    if status not in _ALLOWED_CONTRACT_STATUSES:
        raise ToolError(
            f"status must be one of {sorted(_ALLOWED_CONTRACT_STATUSES)}, got {status!r}"
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
        from storage.mysql import MySQLStore

        store = MySQLStore()
        with store.connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001 - MySQL down; degrade, never fabricate
        logger.warning("contract registry read failed: %s", exc)
        return {
            "degraded": True,
            "degraded_reason": f"mysql unavailable: {exc}",
            "contracts": [],
            "count": 0,
            "filter": {"status": status, "repo_path": repo_path},
        }
    return {
        "degraded": False,
        "contracts": rows,
        "count": len(rows),
        "filter": {"status": status, "repo_path": repo_path},
    }


# ── specproof_eval_summary ──────────────────────────────────────────────────


def _eval_report_path() -> Path:
    env_path = os.getenv("SPECPROOF_EVAL_REPORT_PATH", "").strip()
    if env_path:
        return Path(env_path).resolve()
    return (_PROJECT_ROOT / "docs" / "eval" / "eval-report.results.json").resolve()


def _tool_eval_summary(arguments: dict[str, Any]) -> dict[str, Any]:
    """Latest persisted evaluation report summary (missing file = clear error)."""
    del arguments  # no parameters by design
    path = _eval_report_path()
    if not path.is_file():
        raise ToolError(
            f"No evaluation report at {path}. Run the evaluation pipeline first; "
            "the MCP tool never fabricates metrics."
        )
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolError(f"Evaluation report exists but is unreadable: {exc}") from exc
    if not isinstance(report, dict):
        raise ToolError("Evaluation report is not a JSON object")
    case_verdicts = dict(Counter(str(c.get("verdict")) for c in report.get("cases", [])))
    return {
        "source": str(path),
        "modified_at": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(path.stat().st_mtime)
        ),
        "total_cases": report.get("total_cases"),
        "should_detect": report.get("should_detect"),
        "detected": report.get("detected"),
        "false_positives": report.get("false_positives"),
        "precision": report.get("precision"),
        "recall": report.get("recall"),
        "f1": report.get("f1"),
        "case_verdicts": case_verdicts,
    }


# ── specproof_craft_plan ────────────────────────────────────────────────────


def _tool_craft_plan(arguments: dict[str, Any]) -> dict[str, Any]:
    """Deterministic (M1) craft plan via subprocess; plan.json read back."""
    spec_text = _required_str(arguments, "spec_text")
    repo = _optional_str(arguments, "repo") or str(Path.cwd())
    repo_path = Path(repo).expanduser()
    if not repo_path.is_dir():
        raise ToolError(f"repository path does not exist: {repo_path}")
    timeout = _env_int("SPECPROOF_MCP_CRAFT_TIMEOUT", 600)
    workdir = Path(tempfile.mkdtemp(prefix="specproof-mcp-craft-"))
    spec_file = workdir / "spec.txt"
    spec_file.write_text(spec_text, encoding="utf-8")
    out_dir = workdir / "plan"
    cmd = [
        sys.executable,
        "-m",
        "cli.specproof.main",
        "craft",
        "plan",
        str(spec_file),
        "--repo",
        str(repo_path),
        "--no-llm",
        "--output",
        str(out_dir),
    ]
    proc = _run_cli(cmd, timeout)
    if proc.returncode != 0:
        raise ToolError(
            f"craft plan exited with code {proc.returncode}: "
            f"{_tail(proc.stderr or proc.stdout)}"
        )
    plan_path = out_dir / "plan.json"
    if not plan_path.is_file():
        raise ToolError(
            "craft plan reported success but plan.json is missing "
            f"(expected at {plan_path})"
        )
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolError(f"craft plan.json is unreadable: {exc}") from exc
    steps = [
        {
            "id": step.get("id"),
            "kind": step.get("kind"),
            "intent": step.get("intent"),
            "target_files": step.get("target_files", []),
            "success_criteria": step.get("success_criteria"),
            "deps": step.get("deps", []),
        }
        for step in plan.get("steps", [])
        if isinstance(step, dict)
    ]
    return {
        "task_title": plan.get("task_title"),
        "mode": plan.get("mode"),
        "llm_fallback_reason": plan.get("llm_fallback_reason"),
        "risk_classification": plan.get("risk_classification"),
        "budget_alloc": plan.get("budget_alloc"),
        "steps": steps,
        "step_count": len(steps),
        "plan_path": str(plan_path),
    }


# ── specproof_health ────────────────────────────────────────────────────────


def _tool_health(arguments: dict[str, Any]) -> dict[str, Any]:
    """Per-dependency health probes (same semantics as GET /api/v1/health)."""
    del arguments  # no parameters by design

    def probe(name: str, factory: Callable[[], Any]) -> dict[str, Any]:
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

    from storage.elasticsearch import ElasticsearchStore
    from storage.minio import MinIOClient
    from storage.mongodb import MongoDBStore
    from storage.mysql import MySQLStore
    from storage.rabbitmq import RabbitMQClient
    from storage.redis import RedisStore

    factories: dict[str, Callable[[], Any]] = {
        "mysql": MySQLStore,
        "mongodb": MongoDBStore,
        "elasticsearch": ElasticsearchStore,
        "redis": RedisStore,
        "rabbitmq": RabbitMQClient,
        "minio": MinIOClient,
    }
    checks = {name: probe(name, factory) for name, factory in factories.items()}
    all_ok = all(check["ok"] for check in checks.values())
    return {"status": "ok" if all_ok else "degraded", "degraded": not all_ok, "checks": checks}


# ── specproof_replay_info ───────────────────────────────────────────────────


def _capsule_dirs() -> list[Path]:
    """Directories searched for capsule artifacts (order = precedence)."""
    dirs: list[Path] = []
    env_dir = os.getenv("SPECPROOF_CAPSULE_DIR", "").strip()
    if env_dir:
        dirs.append(Path(env_dir).resolve())
    dirs.append((_PROJECT_ROOT / "capsules").resolve())
    dirs.append((Path.cwd() / "capsules").resolve())
    return dirs


def _available_capsule_names() -> list[str]:
    names: set[str] = set()
    for base in _capsule_dirs():
        if not base.is_dir():
            continue
        for child in base.iterdir():
            if child.is_dir() and _CAPSULE_NAME_RE.fullmatch(child.name):
                names.add(child.name)
            elif child.is_file() and child.suffix == ".zip" and _CAPSULE_NAME_RE.fullmatch(
                child.stem
            ):
                names.add(child.stem)
    return sorted(names)


def _read_manifest_from(source: Path, *, zipped: bool) -> dict[str, Any]:
    if not zipped:
        raw = (source / "manifest.json").read_bytes()
    else:
        with zipfile.ZipFile(source) as archive:
            raw = archive.read("manifest.json")
    if len(raw) > _MANIFEST_MAX_BYTES:
        raise ToolError(f"capsule manifest at {source} exceeds the 1 MiB read cap")
    manifest = json.loads(raw.decode("utf-8"))
    if not isinstance(manifest, dict):
        raise ToolError(f"capsule manifest at {source} is not a JSON object")
    return manifest


def _tool_replay_info(arguments: dict[str, Any]) -> dict[str, Any]:
    """Capsule directory listing + manifest summary (path traversal guarded)."""
    name = _required_str(arguments, "capsule_name")
    if not _CAPSULE_NAME_RE.fullmatch(name) or ".." in name:
        raise ToolError(
            f"invalid capsule name {name!r}: expected [A-Za-z0-9][A-Za-z0-9._-]"
            "{0,127} with no path separators (path traversal rejected)"
        )
    for base in _capsule_dirs():
        extracted = (base / name).resolve()
        zipped = (base / f"{name}.zip").resolve()
        if extracted.is_dir() and (extracted / "manifest.json").is_file():
            if extracted.parent != base:
                continue  # resolve() must stay inside the capsule dir
            manifest = _read_manifest_from(extracted, zipped=False)
            listing = sorted(p.name for p in extracted.iterdir())[:50]
            return {
                "capsule_name": name,
                "found": True,
                "source": str(extracted),
                "kind": "directory",
                "listing": listing,
                "manifest": manifest,
            }
        if zipped.is_file() and zipped.parent == base:
            try:
                manifest = _read_manifest_from(zipped, zipped=True)
            except (KeyError, zipfile.BadZipFile) as exc:
                raise ToolError(
                    f"capsule zip {zipped} has no readable manifest: {exc}"
                ) from exc
            with zipfile.ZipFile(zipped) as archive:
                files = sorted(m for m in archive.namelist() if "/" not in m)
                dirs = sorted({m.split("/", 1)[0] for m in archive.namelist() if "/" in m})
            return {
                "capsule_name": name,
                "found": True,
                "source": str(zipped),
                "kind": "zip",
                "listing": (files + dirs)[:50],
                "manifest": manifest,
            }
    available = _available_capsule_names()
    dirs_text = ", ".join(str(d) for d in _capsule_dirs())
    raise ToolError(
        f"capsule {name!r} not found in capsule directories ({dirs_text}); "
        f"available capsules: {', '.join(available[:50]) or 'none'}"
    )


# ── Dispatch ────────────────────────────────────────────────────────────────

_HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "specproof_verify": _tool_verify,
    "specproof_contracts_list": _tool_contracts_list,
    "specproof_eval_summary": _tool_eval_summary,
    "specproof_craft_plan": _tool_craft_plan,
    "specproof_health": _tool_health,
    "specproof_replay_info": _tool_replay_info,
    "specproof_verify_job": _tool_verify_job,
}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "specproof_verify",
        "description": (
            "Run a SpecProof verification job over a base/head ref pair and return the "
            "honest verdict with a findings summary (severity, confidence, evidence type, "
            "capsule file names). Runs specproof verify in a subprocess; can take minutes "
            "to build and execute differential tests. Requires a local git repository and "
            "a requirement spec text."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Path to the git repository."},
                "base_ref": {
                    "type": "string",
                    "description": "Base ref (branch/tag/commit) to diff against.",
                },
                "head_ref": {
                    "type": "string",
                    "description": "Head ref (branch/tag/commit) containing the change.",
                },
                "spec_text": {
                    "type": "string",
                    "description": "Requirement specification text to compile contracts from.",
                },
            },
            "required": ["repo", "base_ref", "head_ref", "spec_text"],
        },
    },
    {
        "name": "specproof_verify_job",
        "description": (
            "Create a verification JOB through the job system (same fail-closed "
            "field allowlist as POST /jobs): the job plus its outbox event are "
            "persisted in one MySQL transaction, the worker executes it "
            "asynchronously, and progress is queryable via the job/SSE endpoints. "
            "Returns job_id + status=QUEUED; on persistence failure the result is "
            "degraded with an explicit reason - a job is never acknowledged when "
            "nothing was stored."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Path to the git repository (must exist locally).",
                },
                "base_ref": {"type": "string", "description": "Base ref (branch/tag/commit)."},
                "head_ref": {"type": "string", "description": "Head ref (branch/tag/commit)."},
                "spec_path": {
                    "type": "string",
                    "description": "Path to the requirement spec file (must exist locally).",
                },
                "depth": {
                    "type": "string",
                    "enum": ["FAST"],
                    "description": "Verification depth (only FAST is accepted today).",
                },
            },
            "required": ["repo_path", "base_ref", "head_ref", "spec_path"],
        },
    },
    {
        "name": "specproof_contracts_list",
        "description": (
            "List the contract registry (same semantics as GET /api/v1/contracts). "
            "Optionally filter by approval status (all/approved/proposed/rejected/revoked) "
            "and repo path. When MySQL is unreachable the result is degraded with an "
            "explicit reason - never fabricated."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Filter by repository path (exact match).",
                },
                "status": {
                    "type": "string",
                    "enum": ["all", "approved", "proposed", "rejected", "revoked"],
                    "description": "Approval status filter (default: all).",
                },
            },
        },
    },
    {
        "name": "specproof_eval_summary",
        "description": (
            "Read the latest persisted evaluation report summary "
            "(docs/eval/eval-report.results.json): precision/recall/F1 over the golden "
            "cases. Errors clearly when the report does not exist - metrics are never "
            "invented."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "specproof_craft_plan",
        "description": (
            "Generate a deterministic (M1) SpecCraft implementation plan for a requirement "
            "spec text via specproof craft plan --no-llm. Returns the plan steps "
            "(id/kind/intent/targets/mechanical success criteria), risk classification and "
            "budget allocation. LLM planning (M2) is deliberately not used by this tool."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "spec_text": {
                    "type": "string",
                    "description": "Task/requirement text to plan from.",
                },
                "repo": {
                    "type": "string",
                    "description": "Repository path (plan working directory; default: server cwd).",
                },
            },
            "required": ["spec_text"],
        },
    },
    {
        "name": "specproof_health",
        "description": (
            "Probe SpecProof dependencies (MySQL/MongoDB/Elasticsearch/Redis/RabbitMQ/MinIO) "
            "with per-dependency ok/latency/error - same semantics as GET /api/v1/health. "
            "Probes fail soft and report the real state."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "specproof_replay_info",
        "description": (
            "Inspect one bug capsule by name: directory listing plus manifest summary "
            "(finding id, severity, contract, evidence type, digest, blocker check). "
            "Capsule names are validated strictly to prevent path traversal."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "capsule_name": {
                    "type": "string",
                    "description": "Capsule name (e.g. capsule-COURT-AUTH-01), without .zip.",
                }
            },
            "required": ["capsule_name"],
        },
    },
]


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Dispatch one MCP tool call; raises ToolError for structured failures."""
    handler = _HANDLERS.get(name)
    if handler is None:
        raise ToolError(f"unknown tool: {name!r} (available: {', '.join(sorted(_HANDLERS))})")
    if not isinstance(arguments, dict):
        raise ToolError("tool arguments must be a JSON object")
    return handler(arguments)
