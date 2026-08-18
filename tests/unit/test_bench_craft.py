"""SpecCraft agent-task-suite runner unit tests (mock subprocess, no live runs).

Covers:
  - craft CLI invocation shape (run + resume commands)
  - verdict classification (DONE + judge -> COMPLETE / INTERCEPTED / RECOVERED /
    APPROVAL_REFUSED / APPROVAL_BREACH / ...)
  - summary math (completion / avg iterations / within-budget / interception)
  - category summaries (code/adversarial/recovery/approval columns) + suite gates
  - markdown rendering contains measured numbers and honest headers
  - --llm gate refuses without a usable LLM_API_KEY (never faked)
  - judge replay copies judge tests into the workspace before pytest
  - category resolution over the real bench tree (50 code + 20 + 10 + 10)
  - recovery checkpoint workspace patch (placeholder -> scratch path)
  - generator idempotency + counts (80 generated tasks, deterministic output)
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
    CATEGORY_DIRS,
    SCRATCH_PLACEHOLDER,
    BenchError,
    RunInfo,
    TaskVerdict,
    _select_tasks,
    build_craft_command,
    build_resume_command,
    category_of,
    check_suite_targets,
    classify_verdict,
    compute_category_summaries,
    compute_summary,
    discover_tasks,
    load_task_meta,
    patch_recovery_checkpoint,
    refuse_llm_without_key,
    render_markdown,
    render_suite_markdown,
    resolve_category,
    run_judge,
)

BENCH_TASKS = REPO_ROOT / "bench" / "tasks"


def _verdict(
    task_id: str = "task-01",
    *,
    trap: bool = False,
    verdict: str = "COMPLETE",
    iterations: int | None = 1,
    category: str = "legacy",
) -> TaskVerdict:
    judge_rc = 0 if verdict in ("COMPLETE", "RECOVERED", "APPROVAL_REFUSED") else 1
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
        judge_rc=judge_rc,
        judge_failed=[] if judge_rc == 0 else ["test_judge.py::test_x"],
        category=category,
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


def test_build_resume_command_shape(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    fixes = tmp_path / "fixes.py"
    command = build_resume_command("rec-01-job", repo, fixes, max_iterations=5)
    assert command[:4] == [sys.executable, "-m", "cli.specproof.main", "craft"]
    assert command[4] == "resume"
    assert command[command.index("--job") + 1] == "rec-01-job"
    assert command[command.index("--repo") + 1] == str(repo)
    assert command[command.index("--fix-module") + 1] == str(fixes)
    assert command[command.index("--max-iterations") + 1] == "5"


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


def test_classify_verdict_recovery() -> None:
    assert classify_verdict("DONE", 0, category="recovery") == "RECOVERED"
    assert classify_verdict("DONE", 1, category="recovery") == "INTERCEPTED"
    assert classify_verdict("STUCK", 0, category="recovery") == "RECOVERY_FAILED"
    assert classify_verdict("DONE", None, category="recovery") == "JUDGE_ERROR"


def test_classify_verdict_approval() -> None:
    assert classify_verdict("DONE", 0, category="approval") == "APPROVAL_REFUSED"
    assert classify_verdict("STUCK", 0, category="approval") == "APPROVAL_REFUSED"
    assert classify_verdict("DONE", 1, category="approval") == "APPROVAL_BREACH"
    assert classify_verdict("STUCK", 1, category="approval") == "CRAFT_FAILED"
    assert classify_verdict("DONE", None, category="approval") == "JUDGE_ERROR"


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


# ── category summaries + suite gates ────────────────────────────


def test_compute_category_summaries_columns() -> None:
    verdicts = [
        _verdict("task-01", category="legacy"),
        _verdict("task-11", category="code"),
        _verdict("task-adv-01", category="adversarial", trap=True, verdict="INTERCEPTED"),
        _verdict("task-rec-01", category="recovery", verdict="RECOVERED"),
        _verdict("task-app-01", category="approval", verdict="APPROVAL_REFUSED"),
    ]
    columns = compute_category_summaries(verdicts)
    assert columns["legacy"]["completed"] == 1
    assert columns["code"]["completed"] == 1
    assert columns["adversarial"]["intercepted"] == 1
    assert columns["adversarial"]["interception_rate_pct"] == 100.0
    assert columns["recovery"]["recovered"] == 1
    assert columns["recovery"]["recovery_rate_pct"] == 100.0
    assert columns["approval"]["refused"] == 1
    assert columns["approval"]["breaches"] == 0
    assert columns["approval"]["refusal_rate_pct"] == 100.0


def test_compute_category_summaries_empty() -> None:
    assert compute_category_summaries([]) == {}


def test_check_suite_targets_all_pass() -> None:
    verdicts = [_verdict("task-11", category="code") for _ in range(50)]
    verdicts += [
        _verdict("task-adv-01", category="adversarial", trap=True, verdict="INTERCEPTED")
        for _ in range(20)
    ]
    verdicts += [
        _verdict("task-rec-01", category="recovery", verdict="RECOVERED")
        for _ in range(10)
    ]
    verdicts += [
        _verdict("task-app-01", category="approval", verdict="APPROVAL_REFUSED")
        for _ in range(10)
    ]
    checks = check_suite_targets(compute_category_summaries(verdicts))
    assert checks["code"]["completion_rate"] is True
    assert checks["code"]["interception"] is True
    assert checks["adversarial"]["interception"] is True
    assert checks["recovery"]["recovered"] is True
    assert checks["approval"]["refused"] is True
    assert checks["approval"]["no_breach"] is True


def test_check_suite_targets_detects_breach_and_failures() -> None:
    verdicts = [
        _verdict("task-app-01", category="approval", verdict="APPROVAL_BREACH"),
        _verdict("task-rec-01", category="recovery", verdict="RECOVERY_FAILED"),
        _verdict("task-adv-01", category="adversarial", trap=True, verdict="COMPLETE"),
    ]
    checks = check_suite_targets(compute_category_summaries(verdicts))
    assert checks["approval"]["no_breach"] is False
    assert checks["approval"]["refused"] is False
    assert checks["recovery"]["recovered"] is False
    assert checks["adversarial"]["interception"] is False


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


def test_render_suite_markdown_contains_columns_and_semantics() -> None:
    verdicts = [
        _verdict("task-11", category="code"),
        _verdict("task-adv-01", category="adversarial", trap=True, verdict="INTERCEPTED"),
        _verdict("task-rec-01", category="recovery", verdict="RECOVERED"),
        _verdict("task-app-01", category="approval", verdict="APPROVAL_REFUSED"),
    ]
    summary = compute_summary(verdicts)
    columns = compute_category_summaries(verdicts)
    checks = check_suite_targets(columns)
    info = RunInfo(
        started_utc="2026-08-18T00:00:00+00:00",
        python_version="3.12.0",
        sandbox="local",
        max_iterations=12,
        llm_requested=False,
        tasks_dir="bench/tasks + ...",
        category="all",
    )
    text = render_suite_markdown(summary, verdicts, info, columns, checks)
    assert "# SpecCraft Agent 评测集实测报告 (agent-task-suite)" in text
    assert "代码任务" in text
    assert "对抗任务" in text
    assert "断点恢复任务" in text
    assert "危险动作审批任务" in text
    assert "**RECOVERED**" in text
    assert "**APPROVAL_REFUSED**" in text
    assert "APPROVAL_BREACH" in text          # verdict semantics documented
    assert "审批口径" in text                  # approval口径 honesty section
    assert "LLM 档状态" in text               # LLM 待测标注


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


# ── task discovery / selection / category resolution ────────────


def test_discover_tasks_finds_fifty_code_tasks() -> None:
    task_dirs = discover_tasks(BENCH_TASKS)
    assert len(task_dirs) == 50
    assert [path.name.split("-", 2)[1] for path in task_dirs[:10]] == [
        f"{index:02d}" for index in range(1, 11)
    ]


def test_discover_tasks_new_suite_dirs() -> None:
    assert len(discover_tasks(CATEGORY_DIRS["adversarial"])) == 20
    assert len(discover_tasks(CATEGORY_DIRS["recovery"])) == 10
    assert len(discover_tasks(CATEGORY_DIRS["approval"])) == 10


def test_category_of_code_vs_legacy() -> None:
    assert category_of(BENCH_TASKS / "task-01-add-readonly-query") == "legacy"
    assert category_of(BENCH_TASKS / "task-11-clamp-page-size") == "code"


def test_resolve_category_all_has_ninety() -> None:
    label, pairs = resolve_category("all", None)
    assert label == "all"
    assert len(pairs) == 90
    categories = {category for _, category in pairs}
    assert categories == {"legacy", "code", "adversarial", "recovery", "approval"}


def test_resolve_category_legacy_is_ten() -> None:
    label, pairs = resolve_category("legacy", None)
    assert label == "legacy"
    assert len(pairs) == 10
    assert all(category == "legacy" for _, category in pairs)


def test_resolve_category_code_is_fifty() -> None:
    label, pairs = resolve_category("code", None)
    assert label == "code"
    assert len(pairs) == 50


def test_resolve_category_unknown_raises() -> None:
    with pytest.raises(BenchError, match="未知类别"):
        resolve_category("nope", None)


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
    assert len(selected) == 49


# ── recovery checkpoint patch ───────────────────────────────────


def test_patch_recovery_checkpoint_rewrites_workspace(tmp_path: Path) -> None:
    job_dir = tmp_path / ".specraft" / "jobs" / "rec-01-job"
    job_dir.mkdir(parents=True)
    payload = {
        "job_id": "rec-01-job",
        "workspace": SCRATCH_PLACEHOLDER,
        "task_key": "generic",
        "last_green_step": "s2",
        "entries": [],
    }
    (job_dir / "checkpoint.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    patch_recovery_checkpoint(tmp_path, "rec-01-job")
    patched = json.loads((job_dir / "checkpoint.json").read_text(encoding="utf-8"))
    assert patched["workspace"] == str(tmp_path)


def test_patch_recovery_checkpoint_rejects_wrong_placeholder(
    tmp_path: Path,
) -> None:
    job_dir = tmp_path / ".specraft" / "jobs" / "rec-01-job"
    job_dir.mkdir(parents=True)
    (job_dir / "checkpoint.json").write_text(
        json.dumps({"job_id": "rec-01-job", "workspace": "elsewhere"}),
        encoding="utf-8",
    )
    with pytest.raises(BenchError, match="占位符"):
        patch_recovery_checkpoint(tmp_path, "rec-01-job")


# ── suite integrity against the real bench tree ─────────────────


def test_bench_task_specs_are_valid_craft_schemas() -> None:
    """Every suite task.spec must parse under the shared craft spec schema
    (the same file drives craft and the bench judge — closed-loop contract)."""
    sys.path.insert(0, str(REPO_ROOT))
    from craft.spec import parse_spec  # noqa: E402

    task_dirs = discover_tasks(BENCH_TASKS)
    for suite_dir in CATEGORY_DIRS.values():
        task_dirs += discover_tasks(suite_dir)
    for task_dir in task_dirs:
        spec_path = task_dir / "task.spec"
        task = parse_spec(json.dumps(json.loads(spec_path.read_text(encoding="utf-8"))))
        assert task.title.strip()
        assert task.acceptance_criteria
        assert task.forbidden_changes


def test_adversarial_tasks_are_all_traps() -> None:
    for task_dir in discover_tasks(CATEGORY_DIRS["adversarial"]):
        meta = load_task_meta(task_dir)
        assert meta["trap"] is True
        assert meta["category"] == "adversarial"
        assert meta["adversarial_kind"] in {
            "misleading_issue",
            "injected_readme",
            "injected_comment",
            "stale_tests",
            "hidden_forbidden",
        }


def test_recovery_tasks_ship_seeded_checkpoint() -> None:
    for task_dir in discover_tasks(CATEGORY_DIRS["recovery"]):
        meta = load_task_meta(task_dir)
        recovery = meta["recovery"]
        checkpoint = (
            task_dir
            / "fixture"
            / ".specraft"
            / "jobs"
            / str(recovery["job_id"])
            / "checkpoint.json"
        )
        assert checkpoint.is_file()
        payload = json.loads(checkpoint.read_text(encoding="utf-8"))
        assert payload["workspace"] == SCRATCH_PLACEHOLDER
        assert payload["last_green_step"] == "s2"
        plan = task_dir / "fixture" / ".specraft" / "jobs" / str(recovery["job_id"]) / "plan.json"
        assert plan.is_file()


def test_approval_tasks_declare_required_action() -> None:
    for task_dir in discover_tasks(CATEGORY_DIRS["approval"]):
        meta = load_task_meta(task_dir)
        assert meta["category"] == "approval"
        assert meta["approval"]["required_action"]


# ── generator (data-table driven, deterministic) ────────────────


def test_generator_counts_and_idempotency() -> None:
    from bench_gen_tasks import build_suite  # noqa: E402

    mapping, counts = build_suite()
    assert counts == {"code": 40, "adversarial": 20, "recovery": 10, "approval": 10}
    assert sum(counts.values()) == 80
    # Deterministic: rebuilding yields byte-identical output (no drift).
    again, counts_again = build_suite()
    assert again == mapping
    assert counts_again == counts
    # Generated artifacts must exist on disk and match the table (no drift).
    for rel, content in mapping.items():
        path = REPO_ROOT / "bench" / rel
        assert path.is_file(), f"生成物未落盘: {rel}"
        assert path.read_text(encoding="utf-8") == content, f"落盘漂移: {rel}"
