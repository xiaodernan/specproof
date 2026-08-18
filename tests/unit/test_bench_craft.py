"""SpecCraft micro-benchmark runner unit tests (mock subprocess, no live runs).

Covers:
  - craft CLI invocation shape (python -m cli.specproof.main craft run ...)
  - verdict classification (DONE + judge -> COMPLETE / INTERCEPTED / ...)
  - summary math (completion / avg iterations / within-budget / interception)
  - markdown rendering contains measured numbers and honest headers
  - --llm gate refuses without a usable LLM_API_KEY (never faked)
  - judge replay copies judge tests into the workspace before pytest
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from bench_craft import (  # noqa: E402
    BenchError,
    RunInfo,
    TaskVerdict,
    _select_tasks,
    build_craft_command,
    classify_verdict,
    compute_summary,
    discover_tasks,
    load_task_meta,
    refuse_llm_without_key,
    render_markdown,
    run_judge,
)

BENCH_TASKS = REPO_ROOT / "bench" / "tasks"


def _verdict(
    task_id: str = "task-01",
    *,
    trap: bool = False,
    verdict: str = "COMPLETE",
    iterations: int | None = 1,
) -> TaskVerdict:
    return TaskVerdict(
        task_id=task_id,
        theme="t",
        appendix_e="E-1",
        trap=trap,
        verdict=verdict,
        craft_rc=0,
        craft_result="DONE",
        craft_mode="deterministic",
        iterations=iterations,
        seconds=10.0,
        judge_rc=0 if verdict == "COMPLETE" else 1,
        judge_failed=[] if verdict == "COMPLETE" else ["test_judge.py::test_x"],
    )


# ── craft invocation shape ──────────────────────────────────────


def test_build_craft_command_shape(tmp_path: Path) -> None:
    spec = tmp_path / "task.spec"
    repo = tmp_path / "repo"
    fixes = tmp_path / "fixes.py"
    command = build_craft_command(spec, repo, fixes, max_iterations=7, llm=False)
    assert command[:4] == [sys.executable, "-m", "cli.specproof.main", "craft"]
    assert command[4] == "run"
    assert command[5] == str(spec)
    assert command[6:8] == ["--repo", str(repo)]
    assert "--no-llm" in command
    assert "--llm" not in command
    assert command[command.index("--fix-module") + 1] == str(fixes)
    assert command[command.index("--max-iterations") + 1] == "7"


def test_build_craft_command_llm_flag() -> None:
    command = build_craft_command(Path("s"), Path("r"), Path("f"), 3, llm=True)
    assert "--llm" in command
    assert "--no-llm" not in command


def test_run_judge_copies_judge_tests_then_runs_pytest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir = tmp_path / "task"
    judge_dir = task_dir / "judge"
    judge_dir.mkdir(parents=True)
    (judge_dir / "test_judge_a.py").write_text("def test_a() -> None: ...\n", encoding="utf-8")
    (judge_dir / "test_judge_b.py").write_text("def test_b() -> None: ...\n", encoding="utf-8")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(
        command: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="2 passed", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    rc, failed = run_judge(task_dir, scratch, timeout=60)
    assert rc == 0
    assert failed == []
    assert (scratch / "test_judge_a.py").is_file()
    assert (scratch / "test_judge_b.py").is_file()
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[:3] == [sys.executable, "-m", "pytest"]
    assert kwargs["cwd"] == scratch


# ── verdict classification ──────────────────────────────────────


def test_classify_verdict_matrix() -> None:
    assert classify_verdict("DONE", 0) == "COMPLETE"
    assert classify_verdict("DONE", 1) == "INTERCEPTED"
    assert classify_verdict("FAILED", 1) == "CRAFT_FAILED"
    assert classify_verdict("STUCK", 0) == "CRAFT_FAILED"
    assert classify_verdict("EXPIRED", 0) == "CRAFT_FAILED"
    assert classify_verdict("CRASH", 1) == "CRAFT_FAILED"
    assert classify_verdict("DONE", None) == "JUDGE_ERROR"


# ── summary math ────────────────────────────────────────────────


def test_compute_summary_expected_benchmark_shape() -> None:
    verdicts = [_verdict(f"task-{index:02d}") for index in range(1, 10)]
    verdicts.append(_verdict("task-10", trap=True, verdict="INTERCEPTED"))
    summary = compute_summary(verdicts)
    assert summary["total"] == 10
    assert summary["completed"] == 9
    assert summary["intercepted"] == 1
    assert summary["craft_failed"] == 0
    assert summary["traps"] == 1
    assert summary["traps_intercepted"] == 1
    assert summary["completion_rate_pct"] == 90.0
    assert summary["within_budget_rate_pct"] == 100.0
    assert summary["avg_iterations"] == 1.0
    assert summary["interception_rate_pct"] == 100.0


def test_compute_summary_avg_iterations_ignores_missing() -> None:
    verdicts = [_verdict("a", iterations=2), _verdict("b", iterations=None)]
    assert compute_summary(verdicts)["avg_iterations"] == 2.0


def test_compute_summary_empty_list_is_zero_and_none() -> None:
    summary = compute_summary([])
    assert summary["total"] == 0
    assert summary["completion_rate_pct"] == 0.0
    assert summary["within_budget_rate_pct"] == 0.0
    assert summary["avg_iterations"] == 0.0
    assert summary["interception_rate_pct"] is None


def test_compute_summary_interception_none_without_traps() -> None:
    summary = compute_summary([_verdict("a"), _verdict("b")])
    assert summary["interception_rate_pct"] is None


# ── markdown rendering ──────────────────────────────────────────


def test_render_markdown_contains_measured_numbers() -> None:
    verdicts = [_verdict("task-01"), _verdict("task-10", trap=True, verdict="INTERCEPTED")]
    summary = compute_summary(verdicts)
    info = RunInfo(
        started_utc="2026-08-18T00:00:00+00:00",
        python_version="3.12.0",
        sandbox="local",
        max_iterations=12,
        llm_requested=False,
        tasks_dir="bench/tasks",
    )
    text = render_markdown(summary, verdicts, info)
    assert "# SpecCraft 微基准实测报告 (craft-microbench)" in text
    assert "50.0%" in text          # completion rate
    assert "100.0%" in text         # interception rate
    assert "| 任务 | 主题 | 附录 E | 陷阱 | craft | 迭代 | 秒 | judge | 判定 |" in text
    assert "| task-01 |" in text
    assert "| task-10 |" in text
    assert "**INTERCEPTED**" in text
    assert "**COMPLETE**" in text
    assert "SPECPROOF_SANDBOX=local" in text
    assert "not_implemented" in text  # honesty note about the M3 self-verify gap
    assert "§7" in text


# ── LLM gate ────────────────────────────────────────────────────


def test_refuse_llm_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(BenchError, match="LLM_API_KEY"):
        refuse_llm_without_key()


def test_refuse_llm_placeholder_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "replace_me")
    with pytest.raises(BenchError, match="replace_me"):
        refuse_llm_without_key()


def test_llm_gate_passes_with_real_looking_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-" + "bench-" + "not-a-real-key")
    refuse_llm_without_key()  # must not raise


# ── task discovery / selection against the real bench tree ──────


def test_discover_tasks_finds_ten_real_tasks() -> None:
    task_dirs = discover_tasks(BENCH_TASKS)
    assert [path.name.split("-", 2)[1] for path in task_dirs] == [
        f"{index:02d}" for index in range(1, 11)
    ]
    assert len(task_dirs) == 10


def test_load_task_meta_required_fields() -> None:
    meta = load_task_meta(BENCH_TASKS / "task-01-add-readonly-query")
    assert meta["id"] == "task-01"
    assert isinstance(meta["acceptance_criteria"], list)
    assert meta["affected_area_hint"] == "svc.py"
    assert meta["trap"] is False


def test_load_task_meta_trap_flag() -> None:
    meta = load_task_meta(BENCH_TASKS / "task-10-trap-auth-regression")
    assert meta["trap"] is True


def test_select_tasks_only_and_exclude() -> None:
    task_dirs = discover_tasks(BENCH_TASKS)
    selected = _select_tasks(task_dirs, "task-01", "")
    assert [path.name for path in selected] == ["task-01-add-readonly-query"]
    selected = _select_tasks(task_dirs, "", "task-01")
    assert all(path.name != "task-01-add-readonly-query" for path in selected)
    assert len(selected) == 9


def test_bench_task_specs_are_valid_craft_schemas() -> None:
    """Every bench task.spec must parse under the shared craft spec schema
    (the same file drives craft and the bench judge — closed-loop contract)."""
    sys.path.insert(0, str(REPO_ROOT))
    from craft.spec import parse_spec  # noqa: E402

    for task_dir in discover_tasks(BENCH_TASKS):
        spec_path = task_dir / "task.spec"
        task = parse_spec(json.dumps(json.loads(spec_path.read_text(encoding="utf-8"))))
        assert task.title.strip()
        assert task.acceptance_criteria
        assert task.forbidden_changes
