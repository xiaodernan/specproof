"""craft/accept.py unit tests — the M5 SpecCraft → SpecProof closure.

Covers the full fail-closed contract from docs/architecture/
CRAFT_ACCEPT_DESIGN.md:
  - gates FAIL ⇒ STOP (no SpecProof call), rollback via git reset --hard,
    no certificate; gate errors are the worst of all (ERROR verdict);
  - verify BLOCKED / NEEDS REVIEW / FAILED ⇒ rollback + rejection notice;
  - verify raises ⇒ BLOCKED with an error-category finding (never silent);
  - VERIFIED ⇒ Merge Certificate written + lineage extension + a real
    Ed25519 signature (ephemeral key generated in-test via cryptography,
    verified with evidence.signing.verify_statement);
  - signing unavailable ⇒ ERROR, never a silent unsigned accept;
  - idempotency key (job_id, head_sha, bundle digest) ⇒ repeat accept
    returns the existing certificate without re-running the closure;
  - user workspace changes ⇒ reject WITHOUT rollback (user-work protection).

Everything is local/fake: scripted ExecRunner for the gates, fake security
scan, fake self-verify, fake verify_fn, ephemeral Ed25519 signer — no
network, no live LLM, no Docker. Only real git (a tmp repo) exercises the
rollback path.
"""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from craft.accept import (
    CERTIFICATE_NAME,
    REJECTION_NOTICE_NAME,
    AcceptResult,
    bundle_digest,
    craft_accept,
    requirement_text_from_job_spec,
)
from craft.executor import ExecResult
from craft.schemas import ChangeBundle
from evidence.signing import SigningError, verify_statement

SPEC_TEXT = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"

BASE_CALC = "def double(x):\n    return x / 2\n"
HEAD_CALC = "def double(x):\n    return x * 2\n"
WRONG_CALC = "def double(x):\n    return x * 3\n"


def make_bundle(task_id: str = "task-1", files: list[str] | None = None) -> ChangeBundle:
    return ChangeBundle(task_id=task_id, changed_files=files or ["calc.py"])


