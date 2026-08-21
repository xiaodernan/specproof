"""SpecCraft → SpecProof accept 强制闭环 (Agent 计划 M5 / 工业化阶段 7).

Follows docs/architecture/CRAFT_ACCEPT_DESIGN.md exactly:

  1. internal gates (craft/gates.py GatePipeline, five layered gates):
     any FAIL/error ⇒ STOP — no SpecProof call, rollback via
     'git reset --hard <base_sha>', no certificate;
  2. SpecProof independent verification: the same agent-graph pipeline the
    'specproof verify' CLI runs (compile contracts → Base/Head differential
    → Review Court), via the default verify_fn below;
  3. verdict VERIFIED ⇒ Merge Certificate (evidence/certificate.py) +
    lineage extension (evidence/lineage.py: contracts → findings →
    ChangeBundle digests) + Ed25519 signature (evidence/signing.py);
    anything else ⇒ rollback + rejection notice;
  4. idempotency key (job_id, head_sha, bundle digest): a repeat accept of
    the same head returns the existing certificate without re-running;
  5. every failure mode is fail-closed per the design's failure table —
    signing key missing ⇒ ERROR, never a silent unsigned accept.

The signing key comes from evidence/signing.py (SPECPROOF_SIGNING_KEY /
SPECPROOF_SIGNING_KEY_FILE); a missing key raises SigningError and the
accept fails closed. The signer and verify_fn parameters exist for
tests (fake signer / fake verification, no network, no live LLM, no Docker).
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from evidence.certificate import build_rejection_notice, issue_certificate
from evidence.lineage import build_lineage
from evidence.signing import SigningError, sign_json_document
from storage.agent_jobs import AgentJobStore, AgentJobStoreError

from .editor import classify_workspace_changes
from .gates import ExecRunner, GatePipeline, SecurityScanFn, SelfVerifyFn
from .schemas import ChangeBundle, sha256_hex

AcceptVerdict = Literal["VERIFIED", "BLOCKED", "ERROR"]

# verify_fn contract: (repo, base_sha, head_sha, spec_text) -> summary dict.
VerifyFn = Callable[[str, str, str, str], dict[str, Any]]
# signer contract: unsigned certificate document -> in-toto-style statement.
SignerFn = Callable[[dict[str, Any]], dict[str, Any]]

ACCEPT_RECORD_NAME = "accept.json"
CERTIFICATE_NAME = "merge-certificate.json"
REJECTION_NOTICE_NAME = "rejection-notice.json"


class AcceptError(RuntimeError):
    """The accept closure cannot even run (e.g. git unavailable)."""


@dataclass(frozen=True)
class AcceptResult:
    """Terminal outcome of one craft_accept closure run."""

    verdict: AcceptVerdict
    certificate_path: str | None
    findings: list[dict[str, Any]]
    gates_report: dict[str, Any] | None
    rolled_back: bool
    rejection_notice_path: str | None = None
    idempotent: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "certificate_path": self.certificate_path,
            "rejection_notice_path": self.rejection_notice_path,
            "findings": [dict(finding) for finding in self.findings],
            "gates_report": (
                dict(self.gates_report) if self.gates_report is not None else None
            ),
            "rolled_back": self.rolled_back,
            "idempotent": self.idempotent,
            "note": self.note,
        }


# -- bundle digest -------------------------------------------------------------


def bundle_digest(bundle: ChangeBundle) -> str:
    """Canonical sha256 over the bundle stable fields — the idempotency key."""
    payload: dict[str, Any] = {
        "task_id": bundle.task_id,
        "plan_version": bundle.plan_version,
        "changed_files": sorted(bundle.changed_files),
        "diff": bundle.diff,
        "test_results": [test.model_dump() for test in bundle.test_results],
        "dependency_changes": list(bundle.dependency_changes),
        "migration_notes": list(bundle.migration_notes),
        "risks": list(bundle.risks),
        "unverified": list(bundle.unverified),
        "rollback": bundle.rollback,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return sha256_hex(canonical)


def persist_accept_result(
    store: AgentJobStore, job_id: str, result: AcceptResult
) -> bool:
    """Post-hoc accept projection into the durable job store (W35.1).

    Calls storage.agent_jobs.attach_accept_result — the ONLY write a
    terminal job accepts: succeeded/failed only, first attach wins, repeat
    attaches are idempotent no-ops. Returns True iff the projection was
    attached; any AgentJobStoreError (non-terminal target, unknown job) is
    swallowed so the accept verdict itself is never changed by a
    projection failure — the certificate on disk and the printed verdict
    remain the authoritative record.
    """
    with suppress(AgentJobStoreError):
        store.attach_accept_result(job_id, result.to_dict())
        return True
    return False


def requirement_text_from_job_spec(spec_text: str) -> str:
    """Recover human-readable requirement text from a stored job spec.

    The W30 integration writes json.dumps(TaskSpec.to_dict()); legacy rows
    may carry plain text. Both shapes normalize to "title\nbody" here.
    """
    try:
        data = json.loads(spec_text)
    except json.JSONDecodeError:
        return spec_text
    if not isinstance(data, dict) or not isinstance(data.get("title"), str):
        return spec_text
    parts = [data["title"]]
    description = data.get("description")
    if isinstance(description, str) and description.strip():
        parts.append(description)
    return "\n".join(parts)


# -- git helpers ---------------------------------------------------------------


def _rollback_to(repo: Path, base_sha: str) -> bool:
    """git reset --hard <base_sha>; True iff the reset succeeded."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "reset", "--hard", base_sha],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception:  # noqa: BLE001 — any failure means no rollback happened
        return False
    return proc.returncode == 0


