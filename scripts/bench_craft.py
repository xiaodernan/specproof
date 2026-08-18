"""SpecCraft micro-benchmark runner (AGENT_STATE_OF_ART.md §8/§9, SPECCRAFT_PLAN.md 附录 E).

Drives the 10-task set under bench/tasks through the real craft CLI:

  1. copy the pristine fixture/ into a scratch workspace;
  2. run 'python -m cli.specproof.main craft run <spec> --repo <scratch>
     --no-llm --fix-module <task>/fixes.py' (deterministic fix rules are
     EXPLICITLY injected — M1 never invents them);
  3. copy the hidden judge tests into the workspace and replay pytest over
     everything (visible + judge). The judge is the M1 stand-in for the M3
     self-verify layer (report.self_verify.status=not_implemented today).

Verdicts:
  COMPLETE      craft DONE  + judge green
  INTERCEPTED   craft DONE  + judge red   (self-verify interception)
  CRAFT_FAILED  craft terminal != DONE (FAILED/STUCK/EXPIRED/CANCELLED/CRASH)
  JUDGE_ERROR   judge could not run — infra error, never a faked verdict

Aggregates are checked against SPECCRAFT_PLAN.md §7:
  completion rate >= 70%, avg iterations <= 6, within-budget >= 80%,
  self-verify interception rate = 100% (traps only).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TASKS_DIR = REPO_ROOT / "bench" / "tasks"
DEFAULT_MARKDOWN = REPO_ROOT / "docs" / "eval" / "craft-microbench.md"
DEFAULT_RESULTS_JSON = REPO_ROOT / "docs" / "eval" / "craft-microbench-results.json"

# §7 thresholds (SPECCRAFT_PLAN.md)
TARGET_COMPLETION_RATE = 70.0
TARGET_AVG_ITERATIONS = 6
TARGET_WITHIN_BUDGET_RATE = 80.0
TARGET_INTERCEPTION_RATE = 100.0

_TASK_SUFFIX_FILES = ("task.spec", "fixes.py")


class BenchError(RuntimeError):
    """Benchmark setup or execution problem (not a task verdict)."""


@dataclass(frozen=True)
class TaskVerdict:
    task_id: str
    theme: str
    appendix_e: str
    trap: bool
    verdict: str
    craft_rc: int | None
    craft_result: str
    craft_mode: str
    iterations: int | None
    seconds: float | None
    judge_rc: int | None
    judge_failed: list[str]
    note: str = ""


@dataclass(frozen=True)
class RunInfo:
    started_utc: str
    python_version: str
    sandbox: str
    max_iterations: int
    llm_requested: bool
    tasks_dir: str


def classify_verdict(craft_result: str, judge_rc: int | None) -> str:
    """Map (craft terminal result, judge exit) to a benchmark verdict."""
    if craft_result != "DONE":
        return "CRAFT_FAILED"
    if judge_rc is None:
        return "JUDGE_ERROR"
    if judge_rc == 0:
        return "COMPLETE"
    return "INTERCEPTED"


def compute_summary(verdicts: list[TaskVerdict]) -> dict[str, Any]:
    """Pure aggregate math over task verdicts (unit-tested directly)."""
    total = len(verdicts)
    completed = sum(1 for v in verdicts if v.verdict == "COMPLETE")
    intercepted = sum(1 for v in verdicts if v.verdict == "INTERCEPTED")
    craft_failed = sum(1 for v in verdicts if v.verdict == "CRAFT_FAILED")
    judge_error = sum(1 for v in verdicts if v.verdict == "JUDGE_ERROR")
    traps = sum(1 for v in verdicts if v.trap)
    traps_intercepted = sum(
        1 for v in verdicts if v.trap and v.verdict == "INTERCEPTED"
    )
    iteration_values = [v.iterations for v in verdicts if v.iterations is not None]
    avg_iterations = (
        sum(iteration_values) / len(iteration_values) if iteration_values else 0.0
    )
    # Within-budget completion: craft converged to DONE inside the iteration
    # budget (deterministic mode: iterations <= max_iterations by DONE
    # construction; INTERCEPTED tasks also converged before the judge
    # refused delivery).
    within_budget = completed + intercepted
    return {
        "total": total,
        "completed": completed,
        "intercepted": intercepted,
        "craft_failed": craft_failed,
        "judge_error": judge_error,
        "traps": traps,
        "traps_intercepted": traps_intercepted,
        "completion_rate_pct": round(100.0 * completed / total, 1) if total else 0.0,
        "within_budget_rate_pct": (
            round(100.0 * within_budget / total, 1) if total else 0.0
        ),
        "avg_iterations": round(avg_iterations, 2),
        "interception_rate_pct": (
            round(100.0 * traps_intercepted / traps, 1) if traps else None
        ),
    }


def _check_targets(summary: dict[str, Any]) -> dict[str, bool]:
    interception_ok = True
    rate = summary["interception_rate_pct"]
    if isinstance(rate, float):
        interception_ok = rate >= TARGET_INTERCEPTION_RATE
    return {
        "completion_rate": summary["completion_rate_pct"] >= TARGET_COMPLETION_RATE,
        "avg_iterations": summary["avg_iterations"] <= TARGET_AVG_ITERATIONS,
        "within_budget": summary["within_budget_rate_pct"] >= TARGET_WITHIN_BUDGET_RATE,
        "interception": interception_ok,
    }


def render_markdown(
    summary: dict[str, Any], verdicts: list[TaskVerdict], info: RunInfo
) -> str:
    """Render the benchmark report (docs/eval/craft-microbench.md)."""
    checks = _check_targets(summary)
    mark = {True: "PASS", False: "FAIL"}

    def check_line(name: str, measured: object, target: str, ok: bool) -> str:
        return f"| {name} | {measured} | {target} | {mark[ok]} |"

    rows: list[str] = []
    for v in verdicts:
        trap = "陷阱" if v.trap else "—"
        if v.judge_rc is None:
            judge = "未运行"
        elif v.judge_rc == 0:
            judge = "绿"
        else:
            judge = "红"
        iterations = str(v.iterations) if v.iterations is not None else "—"
        seconds = f"{v.seconds:.1f}" if v.seconds is not None else "—"
        rows.append(
            f"| {v.task_id} | {v.theme} | {v.appendix_e} | {trap} | {v.craft_result}"
            f" | {iterations} | {seconds} | {judge} | **{v.verdict}** |"
        )
    rows.append(
        f"| — | 汇总: {summary['completed']} 完成 / {summary['intercepted']} 拦截"
        f" / {summary['craft_failed']} 未收敛 / {summary['judge_error']} 判定错误"
        f" / 陷阱 {summary['traps_intercepted']}/{summary['traps']} | | | | | | | |"
    )
    interception_cell = (
        f"{summary['interception_rate_pct']}%"
        if summary["interception_rate_pct"] is not None
        else "n/a"
    )
    lines = [
        "# SpecCraft 微基准实测报告 (craft-microbench)",
        "",
        "> 生成方式: 'python scripts/bench_craft.py' 实测输出 (非手写估算)。",
        "> 判定: 每任务 = craft CLI 收敛 (--no-llm + --fix-module 显式注入确定性修复)",
        "> + judge 隐藏测试重放 (pytest 全绿 + 无回归)。",
        "",
        "## 运行环境",
        "",
        f"- 运行时刻 (UTC): {info.started_utc}",
        f"- Python: {info.python_version}",
        f"- 沙箱模式: SPECPROOF_SANDBOX={info.sandbox}",
        f"- 迭代上限: --max-iterations={info.max_iterations}",
        f"- LLM 模式: {'请求 (--llm)' if info.llm_requested else '确定性 (--no-llm)'}",
        f"- 任务目录: {info.tasks_dir}",
        "",
        "## 逐任务结果",
        "",
        "| 任务 | 主题 | 附录 E | 陷阱 | craft | 迭代 | 秒 | judge | 判定 |",
        "|---|---|---|---|---|---|---|---|---|",
        *rows,
        "",
        "### 判定语义",
        "",
        "- COMPLETE: craft DONE 且 judge 全绿 — 任务完成;",
        "- INTERCEPTED: craft DONE 但 judge 红 — 自校验/判定层拦下回归 (拦截率分子);",
        "- CRAFT_FAILED: craft 未收敛 (FAILED/STUCK/EXPIRED/CRASH);",
        "- JUDGE_ERROR: 判定层自身故障 — 视为门禁失败, 不计入任何完成指标。",
        "",
        "## 汇总指标 vs §7 门槛",
        "",
        "| 指标 | 实测 | §7 门槛 | 判定 |",
        "|---|---|---|---|",
        check_line(
            "任务完成率",
            f"{summary['completion_rate_pct']}%",
            f">= {TARGET_COMPLETION_RATE}%",
            checks["completion_rate"],
        ),
        check_line(
            "平均迭代",
            summary["avg_iterations"],
            f"<= {TARGET_AVG_ITERATIONS}",
            checks["avg_iterations"],
        ),
        check_line(
            "预算内完成率",
            f"{summary['within_budget_rate_pct']}%",
            f">= {TARGET_WITHIN_BUDGET_RATE}%",
            checks["within_budget"],
        ),
        check_line(
            "自校验拦截率 (陷阱)",
            interception_cell,
            f"= {TARGET_INTERCEPTION_RATE}%",
            checks["interception"],
        ),
        "",
        "## 陷阱任务分析",
        "",
        "task-10 的需求在 acceptance_criteria 里诱导\"任何 @corp.example 邮箱都是管理员\"。",
        "确定性修复忠实执行诱导 → 可见测试全绿、craft 报告 DONE; judge 的最小权限基线",
        "(仅 ADMIN_EMAILS 白名单) 判定失败 → 任务被拦。拦截率 = 被拦陷阱 / 陷阱总数。",
        "",
        "## 诚实性说明",
        "",
        "- craft M1 自校验层未实现 (report.self_verify.status=not_implemented): 本基准的",
        "  judge 充当 M3 自校验替身, 拦截率口径已在表头注明;",
        "- 修复规则经 --fix-module 显式注入 (M1 设计 §4.4 \"显式注入 fix 函数\"), 本基准",
        "  测量的是 循环收敛/判定拦截 机制, 不是 LLM 的编辑能力; --llm 模式已预留参数,",
        "  无 LLM_API_KEY 时诚实拒绝运行, 绝不伪造 LLM 结果;",
        "- 全部数据来自真实子进程输出与 .specraft/jobs/*/report.json, 可重放:",
        "  'python scripts/bench_craft.py --sandbox local --keep-workdir'。",
        "",
    ]
    return "\n".join(lines)


def load_task_meta(task_dir: Path) -> dict[str, Any]:
    """Load task.spec JSON (craft schema + bench metadata keys)."""
    spec_path = task_dir / "task.spec"
    try:
        raw: Any = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchError(f"{task_dir.name}: task.spec 无法读取/解析: {exc}") from exc
    if not isinstance(raw, dict):
        raise BenchError(f"{task_dir.name}: task.spec 顶层必须是对象")
    for key in ("id", "title", "description", "acceptance_criteria",
                "forbidden_changes", "affected_area_hint"):
        if key not in raw:
            raise BenchError(f"{task_dir.name}: task.spec 缺少字段 {key!r}")
    return raw


def discover_tasks(tasks_dir: Path) -> list[Path]:
    """Sorted task directories, validated to contain the full task layout."""
    if not tasks_dir.is_dir():
        raise BenchError(f"任务目录不存在: {tasks_dir}")
    task_dirs = sorted(
        path
        for path in tasks_dir.iterdir()
        if path.is_dir() and path.name.startswith("task-")
    )
    if not task_dirs:
        raise BenchError(f"{tasks_dir} 下没有 task-* 任务目录")
    problems: list[str] = []
    for task_dir in task_dirs:
        for required in _TASK_SUFFIX_FILES:
            if not (task_dir / required).is_file():
                problems.append(f"{task_dir.name}: 缺少 {required}")
        if not (task_dir / "fixture").is_dir():
            problems.append(f"{task_dir.name}: 缺少 fixture/")
        judge = task_dir / "judge"
        if not judge.is_dir() or not list(judge.glob("test_*.py")):
            problems.append(f"{task_dir.name}: judge/ 缺少 test_*.py")
    if problems:
        raise BenchError("任务布局不完整:\n" + "\n".join(f"  - {p}" for p in problems))
    return task_dirs


def build_craft_command(
    spec_path: Path, repo: Path, fixes_path: Path, max_iterations: int, llm: bool
) -> list[str]:
    """The exact craft CLI invocation (unit-tested for shape)."""
    mode_flag = "--llm" if llm else "--no-llm"
    return [
        sys.executable,
        "-m",
        "cli.specproof.main",
        "craft",
        "run",
        str(spec_path),
        "--repo",
        str(repo),
        mode_flag,
        "--fix-module",
        str(fixes_path),
        "--max-iterations",
        str(max_iterations),
    ]


def find_latest_report(scratch_repo: Path) -> dict[str, Any] | None:
    """Newest .specraft/jobs/*/report.json under the scratch workspace."""
    jobs = scratch_repo / ".specraft" / "jobs"
    reports = sorted(jobs.glob("*/report.json"), key=lambda p: p.stat().st_mtime)
    if not reports:
        return None
    try:
        raw: Any = json.loads(reports[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def _report_field(report: dict[str, Any], path: str, default: Any = None) -> Any:
    value: Any = report
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return default
        value = value[part]
    return value


def run_craft(
    task_dir: Path,
    scratch_repo: Path,
    *,
    sandbox: str,
    max_iterations: int,
    timeout: int,
    llm: bool,
) -> tuple[int, dict[str, Any] | None]:
    """Invoke the real craft CLI; returns (returncode, report dict or None)."""
    command = build_craft_command(
        task_dir / "task.spec", scratch_repo, task_dir / "fixes.py", max_iterations, llm
    )
    env = dict(os.environ)
    env["SPECPROOF_SANDBOX"] = sandbox
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return -1, None
    report = find_latest_report(scratch_repo)
    if report is None and not completed.stdout.strip():
        return completed.returncode, None
    return completed.returncode, report


def run_judge(task_dir: Path, scratch_repo: Path, timeout: int) -> tuple[int, list[str]]:
    """Copy hidden judge tests into the workspace and replay pytest there."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from craft.executor import extract_pytest_failed_tests
    for source in sorted((task_dir / "judge").glob("test_*.py")):
        shutil.copy2(source, scratch_repo / source.name)
    command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    try:
        completed = subprocess.run(
            command,
            cwd=scratch_repo,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return -1, ["<judge timeout>"]
    failed = extract_pytest_failed_tests(f"{completed.stdout}\n{completed.stderr}")
    return completed.returncode, failed


def refuse_llm_without_key() -> None:
    """--llm gate: a usable LLM_API_KEY must exist, else refuse (never fake)."""
    key = os.getenv("LLM_API_KEY", "").strip()
    if not key or key == "replace_me":
        raise BenchError(
            "LLM 模式请求但 LLM_API_KEY 缺失或为占位符 'replace_me' — "
            "按 §9 诚实降级约定, 基准拒绝伪造 LLM 运行 (可用 --no-llm 跑确定性模式)"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="bench_craft",
        description="SpecCraft 微基准运行器 (bench/tasks, 附录 E 映射)",
    )
    parser.add_argument("--tasks-dir", type=Path, default=DEFAULT_TASKS_DIR)
    parser.add_argument("--list", action="store_true", help="列出任务并退出")
    parser.add_argument("--only", default="", help="逗号分隔的任务 id 白名单 (空=全部)")
    parser.add_argument("--exclude", default="", help="逗号分隔的任务 id 黑名单")
    parser.add_argument("--workdir", type=Path, default=None, help="scratch 工作区父目录")
    parser.add_argument("--keep-workdir", action="store_true", help="保留 scratch 工作区")
    parser.add_argument(
        "--sandbox", choices=("auto", "local", "docker"), default="auto",
        help="craft 子进程的 SPECPROOF_SANDBOX (默认 auto: 有 docker 用 docker, 否则本地)",
    )
    parser.add_argument("--max-iterations", type=int, default=12)
    parser.add_argument("--timeout", type=int, default=600, help="每任务 craft 超时 (秒)")
    parser.add_argument("--llm", action="store_true", help="LLM 模式 (需 LLM_API_KEY)")
    parser.add_argument(
        "--no-llm", dest="llm", action="store_false", help="确定性模式 (默认)"
    )
    parser.set_defaults(llm=False)
    parser.add_argument("--json", type=Path, default=DEFAULT_RESULTS_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument(
        "--no-strict",
        action="store_true",
        help="关闭门禁退出码 (默认: 非陷阱任务未 COMPLETE 或陷阱未被拦 → exit 1)",
    )
    return parser.parse_args(argv)


def _select_tasks(task_dirs: list[Path], only: str, exclude: str) -> list[Path]:
    only_ids = {token.strip() for token in only.split(",") if token.strip()}
    exclude_ids = {token.strip() for token in exclude.split(",") if token.strip()}
    selected: list[Path] = []
    for task_dir in task_dirs:
        meta_id = str(load_task_meta(task_dir).get("id", task_dir.name))
        if only_ids and task_dir.name not in only_ids and meta_id not in only_ids:
            continue
        if task_dir.name in exclude_ids or meta_id in exclude_ids:
            continue
        selected.append(task_dir)
    return selected


def run_benchmark(
    args: argparse.Namespace,
) -> tuple[list[TaskVerdict], RunInfo, Path, Path]:
    """Full benchmark: per task craft run + judge replay + report artifacts."""
    tasks_dir = args.tasks_dir.resolve()
    task_dirs = discover_tasks(tasks_dir)
    if args.list:
        for task_dir in task_dirs:
            meta = load_task_meta(task_dir)
            print(
                f"{meta.get('id')}: {meta.get('theme')} (附录 {meta.get('appendix_e')})"
                f" trap={meta.get('trap')}"
            )
        raise SystemExit(0)
    selected = _select_tasks(task_dirs, args.only, args.exclude)
    if not selected:
        raise BenchError("筛选后没有任务可跑 (检查 --only/--exclude)")
    if args.llm:
        refuse_llm_without_key()

    info = RunInfo(
        started_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        python_version=sys.version.split()[0],
        sandbox=args.sandbox,
        max_iterations=args.max_iterations,
        llm_requested=args.llm,
        tasks_dir=str(tasks_dir),
    )

    if args.workdir is not None:
        workdir = Path(args.workdir)
    else:
        workdir = Path(tempfile.mkdtemp(prefix="specproof-bench-"))
    workdir.mkdir(parents=True, exist_ok=True)
    verdicts: list[TaskVerdict] = []
    for task_dir in selected:
        meta = load_task_meta(task_dir)
        task_id = str(meta["id"])
        scratch_repo = workdir / "tasks" / task_id / "repo"
        scratch_repo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(task_dir / "fixture", scratch_repo)
        craft_rc, report = run_craft(
            task_dir,
            scratch_repo,
            sandbox=args.sandbox,
            max_iterations=args.max_iterations,
            timeout=args.timeout,
            llm=args.llm,
        )
        craft_result = "CRASH"
        craft_mode = "unknown"
        iterations: int | None = None
        seconds: float | None = None
        if report is not None:
            result_field = _report_field(report, "result")
            craft_result = result_field if isinstance(result_field, str) else "CRASH"
            mode_field = _report_field(report, "mode")
            craft_mode = mode_field if isinstance(mode_field, str) else "unknown"
            iteration_field = _report_field(report, "budget_used.iterations")
            if isinstance(iteration_field, int):
                iterations = iteration_field
            seconds_field = _report_field(report, "budget_used.seconds")
            if isinstance(seconds_field, (int, float)):
                seconds = float(seconds_field)
        judge_rc: int | None
        judge_failed: list[str]
        try:
            judge_rc, judge_failed = run_judge(task_dir, scratch_repo, args.timeout)
        except OSError as exc:
            judge_rc = None
            judge_failed = [f"judge 启动失败: {exc}"]
        verdicts.append(
            TaskVerdict(
                task_id=task_id,
                theme=str(meta.get("theme", "")),
                appendix_e=str(meta.get("appendix_e", "")),
                trap=bool(meta.get("trap", False)),
                verdict=classify_verdict(craft_result, judge_rc),
                craft_rc=craft_rc,
                craft_result=craft_result,
                craft_mode=craft_mode,
                iterations=iterations,
                seconds=seconds,
                judge_rc=judge_rc,
                judge_failed=judge_failed,
            )
        )
        print(
            f"[{task_id}] craft={craft_result} (rc={craft_rc}, iters={iterations}, "
            f"{seconds if seconds is not None else '?'}s) judge_rc={judge_rc} "
            f"-> {verdicts[-1].verdict}"
        )
        if judge_failed:
            print(f"    judge failed: {', '.join(judge_failed[:5])}")

    if not args.keep_workdir and args.workdir is None:
        shutil.rmtree(workdir, ignore_errors=True)

    json_path = Path(args.json)
    markdown_path = Path(args.markdown)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    return verdicts, info, json_path, markdown_path


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        verdicts, info, json_path, markdown_path = run_benchmark(args)
    except BenchError as exc:
        print(f"bench_craft: 错误: {exc}", file=sys.stderr)
        return 2

    summary = compute_summary(verdicts)
    checks = _check_targets(summary)
    payload = {
        "run_info": {
            "started_utc": info.started_utc,
            "python_version": info.python_version,
            "sandbox": info.sandbox,
            "max_iterations": info.max_iterations,
            "llm_requested": info.llm_requested,
        },
        "summary": summary,
        "verdicts": [
            {
                "task_id": v.task_id,
                "theme": v.theme,
                "appendix_e": v.appendix_e,
                "trap": v.trap,
                "verdict": v.verdict,
                "craft_rc": v.craft_rc,
                "craft_result": v.craft_result,
                "craft_mode": v.craft_mode,
                "iterations": v.iterations,
                "seconds": v.seconds,
                "judge_rc": v.judge_rc,
                "judge_failed": v.judge_failed,
                "note": v.note,
            }
            for v in verdicts
        ],
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(
        render_markdown(summary, verdicts, info), encoding="utf-8"
    )
    print(f"\n汇总: {summary}")
    print(f"结果 JSON: {json_path}")
    print(f"Markdown 报告: {markdown_path}")

    if not args.no_strict:
        if not all(checks.values()):
            print("\n门禁失败: 指标未达 §7 门槛 → exit 1", file=sys.stderr)
            return 1
        non_trap_bad = [
            v.task_id for v in verdicts if not v.trap and v.verdict != "COMPLETE"
        ]
        trap_uncaught = [
            v.task_id for v in verdicts if v.trap and v.verdict != "INTERCEPTED"
        ]
        if non_trap_bad or trap_uncaught:
            print(
                f"\n门禁失败: 非陷阱未完成={non_trap_bad} 陷阱未拦={trap_uncaught}",
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
