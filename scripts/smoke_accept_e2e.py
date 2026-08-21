"""One-shot E2E smoke: craft run (deterministic fix) -> craft_accept with the
REAL SpecProof verification pipeline, on a tiny python fixture repo.
Bounded: if the real pipeline needs maven/docker it will fail closed and we
document the result honestly.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from craft.accept import (  # noqa: E402
    craft_accept,
    persist_accept_result,
    requirement_text_from_job_spec,
)
from craft.editor import Editor  # noqa: E402
from craft.loop import CraftLoop  # noqa: E402
from craft.planner import Step, compile_plan  # noqa: E402
from craft.schemas import ChangeBundle, TestResult  # noqa: E402
from craft.spec import parse_spec_text  # noqa: E402
from storage.agent_jobs import SqliteAgentJobStore  # noqa: E402

FIX_SPEC = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"

def main():
    base_dir = Path(tempfile.mkdtemp(prefix="specproof-smoke-"))
    repo = base_dir / "demo"
    repo.mkdir()
    (repo / "calc.py").write_text("def double(x):\n    return x / 2\n", encoding="utf-8")
    (repo / "test_calc.py").write_text(
        "from calc import double\n\n\ndef test_double():\n    assert double(4) == 8\n",
        encoding="utf-8",
    )
    (repo / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths = ['.']\n", encoding="utf-8"
    )
    for cmd in (
        ["git", "init", "-q"],
        ["git", "add", "."],
        [
            "git", "-c", "user.email=smoke@example.com", "-c", "user.name=smoke",
            "commit", "-qm", "base",
        ],
    ):
        subprocess.run(cmd, cwd=repo, check=True)
    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()

    def fix_double(editor: Editor, step: Step, diagnosis: str) -> list[str]:
        editor.apply_edit("calc.py", "return x / 2", "return x * 2")
        return ["calc.py"]

    store = SqliteAgentJobStore(base_dir / "jobs.sqlite")
    spec = parse_spec_text(FIX_SPEC)
    plan = compile_plan(spec)
    loop = CraftLoop(
        spec, plan, repo, job_id="smoke-1", fix_registry={"test": fix_double},
        exec_mode="local", store=store,
    )
    report = loop.run()
    print("LOOP_RESULT:", report["result"])
    # commit the fixed head so the Base/Head differential can observe it
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        [
            "git", "-c", "user.email=smoke@example.com", "-c", "user.name=smoke",
            "commit", "-qm", "head fix",
        ],
        cwd=repo,
        check=True,
    )
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()

    key = Ed25519PrivateKey.generate().private_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    ).hex()
    os.environ["SPECPROOF_SIGNING_KEY"] = key
    os.environ["SPECPROOF_SANDBOX"] = "local"  # real gates + real verify, no Docker

    bundle = ChangeBundle(
        task_id="smoke-1",
        changed_files=list(report["diff_stat"]["files"]),
        test_results=[
            TestResult(command="python -m pytest -q", exit_code=0, summary="", passed=True)
        ],
    )
    job = store.get("smoke-1")
    spec_text = requirement_text_from_job_spec(job.spec_text)
    result = craft_accept(bundle, spec_text, repo, base_sha, head_sha, job_id="smoke-1")
    print("ACCEPT_VERDICT:", result.verdict)
    print("CERT:", result.certificate_path)
    print("ROLLED_BACK:", result.rolled_back)
    print("FINDINGS:", len(result.findings))
    for f in result.findings[:5]:
        print("  -", f.get("kind"), "|", str(f.get("description"))[:160])
    print("GATES_OVERALL:", (result.gates_report or {}).get("overall"))
    print("NOTE:", result.note)

    # W35.1: post-hoc accept projection into the durable job store
    # (attach_accept_result — succeeded/failed only, first attach wins).
    persisted = persist_accept_result(store, "smoke-1", result)
    print("ACCEPT_PERSISTED:", persisted)
    fresh = store.get("smoke-1")
    if fresh and fresh.accept_json:
        stored = json.loads(fresh.accept_json)
        print("STORED_ACCEPT_VERDICT:", stored.get("verdict"))
        print("STORED_CERTIFICATE_PATH:", stored.get("certificate_path"))

if __name__ == "__main__":
    main()