def _workspace_buckets(repo: Path, agent_paths: list[str]) -> dict[str, list[str]]:
    """classify_workspace_changes over the live git status (fail-closed)."""
    proc = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise AcceptError(
            f"git status 失败 (exit {proc.returncode}): 工作区无法分类, 拒绝 accept"
        )
    return classify_workspace_changes(proc.stdout or "", agent_paths=agent_paths)


# -- SpecProof verification (default verify_fn) ---------------------------------


def run_specproof_verification(
    repo: str | Path,
    base_ref: str,
    head_ref: str,
    spec_text: str,
    *,
    depth: str = "FAST",
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run the real SpecProof verification pipeline, the same way
    'specproof verify' does: build_phase0_graph + initial_state + invoke
    over all nodes (compile contracts → Base/Head differential → court),
    then map the final state to the same honest verdict block the CLI uses
    (mirrors cli/specproof/commands/verify.py — kept in sync manually).

    Temporary Base/Head worktrees created by the pipeline are always
    cleaned up, exactly like the CLI default (--keep-worktrees off).
    """
    from agent.graph import build_phase0_graph
    from agent.state import initial_state

    repo_path = Path(repo).resolve()
    with tempfile.TemporaryDirectory(prefix="specproof-accept-") as tmp_dir:
        spec_file = Path(tmp_dir) / "task.spec"
        spec_file.write_text(spec_text, encoding="utf-8")
        graph = build_phase0_graph()
        state = initial_state(
            repo_path=str(repo_path),
            base_ref=base_ref,
            head_ref=head_ref,
            spec_path=str(spec_file),
            depth=depth,
        )
        state["output_dir"] = str(
            Path(output_dir).resolve() if output_dir is not None else Path(tmp_dir) / "reports"
        )
        state["use_llm"] = True  # same default as 'specproof verify' (deterministic fallback)
        final_state: dict[str, Any] = {}
        try:
            final_state = graph.invoke(state)
        finally:
            for key in ("base_workspace", "head_workspace"):
                workspace = final_state.get(key, "")
                if not workspace:
                    continue
                with suppress(Exception):
                    subprocess.run(
                        ["git", "-C", str(repo_path), "worktree", "remove", "--force", workspace],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
    return _verification_summary(final_state)


def _verification_summary(final_state: Mapping[str, Any]) -> dict[str, Any]:
    """Honest verdict mapping of the pipeline final state (mirrors the CLI)."""
    findings = [dict(f) for f in (final_state.get("confirmed_findings") or [])]
    contracts = [dict(c) for c in (final_state.get("contracts") or [])]
    contract_results = [dict(r) for r in (final_state.get("contract_results") or [])]
    errors = [str(e) for e in (final_state.get("errors") or [])]
    matrix = final_state.get("matrix") or {}

    results_by_contract = {
        r.get("contract_id"): r for r in contract_results if isinstance(r, dict)
    }
    merged_contracts: list[dict[str, Any]] = []
    for contract in contracts:
        merged = dict(contract)
        result = results_by_contract.get(contract.get("id"), {})
        merged["result"] = result.get("result", "UNVERIFIED")
        merged["evidence_ref"] = result.get("evidence_ref")
        merged_contracts.append(merged)

    blocker_count = sum(1 for f in findings if f.get("severity") == "BLOCKER")
    if errors:
        verdict = "FAILED"
    elif blocker_count > 0:
        verdict = "BLOCKED"
    elif findings:
        verdict = "NEEDS REVIEW"
    elif matrix.get("unverified", 0) > 0 or not contracts:
        verdict = "NEEDS REVIEW (verification incomplete)"
    else:
        verdict = "VERIFIED"
    return {
        "verdict": verdict,
        "findings": findings,
        "contracts": merged_contracts,
        "contract_results": contract_results,
        "capsules": [str(c) for c in (final_state.get("capsules") or [])],
        "errors": errors,
        "matrix": dict(matrix),
        "report_path": str(final_state.get("report_path") or ""),
    }


# -- accept record (idempotency) -------------------------------------------------


def _record_path(out_dir: Path) -> Path:
    return out_dir / ACCEPT_RECORD_NAME


def _load_record(out_dir: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(_record_path(out_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _record_matches(record: Mapping[str, Any], job_id: str, head_sha: str, digest: str) -> bool:
    expected = {"job_id": job_id, "head_sha": head_sha, "bundle_digest": digest}
    return all(record.get(key) == value for key, value in expected.items())


def _write_record(
    out_dir: Path,
    *,
    job_id: str,
    head_sha: str,
    digest: str,
    verdict: AcceptVerdict,
    certificate_path: str | None,
    rejection_notice_path: str | None,
    gates_overall: str,
    gates_report: dict[str, Any],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": 1,
        "job_id": job_id,
        "head_sha": head_sha,
        "bundle_digest": digest,
        "verdict": verdict,
        "certificate_path": certificate_path,
        "rejection_notice_path": rejection_notice_path,
        "gates_overall": gates_overall,
        "gates_report": dict(gates_report),
        "issued_at": datetime.now(UTC).isoformat(),
    }
    _record_path(out_dir).write_text(json.dumps(record, indent=2), encoding="utf-8")


# -- finding helpers --------------------------------------------------------------


def _finding(kind: str, description: str, severity: str = "BLOCKER") -> dict[str, Any]:
    return {"kind": kind, "severity": severity, "description": description}


def _gate_findings(gates_report: Any) -> list[dict[str, Any]]:
    entries = gates_report.entries if hasattr(gates_report, "entries") else ()
    collected: list[dict[str, Any]] = []
    for entry in entries:
        if entry.status == "error":
            collected.append(
                _finding(
                    "gate_error",
                    f"门禁 {entry.gate} 执行异常 (error 为最差, 不伪造通过): {entry.note}",
                )
            )
        for item in entry.findings:
            collected.append(dict(item))
    if not collected:
        collected.append(_finding("gate_failed", "内部门禁 FAIL: " + gates_report.overall_note))
    return collected


def _write_rejection_notice(
    out_dir: Path,
    *,
    repo: Path,
    head_sha: str,
    spec_text: str,
    contracts: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    digest: str,
) -> str | None:
    reasons = [str(f.get("description", "")) for f in findings[:5]] or ["verification failed"]
    notice = build_rejection_notice(
        repository=str(repo),
        commit_sha=head_sha,
        requirements_text=spec_text,
        contracts=contracts,
        reasons=reasons,
        extension={"bundle_digest": digest},
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / REJECTION_NOTICE_NAME
    path.write_text(notice.to_json(), encoding="utf-8")
    return str(path)


# -- the closure -------------------------------------------------------------------


def craft_accept(
    bundle: ChangeBundle,
    spec_text: str,
    repo: str | Path,
    base_sha: str,
    head_sha: str,
    signer: SignerFn | None = None,
    verify_fn: VerifyFn | None = None,
    *,
    job_id: str | None = None,
    output_dir: str | Path | None = None,
    executor: ExecRunner | None = None,
    security_scan: SecurityScanFn | None = None,
    self_verify_fn: SelfVerifyFn | None = None,
    depth: str = "FAST",
) -> AcceptResult:
    """Run the full SpecCraft → SpecProof accept closure (design doc §1).

    Returns AcceptResult with verdict VERIFIED | BLOCKED | ERROR. Fail-closed
    throughout: gates FAIL stops before SpecProof, verify BLOCKED rolls back,
    signing unavailable is ERROR (never an unsigned accept).
    """
    job_id = job_id or bundle.task_id
    repo_path = Path(repo)
    out_dir = (
        Path(output_dir)
        if output_dir is not None
        else repo_path / ".specraft" / "jobs" / job_id / "accept"
    )
    digest = bundle_digest(bundle)

    # -- idempotency: same (job_id, head_sha, bundle digest) returns the
    #    existing certificate without re-running the closure.
    record = _load_record(out_dir)
    if record is not None and _record_matches(record, job_id, head_sha, digest):
        certificate_path = record.get("certificate_path")
        if record.get("verdict") == "VERIFIED" and isinstance(certificate_path, str):
            cert_file = Path(certificate_path)
            if cert_file.is_file():
                gates_record = record.get("gates_report")
                return AcceptResult(
                    "VERIFIED",
                    str(cert_file),
                    [],
                    dict(gates_record) if isinstance(gates_record, dict) else None,
                    False,
                    idempotent=True,
                    note="幂等命中: 既有证书 " + str(cert_file),
                )

    # -- workspace guard: user edits / conflicts are never reset away.
    try:
        buckets = _workspace_buckets(repo_path, list(bundle.changed_files))
    except AcceptError as exc:
        return AcceptResult(
            "BLOCKED",
            None,
            [_finding("workspace_unclassifiable", str(exc))],
            None,
            False,
            note=str(exc),
        )
    if buckets["user_changes"]:
        return AcceptResult(
            "BLOCKED",
            None,
            [
                _finding(
                    "user_changes",
                    "工作区存在非 agent 改动 (user_changes): "
                    + ", ".join(buckets["user_changes"])
                    + " — 拒绝 accept 且不回滚, 用户改动保护",
                )
            ],
            None,
            False,
            note="工作区脏 (非 agent 文件), 拒绝 accept",
        )
    if buckets["unknown"]:
        return AcceptResult(
            "BLOCKED",
            None,
            [
                _finding(
                    "unknown_changes",
                    "工作区存在无法归属的改动 (冲突/重命名/未跟踪): "
                    + ", ".join(buckets["unknown"])
                    + " — 拒绝 accept 且不回滚",
                )
            ],
            None,
            False,
            note="工作区存在无法归属的改动, 拒绝 accept",
        )

    # -- internal gates: any FAIL (or gate error) ⇒ STOP, rollback, no
    #    SpecProof call, no certificate (design §1 step 2 + failure table).
    pipeline = GatePipeline(
        repo_path,
        executor=executor,
        security_scan=security_scan,
        self_verify_fn=self_verify_fn,
    )
    gates_report = pipeline.run(bundle)
    gates_dict = gates_report.to_dict()
    if gates_report.overall in ("failed", "error"):
        verdict: AcceptVerdict = "BLOCKED" if gates_report.overall == "failed" else "ERROR"
        findings = _gate_findings(gates_report)
        rolled = _rollback_to(repo_path, base_sha)
        if not rolled:
            findings.append(
                _finding("rollback_failed", "git reset --hard " + base_sha + " 失败, 工作区未回滚")
            )
        _write_record(
            out_dir,
            job_id=job_id,
            head_sha=head_sha,
            digest=digest,
            verdict=verdict,
            certificate_path=None,
            rejection_notice_path=None,
            gates_overall=gates_report.overall,
            gates_report=gates_dict,
        )
        return AcceptResult(
            verdict,
            None,
            findings,
            gates_dict,
            rolled,
            note=(
                "内部门禁 FAIL: 不进入 SpecProof, 直接回滚"
                if gates_report.overall == "failed"
                else "内部门禁执行异常 (error 为最差): fail-closed 回滚"
            ),
        )

    # -- SpecProof independent verification (design §1 step 3).
    verifier: VerifyFn = verify_fn or (
        lambda repo_arg, base_arg, head_arg, spec_arg: run_specproof_verification(
            repo_arg, base_arg, head_arg, spec_arg, depth=depth,
            output_dir=out_dir / "specproof",
        )
    )
    try:
        verification = verifier(str(repo_path), base_sha, head_sha, spec_text)
    except Exception as exc:  # noqa: BLE001 — unavailable pipeline ⇒ BLOCKED, never silent
        rolled = _rollback_to(repo_path, base_sha)
        findings = [
            _finding(
                "verify_error",
                "SpecProof 验证管线不可用 (异常), 视为 BLOCKED 且记 error 分类: "
                + f"{type(exc).__name__}: {exc}",
            )
        ]
        if not rolled:
            findings.append(
                _finding("rollback_failed", "git reset --hard " + base_sha + " 失败, 工作区未回滚")
            )
        notice_path = _write_rejection_notice(
            out_dir,
            repo=repo_path,
            head_sha=head_sha,
            spec_text=spec_text,
            contracts=[],
            findings=findings,
            digest=digest,
        )
        _write_record(
            out_dir,
            job_id=job_id,
            head_sha=head_sha,
            digest=digest,
            verdict="BLOCKED",
            certificate_path=None,
            rejection_notice_path=notice_path,
            gates_overall=gates_report.overall,
            gates_report=gates_dict,
        )
        return AcceptResult(
            "BLOCKED", None, findings, gates_dict, rolled,
            rejection_notice_path=notice_path,
            note="verify 管线不可用 (异常), fail-closed 视为 BLOCKED",
        )
    if not isinstance(verification, dict):
        rolled = _rollback_to(repo_path, base_sha)
        findings = [
            _finding(
                "verify_invalid_result",
                "verify_fn 返回非法类型 " + type(verification).__name__ + " (期望 dict), "
                "视为 BLOCKED (不可静默放行)",
            )
        ]
        return AcceptResult(
            "BLOCKED", None, findings, gates_dict, rolled,
            note="verify 结果非法, fail-closed 视为 BLOCKED",
        )
    if verification.get("budget_exceeded"):
        rolled = _rollback_to(repo_path, base_sha)
        findings = [
            _finding(
                "budget_exceeded",
                "验收预算耗尽: 中止且诚实标注 budget_exceeded, 不留半截状态",
            )
        ]
        return AcceptResult(
            "BLOCKED", None, findings, gates_dict, rolled,
            note="预算耗尽, fail-closed 视为 BLOCKED",
        )

    verification_verdict = verification.get("verdict")
    if verification_verdict != "VERIFIED":
        findings = [dict(f) for f in (verification.get("findings") or [])]
        if verification_verdict == "FAILED":
            findings.append(
                _finding(
                    "verify_pipeline_failed",
                    "SpecProof 管线记录了错误 (errors 非空), 判定 FAILED → BLOCKED (记 error 分类)",
                )
            )
        if not findings:
            findings.append(
                _finding(
                    "verify_blocked",
                    "SpecProof 判定 " + repr(verification_verdict)
                    + " (UNVERIFIED 政策 fail-closed), 回滚",
                )
            )
        rolled = _rollback_to(repo_path, base_sha)
        if not rolled:
            findings.append(
                _finding("rollback_failed", "git reset --hard " + base_sha + " 失败, 工作区未回滚")
            )
        notice_path = _write_rejection_notice(
            out_dir,
            repo=repo_path,
            head_sha=head_sha,
            spec_text=spec_text,
            contracts=[dict(c) for c in (verification.get("contracts") or [])],
            findings=findings,
            digest=digest,
        )
        _write_record(
            out_dir,
            job_id=job_id,
            head_sha=head_sha,
            digest=digest,
            verdict="BLOCKED",
            certificate_path=None,
            rejection_notice_path=notice_path,
            gates_overall=gates_report.overall,
            gates_report=gates_dict,
        )
        return AcceptResult(
            "BLOCKED",
            None,
            findings,
            gates_dict,
            rolled,
            rejection_notice_path=notice_path,
            note="SpecProof 判定 " + repr(verification_verdict) + ", 回滚 + 拒绝通知",
        )

    # -- VERIFIED ⇒ Merge Certificate + lineage + Ed25519 signature.
    contracts = [dict(c) for c in (verification.get("contracts") or [])]
    findings = [dict(f) for f in (verification.get("findings") or [])]
    evidence_digests = [str(f["evidence_digest"]) for f in findings if f.get("evidence_digest")]
    file_digests = {
        rel: sha256_hex((repo_path / rel).read_bytes())
        for rel in sorted(bundle.changed_files)
        if (repo_path / rel).is_file()
    }
    evidence_digests.extend(sorted(file_digests.values()))

    certificate = issue_certificate(
        repository=str(repo_path),
        commit_sha=head_sha,
        requirements_text=spec_text,
        contracts=contracts,
        evidence_digests=evidence_digests,
        extension={},
    )
    if certificate is None:
        rolled = _rollback_to(repo_path, base_sha)
        findings.append(
            _finding(
                "certificate_conditions_unmet",
                "verify 声称 VERIFIED 但证书发行条件不满足 (契约未全部 PASS 或无契约), "
                "fail-closed 视为 BLOCKED",
            )
        )
        notice_path = _write_rejection_notice(
            out_dir,
            repo=repo_path,
            head_sha=head_sha,
            spec_text=spec_text,
            contracts=contracts,
            findings=findings,
            digest=digest,
        )
        return AcceptResult(
            "BLOCKED", None, findings, gates_dict, rolled,
            rejection_notice_path=notice_path,
            note="证书发行条件不满足, fail-closed 视为 BLOCKED",
        )

    # Lineage (GRAND_PLAN_V2 §18.1): contracts → findings → ChangeBundle
    # digests, rooted in the certificate. The certificate node content
    # digest deliberately excludes the extension (evidence/lineage.py), so
    # attaching lineage_root below cannot change the recorded root.
    lineage_context: dict[str, Any] = {
        "requirement_text": spec_text,
        "contracts": contracts,
        "contract_results": verification.get("contract_results") or [],
        "confirmed_findings": findings,
        "capsules": verification.get("capsules") or [],
        "certificate": certificate.to_dict(),
    }
    dag, lineage_root = build_lineage(lineage_context)
    certificate.extension = {
        "lineage_root": lineage_root,
        "lineage_nodes": len(dag.get("nodes", [])),
        "lineage_edges": len(dag.get("edges", [])),
        "bundle_digest": digest,
        "bundle_digests": file_digests,
    }
    document = certificate.to_dict()

    sign = signer or sign_json_document
    try:
        statement = sign(document)
    except SigningError as exc:
        return AcceptResult(
            "ERROR",
            None,
            [
                _finding(
                    "signing_unavailable",
                    "签名私钥缺失/不可用: " + str(exc) + " — 拒绝无签名 accept (fail-closed)",
                )
            ],
            gates_dict,
            False,
            note="签名不可用, accept 失败 (不允许无签名证书): " + str(exc),
        )
    except Exception as exc:  # noqa: BLE001 — any signer failure fails closed
        return AcceptResult(
            "ERROR",
            None,
            [
                _finding(
                    "signing_failed",
                    "签名执行失败 (" + type(exc).__name__ + ": " + str(exc)
                    + "), 拒绝无签名 accept",
                )
            ],
            gates_dict,
            False,
            note="签名执行失败, accept 失败 (fail-closed): " + str(exc),
        )
    if not isinstance(statement, dict) or not statement.get("signatures"):
        return AcceptResult(
            "ERROR",
            None,
            [
                _finding(
                    "signing_invalid_statement",
                    "signer 返回了无签名的文档, 拒绝无签名 accept (fail-closed)",
                )
            ],
            gates_dict,
            False,
            note="signer 未产出签名, accept 失败 (fail-closed)",
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    cert_path = out_dir / CERTIFICATE_NAME
    cert_path.write_text(json.dumps(statement, indent=2), encoding="utf-8")
    _write_record(
        out_dir,
        job_id=job_id,
        head_sha=head_sha,
        digest=digest,
        verdict="VERIFIED",
        certificate_path=str(cert_path),
        rejection_notice_path=None,
        gates_overall=gates_report.overall,
        gates_report=gates_dict,
    )
    return AcceptResult(
        "VERIFIED",
        str(cert_path),
        findings,
        gates_dict,
        False,
        note="Merge Certificate 已签发 (Ed25519 签名 + lineage 扩展)",
    )


__all__ = [
    "ACCEPT_RECORD_NAME",
    "CERTIFICATE_NAME",
    "REJECTION_NOTICE_NAME",
    "AcceptError",
    "AcceptResult",
    "AcceptVerdict",
    "SignerFn",
    "VerifyFn",
    "bundle_digest",
    "craft_accept",
    "persist_accept_result",
    "requirement_text_from_job_spec",
    "run_specproof_verification",
]
