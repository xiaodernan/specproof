"""specproof craft — SpecCraft M1 deterministic skeleton (design doc 附录 A).

Subcommands: plan / run / resume / explain / accept. `accept` (M5/W35)
re-runs the SpecCraft → SpecProof closure from a durable agent job
(craft/accept.py): internal gates → real SpecProof verification →
Merge Certificate (or rollback + rejection notice).

Honesty notes:
- LLM planning/diagnosis degrades per §9 to the rule-based planner when no
  usable key exists; everything is then labelled mode=deterministic.
- Fix rules are EXPLICITLY injected via --fix-module (a Python module
  exporting FIXES: dict[str, Callable]) — that is the design §4.4 "显式注入
  fix 函数". Without one, failing steps report FAILED honestly.
- The M3 self-verify hard gate (craft/verify.py) runs by default before
  delivery: secret/canary scan + Java contract checkers. --no-self-verify
  skips it and marks report.self_verify.status = skipped.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

import click

from craft.accept import craft_accept, persist_accept_result, requirement_text_from_job_spec
from craft.budget import Budget, BudgetError
from craft.llm import LLMClient, LLMUnavailableError
from craft.loop import CraftLoop, CraftLoopError, FixFunction
from craft.planner import CraftModeError, CraftPlanError, Plan, compile_plan
from craft.schemas import ChangeBundle, TestResult
from craft.spec import SpecParseError, parse_spec


def _llm_desired(use_llm: bool | None) -> tuple[bool, str]:
    """Tristate --llm/--no-llm -> (llm_active, note).

    None (default): LLM when a usable key exists, else deterministic with an
    honest 'LLM unavailable ... falling back to deterministic' note.
    False: deterministic only. True: LLM requested — still degrades with the
    same honest note when no usable key exists (never a fake LLM run).
    """
    if use_llm is False:
        return False, "确定性规则模式 (--no-llm)"
    try:
        client = LLMClient()
    except LLMUnavailableError as exc:
        return False, f"LLM unavailable: {exc} — falling back to deterministic"
    if client.available:
        return True, "LLM 模式 (providers/openai_compatible, 网关 deepseek-v4-pro)"
    return (
        False,
        "LLM unavailable: "
        + client.unavailable_reason()
        + " — falling back to deterministic",
    )


def _meter_craft_terminal(job_id: str, report: dict[str, Any]) -> None:
    """Best-effort billing event for a craft job's terminal state.

    Industrialization phase 6 (BILLING_DESIGN.md §2): one job_craft unit
    per job once the loop reaches a terminal state; the LLM token classes
    are metered separately through the TokenBudget usage listener
    (providers/budget.py). Tenant attribution comes from the
    request-scoped tenant context when the command runs inside the
    multi-tenant API process; standalone CLI runs have no tenant scope and
    emit nothing (billing is opt-in anyway — with no
    SPECPROOF_BILLING_URL every hook is a no-op).
    """
    try:
        from storage.billing import meter_craft_job_terminal
        from storage.tenant_scope import current_scope

        scope = current_scope()
        if scope is None or not scope.tenant_id:
            return
        status = "succeeded" if report.get("result") == "DONE" else "failed"
        meter_craft_job_terminal(scope.tenant_id, job_id, status)
    except Exception:  # noqa: BLE001 — billing must never break craft
        logging.getLogger(__name__).warning(
            "billing craft event dropped", exc_info=True,
        )


def _load_fix_registry(
    module_spec: str | None, base_dir: Path | None = None
) -> dict[str, FixFunction]:
    """Load explicitly injected fix rules (module name or .py file path).

    Relative file paths are resolved against base_dir (the --repo root).
    """
    if not module_spec:
        return {}
    candidate = Path(module_spec)
    if not candidate.is_absolute() and base_dir is not None:
        candidate = base_dir / candidate
    if candidate.suffix == ".py" or candidate.is_file():
        if not candidate.is_file():
            raise click.ClickException("fix 模块文件不存在: " + module_spec)
        module_name = "specproof_craft_fixes_" + candidate.stem
        spec = importlib.util.spec_from_file_location(module_name, candidate)
        if spec is None or spec.loader is None:
            raise click.ClickException("无法加载 fix 模块文件: " + module_spec)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    else:
        try:
            module = importlib.import_module(module_spec)
        except ImportError as exc:
            raise click.ClickException(
                "fix 模块导入失败: " + module_spec + " (" + str(exc) + ")"
            ) from exc
    fixes = getattr(module, "FIXES", None)
    if not isinstance(fixes, dict):
        raise click.ClickException("fix 模块 " + module_spec + " 未导出 FIXES: dict[str, Callable]")
    registry: dict[str, FixFunction] = {}
    for key, fix in fixes.items():
        if not isinstance(key, str) or not callable(fix):
            raise click.ClickException(
                "FIXES 的键必须为 str、值为可调用对象 (发现 " + repr(key) + ")"
            )
        registry[key] = fix
    return registry


def _compact(value: object, limit: int = 200) -> object:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "..."
    return value


class _StreamEcho:
    """Terminal sink for LLM content deltas (卷 XXI §21.3).

    TTY: every chunk is echoed immediately (no newline) and flushed so
    tokens appear as they arrive. Non-TTY (pipes / CI logs): chunks are
    buffered and echoed line by line so logs stay readable.
    """

    def __init__(self) -> None:
        self._tty = bool(getattr(sys.stdout, "isatty", lambda: False)())
        self._buffer = ""
        self._started = False

    def write(self, piece: str) -> None:
        if not piece:
            return
        if not self._started:
            click.echo("[LLM 流式] ", nl=False)
            self._started = True
        if self._tty:
            click.echo(piece, nl=False)
            sys.stdout.flush()
            return
        self._buffer += piece
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            click.echo(line)
            self._buffer = self._buffer.lstrip("\r")

    def flush(self) -> None:
        if self._buffer:
            click.echo(self._buffer)
            self._buffer = ""
        if self._started:
            click.echo("")


def _echo_stream_modes(report: dict[str, Any]) -> None:
    """Honest per-call stream annotation from the usage ledger."""
    usage = report.get("llm_usage")
    if not isinstance(usage, dict):
        return
    detail = usage.get("calls_detail")
    if not isinstance(detail, list):
        return
    modes = [
        f"{entry.get('label')}={entry.get('stream_mode', 'off')}"
        for entry in detail
        if isinstance(entry, dict)
    ]
    if modes:
        click.echo("stream_modes: " + ", ".join(modes))


def _echo_plan(plan: Plan, plan_path: Path | None, note: str) -> None:
    click.echo("SpecCraft 计划 — " + plan.task_title)
    click.echo("mode=" + plan.mode + "  (" + note + ")")
    if plan.llm_fallback_reason:
        click.echo("llm_fallback_reason=" + plan.llm_fallback_reason)
    for step in plan.steps:
        criteria = step.success_criteria
        targets = ",".join(step.target_files) or "-"
        suffix = "(" + criteria.value + ")" if criteria.value else ""
        click.echo(
            "  " + step.id + " [" + step.kind + "] " + step.intent
            + " | target=" + targets + " | criteria=" + criteria.type + suffix
        )
    click.echo("risk=" + str(plan.risk_classification))
    click.echo("budget_alloc=" + str(plan.budget_alloc))
    if plan_path is not None:
        click.echo("plan.json → " + str(plan_path))


def _echo_report(report: dict[str, Any], artifact_dir: Path) -> None:
    click.echo(
        "job_id=" + str(report["job_id"]) + "  mode=" + str(report["mode"])
        + "  result=" + str(report["result"])
    )
    for step in report["steps"]:
        evidence = {key: _compact(value) for key, value in step["evidence"].items()}
        click.echo(
            "  " + str(step["id"]) + " [" + str(step["kind"]) + "] " + str(step["status"])
            + " (iterations=" + str(step["iterations"]) + ") evidence=" + str(evidence)
        )
    click.echo("diff_stat=" + str(report["diff_stat"]))
    gates = report.get("gates")
    if isinstance(gates, dict):
        click.echo("gates=" + str(gates.get("summary", "")))
    click.echo("self_verify=" + str(report["self_verify"]))
    self_verify = report.get("self_verify")
    if isinstance(self_verify, dict):
        click.echo(
            "self_verify.status=" + str(self_verify.get("status"))
            + "  findings=" + str(len(self_verify.get("findings") or []))
        )
    click.echo("budget_used=" + str(report["budget_used"]))
    usage = report.get("llm_usage")
    if isinstance(usage, dict):
        click.echo(
            "llm_usage="
            + str(
                {
                    "calls": usage.get("calls"),
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "reasoning_tokens": usage.get("reasoning_tokens"),
                    "cache_hit_tokens": usage.get("prompt_cache_hit_tokens"),
                    "cache_miss_tokens": usage.get("prompt_cache_miss_tokens"),
                    "budget": usage.get("budget"),
                }
            )
        )
    if report.get("llm_fallback_reason"):
        click.echo("llm_fallback_reason=" + str(report["llm_fallback_reason"]))
    click.echo("产物目录: " + str(artifact_dir))
    click.echo("续跑: specproof craft resume --job " + str(report["job_id"]) + " --repo <repo>")


@click.group(name="craft")
def craft_cmd() -> None:
    """SpecCraft — 自主开发 Agent (plan/run 支持 LLM 规划与诊断, 无 key 自动降级确定性)."""


@craft_cmd.command("plan")
@click.argument("spec", metavar="SPEC")
@click.option(
    "--repo",
    default=".",
    show_default=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="仓库路径 (计划输出与工作目录)",
)
@click.option(
    "--llm/--no-llm",
    "use_llm",
    default=None,
    help="LLM 规划 (默认: 有 LLM_API_KEY 则开启, 否则确定性)",
)
@click.option(
    "--output",
    default=None,
    type=click.Path(file_okay=False, path_type=Path),
    help="plan.json 输出目录 (默认 <repo>/.specraft)",
)
def craft_plan(spec: str, repo: Path, use_llm: bool | None, output: Path | None) -> None:
    """生成计划并写出 plan.json。SPEC 可为纯文本 / JSON / spec 文件路径。"""
    llm_active, note = _llm_desired(use_llm)
    try:
        task = parse_spec(spec, cwd=repo)
        budget = Budget.from_env()
        client = LLMClient() if llm_active else None
        plan = compile_plan(
            task, mode="llm" if llm_active else "deterministic", budget=budget, client=client
        )
    except (SpecParseError, BudgetError, CraftModeError) as exc:
        raise click.ClickException(str(exc)) from exc
    if plan.llm_fallback_reason:
        note = "LLM 计划失败, 已退回确定性: " + plan.llm_fallback_reason
    out_dir = output if output is not None else repo / ".specraft"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        plan.save(out_dir / "plan.json")
    except (OSError, CraftPlanError) as exc:
        raise click.ClickException("无法写出计划: " + str(exc)) from exc
    _echo_plan(plan, out_dir / "plan.json", note)


@craft_cmd.command("run")
@click.argument("spec", metavar="SPEC")
@click.option(
    "--repo",
    default=".",
    show_default=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="仓库路径 (工作目录与产物根)",
)
@click.option(
    "--max-iterations",
    type=int,
    default=None,
    help="迭代上限 (覆盖 CRAFT_MAX_ITERATIONS)",
)
@click.option(
    "--budget-tokens",
    type=int,
    default=None,
    help="token 预算 (LLM 调用闸门, 覆盖 CRAFT_TOKEN_BUDGET, 默认 500000)",
)
@click.option(
    "--timeout",
    type=int,
    default=None,
    metavar="MIN",
    help="任务时间预算, 分钟 (覆盖 CRAFT_TIMEOUT_MINUTES)",
)
@click.option(
    "--llm/--no-llm",
    "use_llm",
    default=None,
    help="LLM 规划与诊断 (默认: 有 LLM_API_KEY 则开启, 否则确定性)",
)
@click.option(
    "--self-verify/--no-self-verify",
    "self_verify_enabled",
    default=True,
    help="交付前自校验硬门 (M3): 密钥/canary 扫描 + Java 契约检查器, "
    "默认开启; --no-self-verify 跳过并在 report.self_verify 标注 skipped",
)
@click.option("--dry-run", is_flag=True, default=False, help="只输出计划, 不执行、不落产物")
@click.option(
    "--fix-module",
    default=None,
    metavar="MODULE",
    help="注入确定性 fix 规则的 Python 模块 (需导出 FIXES: dict[str, Callable])",
)
@click.option(
    "--stream/--no-stream",
    "stream",
    default=False,
    help="规划与诊断的 token 级流式输出到终端 (无 TTY 自动逐行; "
    "Ctrl-C 落 checkpoint 后退出码 130); 默认 --no-stream 保持现状",
)
def craft_run(
    spec: str,
    repo: Path,
    max_iterations: int | None,
    budget_tokens: int | None,
    timeout: int | None,
    use_llm: bool | None,
    self_verify_enabled: bool,
    dry_run: bool,
    fix_module: str | None,
    stream: bool,
) -> None:
    """执行 SpecCraft 计划 (plan → execute → verify 循环)。"""
    llm_active, note = _llm_desired(use_llm)
    try:
        task = parse_spec(spec, cwd=repo)
        budget = Budget.from_env().with_overrides(
            max_iterations=max_iterations,
            token_budget=budget_tokens,
            timeout_minutes=timeout,
        )
        client = LLMClient(token_budget=budget_tokens) if llm_active else None
        plan = compile_plan(
            task, mode="llm" if llm_active else "deterministic", budget=budget, client=client
        )
    except (SpecParseError, BudgetError, CraftModeError) as exc:
        raise click.ClickException(str(exc)) from exc
    if dry_run:
        click.echo("--dry-run: 仅生成计划, 不执行")
        _echo_plan(plan, None, note)
        return
    click.echo(note)
    if plan.llm_fallback_reason:
        click.echo("LLM 计划失败, 已退回确定性: " + plan.llm_fallback_reason)
    if not self_verify_enabled:
        click.echo(
            "自校验已跳过 (--no-self-verify): report.self_verify.status=skipped"
        )
    fix_registry = _load_fix_registry(fix_module, base_dir=repo)
    loop = CraftLoop(
        task,
        plan,
        repo,
        budget=budget,
        fix_registry=fix_registry,
        client=client,
        skip_self_verify=not self_verify_enabled,
    )
    sink = None
    if stream:
        if client is None:
            click.echo("--stream: 无可用 LLM (无 key), 无流式输出, 按确定性模式执行")
        else:
            sink = _StreamEcho()
            client.stream_hook = sink.write
    try:
        report = loop.run()
    except KeyboardInterrupt:
        loop.interrupt_checkpoint()
        if sink is not None:
            sink.flush()
        click.echo("")
        click.echo("已中断 (Ctrl-C): 当前状态已写入 checkpoint, memory.json 已落盘")
        click.echo(f"续跑: specproof craft resume --job {loop.job_id} --repo {repo}")
        sys.exit(130)
    _meter_craft_terminal(loop.job_id, report)
    if sink is not None:
        sink.flush()
        _echo_stream_modes(report)
    _echo_report(report, loop.artifact_dir)
    if report["result"] != "DONE":
        sys.exit(1)


@craft_cmd.command("resume")
@click.option("--job", "job_id", required=True, metavar="JOB_ID", help="要续跑的作业 id")
@click.option(
    "--repo",
    default=".",
    show_default=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="仓库路径 (读取 <repo>/.specraft/jobs/JOB_ID)",
)
@click.option("--max-iterations", type=int, default=None, help="续跑轮次的迭代上限")
@click.option(
    "--fix-module",
    default=None,
    metavar="MODULE",
    help="注入确定性 fix 规则的 Python 模块",
)
def craft_resume(
    job_id: str, repo: Path, max_iterations: int | None, fix_module: str | None
) -> None:
    """从 .specraft/jobs/JOB_ID/checkpoint.json 续跑 (最后一个绿步骤之后)。"""
    artifact_dir = repo / ".specraft" / "jobs" / job_id
    if not (artifact_dir / "checkpoint.json").is_file():
        raise click.ClickException(
            "未找到可恢复的作业产物: " + str(artifact_dir) + " (checkpoint.json 不存在)"
        )
    budget = Budget.from_env()
    if max_iterations is not None:
        budget = budget.with_overrides(max_iterations=max_iterations)
    try:
        loop = CraftLoop.from_checkpoint(
            artifact_dir,
            fix_registry=_load_fix_registry(fix_module, base_dir=repo),
            budget=budget,
        )
    except (CraftLoopError, CraftPlanError, BudgetError) as exc:
        raise click.ClickException("恢复失败: " + str(exc)) from exc
    try:
        report = loop.run()
    except KeyboardInterrupt:
        loop.interrupt_checkpoint()
        click.echo("已中断 (Ctrl-C): 当前状态已写入 checkpoint, memory.json 已落盘")
        click.echo(f"续跑: specproof craft resume --job {loop.job_id} --repo {repo}")
        sys.exit(130)
    _meter_craft_terminal(loop.job_id, report)
    _echo_report(report, loop.artifact_dir)
    if report["result"] != "DONE":
        sys.exit(1)


@craft_cmd.command("explain")
@click.argument("step_id", metavar="STEP_ID")
@click.option("--job", "job_id", required=True, metavar="JOB_ID", help="作业 id")
@click.option(
    "--repo",
    default=".",
    show_default=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="仓库路径 (读取 <repo>/.specraft/jobs/JOB_ID)",
)
def craft_explain(step_id: str, job_id: str, repo: Path) -> None:
    """解释某一步骤的决策依据 (计划 + 该步骤的 checkpoint 记录, 审计可读)。"""
    artifact_dir = repo / ".specraft" / "jobs" / job_id
    report_path = artifact_dir / "report.json"
    checkpoint_path = artifact_dir / "checkpoint.json"
    if not report_path.is_file():
        raise click.ClickException("该作业尚无终态报告: " + str(report_path))
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        checkpoint = (
            json.loads(checkpoint_path.read_text(encoding="utf-8"))
            if checkpoint_path.is_file()
            else {}
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise click.ClickException("读取作业产物失败: " + str(exc)) from exc
    steps = report.get("steps", []) if isinstance(report, dict) else []
    found = next((s for s in steps if isinstance(s, dict) and s.get("id") == step_id), None)
    if found is None:
        raise click.ClickException("步骤 " + step_id + " 不存在于作业 " + job_id + " 的 report")
    entries: list[object] = []
    if isinstance(checkpoint, dict):
        raw = checkpoint.get("entries", [])
        entries = [
            entry for entry in raw if isinstance(entry, dict) and entry.get("step_id") == step_id
        ]
    click.echo(
        json.dumps(
            {"job_id": job_id, "step": found, "checkpoint_entries": entries},
            ensure_ascii=False,
            indent=2,
        )
    )


def _bundle_from_job_report(job_id: str, report: dict[str, Any]) -> ChangeBundle:
    """Rebuild the ChangeBundle projection from a stored loop report.

    diff_stat.files is the authoritative changed-file list; test_green /
    compile step evidence projects into TestResult entries verbatim (the
    exit codes are the recorded facts, never re-derived).
    """
    diff_stat = report.get("diff_stat")
    files = [
        str(path) for path in (diff_stat.get("files") or []) if isinstance(path, str)
    ]
    test_results: list[TestResult] = []
    steps = report.get("steps") or []
    for step in steps:
        if not isinstance(step, dict):
            continue
        evidence = step.get("evidence")
        if not isinstance(evidence, dict):
            continue
        check = evidence.get("check")
        exit_code = evidence.get("exit_code")
        if not isinstance(exit_code, int):
            continue
        if check == "test_green":
            test_results.append(
                TestResult(
                    command="python -m pytest -q",
                    exit_code=exit_code,
                    summary=str(evidence.get("output_tail", ""))[:500],
                    passed=exit_code == 0,
                )
            )
        elif check == "compile":
            test_results.append(
                TestResult(
                    command="python -m compileall -q",
                    exit_code=exit_code,
                    summary=str(evidence.get("output_tail", ""))[:500],
                    passed=exit_code == 0,
                )
            )
    return ChangeBundle(task_id=job_id, changed_files=files, test_results=test_results)


@craft_cmd.command("accept")
@click.option("--job", "job_id", required=True, metavar="JOB_ID", help="要验收的作业 id")
@click.option(
    "--base", "base_sha", required=True, metavar="SHA", help="验收基线 (base_sha, 回滚目标)"
)
@click.option(
    "--repo",
    default=".",
    show_default=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="仓库路径 (验收对象与证书输出根)",
)
@click.option(
    "--db",
    "db_path",
    default=None,
    metavar="PATH",
    help="AgentJobStore sqlite 文件路径; 缺省使用内存 store (程序化测试用)",
)
def craft_accept_cmd(job_id: str, base_sha: str, repo: Path, db_path: str | None) -> None:
    """重新运行 SpecCraft → SpecProof 验收闭环 (M5, craft/accept.py)。

    从 AgentJobStore 载入作业 (spec_text + report), 重建 ChangeBundle 后
    走完整闭环: 内部门禁 → SpecProof 独立验证 → Merge Certificate (或回滚 +
    拒绝通知)。退出码: 0 VERIFIED / 1 BLOCKED / 2 ERROR。
    """
    from storage.agent_jobs import (
        AgentJobStoreError,
        InMemoryAgentJobStore,
        SqliteAgentJobStore,
    )

    store = SqliteAgentJobStore(db_path) if db_path else InMemoryAgentJobStore()
    try:
        job = store.get(job_id)
    except AgentJobStoreError as exc:
        click.echo("ERROR: 作业读取失败: " + str(exc), err=True)
        sys.exit(2)
    if job is None:
        click.echo("ERROR: 作业不存在: " + job_id, err=True)
        sys.exit(2)

    repo_resolved = repo.resolve()
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_resolved), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        head_sha = proc.stdout.strip()
    except Exception:  # noqa: BLE001 — resolution failure is an ERROR exit
        head_sha = ""
    if not head_sha:
        click.echo("ERROR: 无法解析仓库 HEAD: " + str(repo_resolved), err=True)
        sys.exit(2)

    report: dict[str, Any] = {}
    if job.result_json:
        try:
            parsed = json.loads(job.result_json)
            if isinstance(parsed, dict):
                report = parsed
        except json.JSONDecodeError:
            report = {}
    bundle = _bundle_from_job_report(job_id, report)
    spec_text = requirement_text_from_job_spec(job.spec_text)

    click.echo(
        "SpecCraft accept 闭环 — job=" + job_id + " base=" + base_sha + " head=" + head_sha
    )
    result = craft_accept(
        bundle, spec_text, repo_resolved, base_sha, head_sha, job_id=job_id
    )

    # W35.1 post-hoc projection: attach_accept_result is the single
    # deliberate write a terminal (succeeded/failed) job accepts — first
    # attach wins, repeats are idempotent. Non-terminal targets are
    # swallowed here: the certificate on disk and this stdout verdict
    # remain the authoritative record.
    attached = persist_accept_result(store, job.id, result)
    if attached:
        click.echo("accept_result 已写入作业投影 (accept_json)")
    else:
        click.echo("accept_result 未写入作业投影 (作业非 succeeded/failed 终态)")

    gates = result.gates_report or {}
    click.echo("gates_overall=" + str(gates.get("overall")))
    click.echo("findings=" + str(len(result.findings)))
    click.echo("rolled_back=" + str(result.rolled_back))
    click.echo("VERDICT: " + result.verdict)
    if result.certificate_path:
        click.echo("certificate: " + result.certificate_path)
    if result.rejection_notice_path:
        click.echo("rejection notice: " + result.rejection_notice_path)
    if result.verdict == "VERIFIED":
        sys.exit(0)
    if result.verdict == "BLOCKED":
        sys.exit(1)
    sys.exit(2)
