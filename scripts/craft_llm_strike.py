#!/usr/bin/env python
"""craft_llm_strike.py — drive one real free-form Chinese requirement through
the full SpecCraft → SpecProof chain against the LIVE aizzz lane.

    修复 double 函数的逻辑错误

into a scratch python fixture repo:

    plan  — compile_plan(mode="llm")  → real aizzz/gpt-6.1-terra Chinese plan
    loop  — no injected fix rules; the LLM edit agent proposes the fix itself
    prove — pytest must go green in the workspace
    dock  — craft_accept base-vs-head differential; verdict recorded verbatim

Everything measured is printed; nothing is retried to grief. An honest
failure IS the result — recorded, never patched over.

Run through the local proxy:

    HTTPS_PROXY=http://127.0.0.1:7897 HTTP_PROXY=http://127.0.0.1:7897 \
        python scripts/craft_llm_strike.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REQUIREMENT = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def main() -> int:
    base_dir = Path(tempfile.mkdtemp(prefix="specproof-llm-strike-"))
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
    (repo / ".gitignore").write_text("/.venv/\n", encoding="utf-8")
    _run(["git", "init", "-q"], cwd=repo)
    _run(["git", "add", "."], cwd=repo)
    _run(["git", "-c", "user.email=strike@example.com", "-c", "user.name=strike", "commit", "-qm", "base"], cwd=repo)
    base_sha = _run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()

    from craft.accept import craft_accept
    from craft.llm import LLMClient
    from craft.loop import CraftLoop
    from craft.planner import compile_plan
    from craft.schemas import ChangeBundle
    from craft.spec import parse_spec_text
    from storage.agent_jobs import SqliteAgentJobStore

    started = datetime.now(UTC).isoformat()
    spec = parse_spec_text(REQUIREMENT)

    client = LLMClient(job_id="craft-llm-strike")
    print(f"lane: available={client.available}")

    plan = compile_plan(spec, mode="llm", client=client)
    print(f"plan.mode={plan.mode} llm_fallback_reason={(plan.llm_fallback_reason if hasattr(plan, 'llm_fallback_reason') else None)!r}")
    for step in plan.steps:
        print(f"  step {step.id}: {getattr(step, 'kind', '?')} · {str(getattr(step, 'title', ''))[:60]}")

    store = SqliteAgentJobStore(base_dir / "jobs.sqlite")
    loop = CraftLoop(
        spec,
        plan,
        repo,
        job_id="craft-llm-strike",
        client=client,
        exec_mode="local",
        store=store,
    )
    report = loop.run()
    print("LOOP_RESULT:", report.get("result"))

    diff = _run(["git", "diff", "HEAD"], cwd=repo).stdout
    print("=== DIFF (model's own edit) ===")
    print(diff or "(no diff produced)")

    stat = _run(["git", "status", "--porcelain"], cwd=repo).stdout.strip()
    _committed = False
    if stat:
        _run(["git", "add", "."], cwd=repo)
        _run(
            ["git", "-c", "user.email=strike@example.com", "-c", "user.name=strike", "commit", "-qm", "model fix"],
            cwd=repo,
        )
        _committed = True
    head_sha = _run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()

    llm_stats = client.stats_report() if client else {}
    print("=== LLM USAGE (in-memory stats) ===")
    for key in ("calls", "prompt_tokens", "completion_tokens", "reasoning_tokens", "prompt_cache_hit_tokens"):
        print(f"  {key}: {llm_stats.get(key)}")
    print("=== ACCEPT (craft_accept, FAST) ===")
    try:
        bundle = ChangeBundle(task_id="craft-llm-strike", changed_files=["calc.py"], diff=diff)
        result = craft_accept(bundle, REQUIREMENT, repo, base_sha, head_sha, job_id="craft-llm-strike", depth="FAST")
        verdict = getattr(result, "verdict", None) or (result.to_dict() if hasattr(result, "to_dict") else str(result))
        print("accept verdict:", verdict)
    except Exception as exc:  # noqa: BLE001 - any accept failure is recorded, never patched
        print(f"accept ERROR: {type(exc).__name__}: {exc}")

    pytest = _run([sys.executable, "-m", "pytest", "-q"], cwd=repo)
    print(f"pytest rc={pytest.returncode} tail={pytest.stdout.strip().splitlines()[-1] if pytest.stdout.strip() else pytest.stderr.strip()[-120:]}")

    print(f"\nworkspace: {repo}")
    print(f"started_utc: {started}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