def make_repo(tmp_path: Path) -> tuple[Path, str, str]:
    """A real git repo: base commit (buggy calc), then a working-tree head.

    Returns (repo, base_sha, head_sha).
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "calc.py").write_text(BASE_CALC, encoding="utf-8")
    (repo / "test_calc.py").write_text(
        "from calc import double\n\n\ndef test_double():\n    assert double(4) == 8\n",
        encoding="utf-8",
    )
    (repo / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths = ['.']\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        [
            "git", "-c", "user.email=test@example.com",
            "-c", "user.name=specproof-test", "commit", "-qm", "base",
        ],
        cwd=repo,
        check=True,
    )
    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    (repo / "calc.py").write_text(HEAD_CALC, encoding="utf-8")
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    return repo, base_sha, head_sha


class FakeRunner:
    """Scripted ExecRunner for the gate pipeline (like test_craft_gates)."""

    def __init__(
        self, script: list[tuple[int, str]] | None = None, exc: Exception | None = None
    ) -> None:
        self.script = list(script or [])
        self.exc = exc
        self.calls: list[list[str]] = []

    def run(self, command: list[str], *, timeout: int | None = None) -> ExecResult:
        self.calls.append(list(command))
        if self.exc is not None:
            raise self.exc
        exit_code, tail = self.script.pop(0) if self.script else (0, "")
        return ExecResult(
            command=list(command),
            exit_code=exit_code,
            stdout=tail,
            stderr="",
            output_tail=tail,
            truncated=False,
            error="",
            mode="local",
        )


class FakeScanResult:
    def __init__(self) -> None:
        self.findings: list[Any] = []


def no_findings_scan(_workspace: str) -> FakeScanResult:
    return FakeScanResult()


def self_verify_passed(
    changed: list[str], workspace: Path, base_files: dict[str, str] | None = None
) -> dict[str, Any]:
    return {"status": "passed", "findings": [], "note": "fake self-verify passed"}


def verify_ok(repo: str, base_sha: str, head_sha: str, spec_text: str) -> dict[str, Any]:
    return {
        "verdict": "VERIFIED",
        "findings": [],
        "contracts": [
            {
                "id": "C-1",
                "checker_type": "static",
                "requirement": "double(4) == 8",
                "expected_behavior": "double 返回输入的两倍",
                "result": "PASS",
                "evidence_ref": "e1",
            }
        ],
        "contract_results": [{"contract_id": "C-1", "result": "PASS", "evidence_ref": "e1"}],
        "capsules": [],
        "errors": [],
        "matrix": {"rows": [{"result": "PASS"}], "passed": 1, "failed": 0, "unverified": 0},
        "report_path": "",
    }


def verify_blocked(repo: str, base_sha: str, head_sha: str, spec_text: str) -> dict[str, Any]:
    return {
        "verdict": "BLOCKED",
        "findings": [
            {
                "severity": "BLOCKER",
                "contract_id": "C-1",
                "description": "回归: double(4) == 12",
                "evidence_digest": hashlib.sha256(b"evidence-blocked").hexdigest(),
            }
        ],
        "contracts": [],
        "contract_results": [],
        "capsules": [],
        "errors": [],
        "matrix": {},
        "report_path": "",
    }


class FakeSigner:
    """Real Ed25519 signing with a fresh ephemeral key (cryptography)."""

    def __init__(self, *, fail: bool = False, unsigned: bool = False) -> None:
        self._key = Ed25519PrivateKey.generate()
        self.public_key_hex = self._key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        ).hex()
        self.fail = fail
        self.unsigned = unsigned
        self.calls = 0

    def __call__(self, document: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        if self.fail:
            raise SigningError("No signing key configured (fake)")
        if self.unsigned:
            return {"_type": "x", "payload": document, "signatures": []}
        pub = self._key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        )
        canonical = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        signature = self._key.sign(canonical)
        return {
            "_type": "https://specproof.dev/attestation/v0.1",
            "subject": [
                {
                    "name": "specproof-verification",
                    "digest": {"sha256": hashlib.sha256(canonical).hexdigest()},
                }
            ],
            "payload": document,
            "signatures": [
                {
                    "keyid": "sha256:" + hashlib.sha256(pub).hexdigest()[:32],
                    "sig": base64.b64encode(signature).decode(),
                }
            ],
        }


class RecordingVerify:
    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.calls = 0

    def __call__(self, repo: str, base_sha: str, head_sha: str, spec_text: str) -> dict[str, Any]:
        self.calls += 1
        return self.inner(repo, base_sha, head_sha, spec_text)


def clean_runner() -> FakeRunner:
    """Three passing commands: pytest (run_test), compileall (run_build), mypy (run_typecheck)."""
    return FakeRunner([(0, ""), (0, ""), (0, "")])


def run_accept(
    repo: Path,
    base_sha: str,
    head_sha: str,
    *,
    bundle: ChangeBundle | None = None,
    signer: Any = None,
    verify_fn: Any = None,
    runner: FakeRunner | None = None,
    job_id: str = "task-1",
    depth: str = "FAST",
) -> AcceptResult:
    return craft_accept(
        bundle or make_bundle(job_id),
        SPEC_TEXT,
        repo,
        base_sha,
        head_sha,
        signer=signer,
        verify_fn=verify_fn,
        job_id=job_id,
        executor=runner if runner is not None else clean_runner(),
        security_scan=no_findings_scan,
        self_verify_fn=self_verify_passed,
        depth=depth,
    )


# -- digest / spec normalization ------------------------------------------------


def test_bundle_digest_is_stable_and_sensitive() -> None:
    first = bundle_digest(make_bundle("t-1", ["calc.py"]))
    second = bundle_digest(make_bundle("t-1", ["calc.py"]))
    other_task = bundle_digest(make_bundle("t-2", ["calc.py"]))
    other_files = bundle_digest(make_bundle("t-1", ["calc.py", "extra.py"]))
    assert len(first) == 64
    assert first == second
    assert first != other_task
    assert first != other_files


def test_requirement_text_from_job_spec_handles_both_shapes() -> None:
    json_shape = json.dumps(
        {"title": "修复 double", "description": "验收: 测试通过", "acceptance_criteria": []},
        ensure_ascii=False,
    )
    assert requirement_text_from_job_spec(json_shape) == "修复 double\n验收: 测试通过"
    assert requirement_text_from_job_spec("纯文本 spec\n第二行") == "纯文本 spec\n第二行"
    assert requirement_text_from_job_spec("{not json") == "{not json"
    assert requirement_text_from_job_spec("[]") == "[]"


# -- gates FAIL ⇒ STOP + rollback + no certificate ------------------------------


def test_gates_fail_stops_before_specproof_and_rolls_back(tmp_path: Path) -> None:
    repo, base_sha, head_sha = make_repo(tmp_path)
    (repo / "calc.py").write_text(WRONG_CALC, encoding="utf-8")
    recorded_verify = RecordingVerify(verify_ok)
    result = run_accept(
        repo,
        base_sha,
        head_sha,
        verify_fn=recorded_verify,
        runner=FakeRunner([(1, "E assert 8 == 6")]),
    )
    assert result.verdict == "BLOCKED"
    assert result.rolled_back is True
    assert result.certificate_path is None
    assert recorded_verify.calls == 0  # design: no SpecProof call on gate FAIL
    assert (repo / "calc.py").read_text(encoding="utf-8") == BASE_CALC
    assert result.gates_report is not None and result.gates_report["overall"] == "failed"
    assert result.findings  # 分层原因在案
    out_dir = repo / ".specraft" / "jobs" / "task-1" / "accept"
    assert not (out_dir / CERTIFICATE_NAME).exists()
    record = json.loads((out_dir / "accept.json").read_text(encoding="utf-8"))
    assert record["verdict"] == "BLOCKED"
    assert record["bundle_digest"] == bundle_digest(make_bundle("task-1"))


def test_gate_error_is_worst_case_and_fails_closed(tmp_path: Path) -> None:
    repo, base_sha, head_sha = make_repo(tmp_path)
    recorded_verify = RecordingVerify(verify_ok)
    result = run_accept(
        repo,
        base_sha,
        head_sha,
        verify_fn=recorded_verify,
        runner=FakeRunner(exc=RuntimeError("sandbox exploded")),
    )
    assert result.verdict == "ERROR"
    assert result.rolled_back is True
    assert recorded_verify.calls == 0
    assert any(f["kind"] == "gate_error" for f in result.findings)


# -- verify BLOCKED ⇒ rollback + rejection notice -------------------------------


def test_verify_blocked_rolls_back_and_writes_rejection_notice(tmp_path: Path) -> None:
    repo, base_sha, head_sha = make_repo(tmp_path)
    result = run_accept(repo, base_sha, head_sha, verify_fn=verify_blocked)
    assert result.verdict == "BLOCKED"
    assert result.rolled_back is True
    assert result.certificate_path is None
    assert (repo / "calc.py").read_text(encoding="utf-8") == BASE_CALC
    assert result.findings[0]["severity"] == "BLOCKER"
    assert result.rejection_notice_path is not None
    out_dir = repo / ".specraft" / "jobs" / "task-1" / "accept"
    assert (out_dir / REJECTION_NOTICE_NAME).is_file()
    notice = json.loads((out_dir / REJECTION_NOTICE_NAME).read_text(encoding="utf-8"))
    assert notice["result"] == "REJECTED"
    assert notice["extension"]["bundle_digest"] == bundle_digest(make_bundle("task-1"))


def test_needs_review_is_fail_closed_blocked(tmp_path: Path) -> None:
    repo, base_sha, head_sha = make_repo(tmp_path)
    def verify_needs_review(
        repo: str, base_sha: str, head_sha: str, spec_text: str
    ) -> dict[str, Any]:
        return dict(verify_ok(repo, base_sha, head_sha, spec_text), verdict="NEEDS REVIEW")

    result = run_accept(repo, base_sha, head_sha, verify_fn=verify_needs_review)
    assert result.verdict == "BLOCKED"  # UNVERIFIED 政策 fail-closed
    assert result.rolled_back is True
    assert result.certificate_path is None
    assert any(f["kind"] == "verify_blocked" for f in result.findings)


def test_verify_raises_treated_as_blocked_with_error_category(tmp_path: Path) -> None:
    repo, base_sha, head_sha = make_repo(tmp_path)
    def explode(repo: str, base_sha: str, head_sha: str, spec_text: str) -> dict[str, Any]:
        raise RuntimeError("maven exploded")

    result = run_accept(repo, base_sha, head_sha, verify_fn=explode)
    assert result.verdict == "BLOCKED"  # 设计表: verify 不可用 ⇒ 视为 BLOCKED, 记 error 分类
    assert result.rolled_back is True
    assert result.certificate_path is None
    assert any(f["kind"] == "verify_error" for f in result.findings)
    assert result.rejection_notice_path is not None


def test_verify_failed_verdict_maps_to_blocked(tmp_path: Path) -> None:
    repo, base_sha, head_sha = make_repo(tmp_path)
    def verify_failed(repo: str, base_sha: str, head_sha: str, spec_text: str) -> dict[str, Any]:
        return {
            "verdict": "FAILED",
            "findings": [],
            "contracts": [],
            "contract_results": [],
            "capsules": [],
            "errors": ["pipeline error"],
            "matrix": {},
            "report_path": "",
        }

    result = run_accept(repo, base_sha, head_sha, verify_fn=verify_failed)
    assert result.verdict == "BLOCKED"
    assert any(f["kind"] == "verify_pipeline_failed" for f in result.findings)
    assert result.rolled_back is True


# -- VERIFIED ⇒ signed certificate + lineage ------------------------------------


def test_verified_writes_signed_certificate_with_lineage(tmp_path: Path) -> None:
    repo, base_sha, head_sha = make_repo(tmp_path)
    signer = FakeSigner()
    result = run_accept(repo, base_sha, head_sha, signer=signer, verify_fn=verify_ok)
    assert result.verdict == "VERIFIED"
    assert result.rolled_back is False
    assert result.certificate_path is not None
    assert (repo / "calc.py").read_text(encoding="utf-8") == HEAD_CALC  # 不回滚

    statement = json.loads(Path(result.certificate_path).read_text(encoding="utf-8"))
    # 真实验签: 用测试内生成的临时 Ed25519 公钥验证签名
    assert verify_statement(statement, signer.public_key_hex) is True
    payload = statement["payload"]
    assert payload["result"] == "VERIFIED"
    assert payload["subject"]["commit_sha"] == head_sha
    extension = payload["extension"]
    assert extension["lineage_root"]
    assert extension["lineage_nodes"] >= 1
    assert extension["lineage_edges"] >= 1
    assert extension["bundle_digest"] == bundle_digest(make_bundle("task-1"))
    # 证书绑定 accept 时工作树的真实字节 (含平台换行符), 而非理想化内容
    tree_digest = hashlib.sha256((repo / "calc.py").read_bytes()).hexdigest()
    assert extension["bundle_digests"]["calc.py"] == tree_digest
    # ChangeBundle 文件摘要已并入证书 evidence_digests (血缘可溯源)
    assert tree_digest in payload["evidence_digests"]


def test_certificate_conditions_unmet_fails_closed(tmp_path: Path) -> None:
    repo, base_sha, head_sha = make_repo(tmp_path)
    def verify_lying(repo: str, base_sha: str, head_sha: str, spec_text: str) -> dict[str, Any]:
        return dict(verify_ok(repo, base_sha, head_sha, spec_text), contracts=[])

    result = run_accept(repo, base_sha, head_sha, verify_fn=verify_lying)
    assert result.verdict == "BLOCKED"  # 证书发行条件不满足, 不可静默放行
    assert result.certificate_path is None
    assert any(f["kind"] == "certificate_conditions_unmet" for f in result.findings)


# -- signing fail-closed ---------------------------------------------------------


def test_signing_unavailable_is_error_not_unsigned_accept(tmp_path: Path) -> None:
    repo, base_sha, head_sha = make_repo(tmp_path)
    result = run_accept(repo, base_sha, head_sha, signer=FakeSigner(fail=True), verify_fn=verify_ok)
    assert result.verdict == "ERROR"  # 绝不降级为无签名 accept
    assert result.certificate_path is None
    assert any(f["kind"] == "signing_unavailable" for f in result.findings)
    out_dir = repo / ".specraft" / "jobs" / "task-1" / "accept"
    assert not (out_dir / CERTIFICATE_NAME).exists()


def test_signer_returning_unsigned_document_is_error(tmp_path: Path) -> None:
    repo, base_sha, head_sha = make_repo(tmp_path)
    result = run_accept(
        repo, base_sha, head_sha, signer=FakeSigner(unsigned=True), verify_fn=verify_ok
    )
    assert result.verdict == "ERROR"
    assert result.certificate_path is None
    assert any(f["kind"] == "signing_invalid_statement" for f in result.findings)


# -- idempotency ------------------------------------------------------------------


def test_idempotent_repeat_returns_same_certificate(tmp_path: Path) -> None:
    repo, base_sha, head_sha = make_repo(tmp_path)
    signer = FakeSigner()
    recorded_verify = RecordingVerify(verify_ok)
    first = run_accept(repo, base_sha, head_sha, signer=signer, verify_fn=recorded_verify)
    assert first.verdict == "VERIFIED" and first.idempotent is False
    second = run_accept(repo, base_sha, head_sha, signer=signer, verify_fn=recorded_verify)
    assert second.verdict == "VERIFIED"
    assert second.idempotent is True
    assert second.certificate_path == first.certificate_path
    assert recorded_verify.calls == 1  # 闭包没有重跑
    assert signer.calls == 1


# -- workspace guard ---------------------------------------------------------------


def test_user_workspace_changes_reject_without_rollback(tmp_path: Path) -> None:
    repo, base_sha, head_sha = make_repo(tmp_path)
    (repo / "scratch.py").write_text("user work", encoding="utf-8")
    subprocess.run(["git", "add", "scratch.py"], cwd=repo, check=True)
    subprocess.run(
        [
            "git", "-c", "user.email=test@example.com", "-c", "user.name=t",
            "commit", "-qm", "user file",
        ],
        cwd=repo,
        check=True,
    )
    (repo / "scratch.py").write_text("user work v2", encoding="utf-8")  # 用户并发改动
    recorded_verify = RecordingVerify(verify_ok)
    result = run_accept(repo, base_sha, head_sha, verify_fn=recorded_verify)
    assert result.verdict == "BLOCKED"
    assert result.rolled_back is False  # 用户改动保护: 绝不 reset --hard
    assert recorded_verify.calls == 0
    assert (repo / "scratch.py").read_text(encoding="utf-8") == "user work v2"
    assert any(f["kind"] == "user_changes" for f in result.findings)


def test_untracked_unknown_changes_reject_without_rollback(tmp_path: Path) -> None:
    repo, base_sha, head_sha = make_repo(tmp_path)
    (repo / "mystery.py").write_text("??", encoding="utf-8")
    result = run_accept(repo, base_sha, head_sha, verify_fn=RecordingVerify(verify_ok))
    assert result.verdict == "BLOCKED"
    assert result.rolled_back is False
    assert (repo / "mystery.py").read_text(encoding="utf-8") == "??"
    assert any(f["kind"] == "unknown_changes" for f in result.findings)

