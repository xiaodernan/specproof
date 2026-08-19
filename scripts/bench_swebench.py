"""Honest SWE-bench-Lite harness for SpecCraft's deterministic pipeline.

What this measures (and what it does not) — see docs/eval/SWEBENCH_PLAN.md.
Short version: the harness runs the REAL deterministic craft loop
(plan -> execute -> verify) against SWE-bench-Lite style instances, applies
each instance's test_patch, replays its FAIL_TO_PASS / PASS_TO_PASS tests
and records `resolved: true` ONLY when craft converged AND every test
passed. Every other outcome is `status=unresolved` with a non-empty
`reason` — the harness never fabricates a resolution.

Deterministic-mode honesty (design contract):
- craft's M1 loop only fixes through EXPLICITLY INJECTED fix rules
  (fix_registry / --fix-module). The bundled sample ships exactly one
  hardcoded rule for `specproof__toycalc-double-1`; real SWE-bench
  instance ids have no rules, so they are recorded unresolved with
  "no fix produced" (craft stage SKIPPED) instead of pretending.
- checkout / patch / test-run failures each become unresolved records with
  the real error on record.

Offline by default: `python scripts/bench_swebench.py --offline` runs the
bundled toy sample (scripts/swebench_sample/) with no network and no
Docker. Real runs need the dataset JSON (scripts/fetch_swebench_lite.ps1)
plus per-instance git checkouts — see the plan doc for the manual steps.

CLI: --tasks N (default 10) --dataset <path|hf-id>
     --output docs/eval/swebench-results.json --mode deterministic
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from craft.budget import Budget  # noqa: E402
from craft.editor import Editor  # noqa: E402
from craft.loop import CraftLoop, FixFunction  # noqa: E402
from craft.planner import Step, compile_plan, write_json_atomic  # noqa: E402
from craft.spec import TaskSpec  # noqa: E402

SAMPLE_DIR = Path(__file__).resolve().parent / "swebench_sample"
SAMPLE_INSTANCES = SAMPLE_DIR / "instances.json"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "eval" / "swebench-results.json"
SCHEMA_VERSION = "1.0"
_ROWS_API = "https://datasets-server.huggingface.co/rows"


def _fix_toycalc_double(editor: Editor, step: Step, diagnosis: str) -> list[str]:
    """Hardcoded fix for the bundled sample instance ONLY.

    The toy bug is double() computing x / 2 instead of x * 2. This rule is
    keyed by the exact sample instance id below, so it can never match a
    real SWE-bench instance id.
    """
    editor.apply_edit("calc.py", "return x / 2", "return x * 2")
    return ["calc.py"]


# Keyed by EXACT instance_id. Real SWE-bench ids are never present, so real
# instances always take the honest "no fix produced" path.
SAMPLE_FIX_REGISTRY: dict[str, dict[str, FixFunction]] = {
    "specproof__toycalc-double-1": {"test": _fix_toycalc_double},
}

_REQUIRED_INSTANCE_FIELDS = (
    "instance_id",
    "repo",
    "base_commit",
    "problem_statement",
    "test_patch",
    "FAIL_TO_PASS",
    "PASS_TO_PASS",
)


class HarnessError(RuntimeError):
    """Dataset / usage / environment problem (not an instance verdict)."""


class InstanceError(RuntimeError):
    """Per-instance failure; converted into an honest unresolved record."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="bench_swebench",
        description=(
            "诚实的 SWE-bench-Lite 评测 harness: 用 SpecCraft 确定性管道跑实例, "
            "应用 test_patch, 重放 FAIL_TO_PASS / PASS_TO_PASS, 只记录真实结果"
        ),
    )
    parser.add_argument(
        "--tasks", type=int, default=10, help="最多评估的实例数 (默认 10; 0=全部)"
    )
    parser.add_argument(
        "--dataset", default=None,
        help="SWE-bench-Lite 风格 JSON 路径, 或 HuggingFace 数据集 id (owner/name 形式)",
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT,
        help=f"结果 JSON 路径 (默认 {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--mode", choices=("deterministic",), default="deterministic",
        help="运行模式 (当前仅 deterministic; LLM agent 模式未实现, 传入其它值即拒绝)",
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="使用捆绑离线样例 (scripts/swebench_sample/), 无需网络/Docker",
    )
    parser.add_argument(
        "--repo-dir", type=Path, default=None,
        help="实例仓库缓存/checkout 目录 (默认系统临时目录; 持久缓存请显式指定)",
    )
    parser.add_argument(
        "--fix-module", type=Path, default=None,
        help="额外注入 fix 规则的 python 模块 (需导出 FIX_REGISTRY: {instance_id: {key: fn}})",
    )
    parser.add_argument(
        "--work-root", type=Path, default=None, help="临时工作区父目录 (默认系统临时目录)"
    )
    parser.add_argument("--keep-work", action="store_true", help="保留临时工作区 (调试)")
    parser.add_argument("--exec-timeout", type=int, default=300, help="每步命令超时 (秒)")
    parser.add_argument(
        "--max-iterations", type=int, default=12, help="craft 循环迭代预算"
    )
    return parser.parse_args(argv)


# -- dataset loading -------------------------------------------------------

def _hf_rows_url(dataset_id: str, offset: int, length: int) -> str:
    encoded = urllib.parse.quote(dataset_id, safe="")
    return (
        f"{_ROWS_API}?dataset={encoded}&config=default&split=test"
        f"&offset={offset}&length={length}"
    )


def _fetch_hf_rows(dataset_id: str, limit: int) -> list[dict[str, Any]]:
    """Fetch dataset rows through the HF datasets-server rows API.

    Proxies come from the standard environment (HTTPS_PROXY/HTTP_PROXY),
    matching scripts/fetch_swebench_lite.ps1. Any failure raises
    HarnessError with the offline fallback spelled out.
    """
    rows: list[dict[str, Any]] = []
    offset = 0
    total: int | None = None
    while True:
        remaining = total - offset if total is not None else 100
        length = min(100, max(remaining, 0))
        if limit > 0:
            length = min(length, limit - len(rows))
        if length <= 0:
            break
        url = _hf_rows_url(dataset_id, offset, length)
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                payload: Any = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise HarnessError(
                f"HF 数据集 {dataset_id!r} 拉取失败: {exc} — 离线方案: "
                "先 scripts/fetch_swebench_lite.ps1 生成本地 JSON 再 "
                "--dataset <文件>, 或 --offline 用捆绑样例"
            ) from exc
        if not isinstance(payload, dict):
            raise HarnessError(f"HF rows 响应顶层不是对象 ({url})")
        raw_total = payload.get("num_rows_total")
        if isinstance(raw_total, int) and raw_total > 0:
            total = raw_total
        raw_rows = payload.get("rows")
        if not isinstance(raw_rows, list):
            raise HarnessError(f"HF rows 响应缺少 rows 数组 ({url})")
        for entry in raw_rows:
            if isinstance(entry, dict):
                row = entry.get("row")
                if isinstance(row, dict):
                    rows.append(row)
        offset += length
        if len(raw_rows) < length:
            break
    if limit > 0:
        rows = rows[:limit]
    if not rows:
        raise HarnessError(f"HF 数据集 {dataset_id!r} 返回 0 行 (split=test 为空?)")
    return rows


def _read_dataset_file(path: Path) -> list[dict[str, Any]]:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessError(f"数据集文件无法读取/解析 ({path}): {exc}") from exc
    if isinstance(payload, list):
        raw_instances: list[object] = payload
    elif isinstance(payload, dict):
        raw_instances = []
        for key in ("data", "instances"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                raw_instances = candidate
                break
        if not raw_instances:
            raise HarnessError(
                f"数据集 JSON 顶层应为实例数组或 {{data|instances: [...]}} ({path})"
            )
    else:
        raise HarnessError(f"数据集 JSON 顶层类型错误 ({path})")
    return [entry for entry in raw_instances if isinstance(entry, dict)]


def _load_instances(
    dataset: str | None, offline: bool, tasks: int
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    if offline:
        path = SAMPLE_INSTANCES
        source: dict[str, str] = {"kind": "offline-sample", "path": str(path)}
        if not path.is_file():
            raise HarnessError(f"捆绑样例缺失: {path}")
        instances = _read_dataset_file(path)
    elif dataset is None:
        raise HarnessError(
            "缺少 --dataset 或 --offline: 请指定本地 JSON 路径、HuggingFace 数据集 id "
            "(如 princeton-nlp/SWE-bench_Lite), 或 --offline 运行捆绑样例"
        )
    else:
        candidate = Path(dataset)
        if candidate.is_file():
            source = {"kind": "file", "path": str(candidate)}
            instances = _read_dataset_file(candidate)
        elif "/" in dataset:
            source = {"kind": "hf-rows-api", "dataset": dataset}
            instances = _fetch_hf_rows(dataset, limit=tasks)
        else:
            raise HarnessError(
                f"--dataset {dataset!r} 既不是已存在的文件也不是 hf 数据集 id "
                "(owner/name 形式); 离线可 --offline"
            )
    if tasks > 0:
        instances = instances[:tasks]
    source_path = source.get("path")
    if isinstance(source_path, str):
        parent = Path(source_path).parent
        for instance in instances:
            repo = instance.get("repo")
            if isinstance(repo, str):
                resolved = parent / repo
                if resolved.exists():
                    instance["repo"] = str(resolved.resolve())
    return instances, source


def _normalize_node_list(value: object) -> list[str] | None:
    """SWE-bench node lists come in three shapes: a flat list (["a::t"]),
    nested bundles ([["a::t", "b::t"]]), or a JSON-encoded string of one
    of those (HF rows API quirk). All mean "all listed nodes must pass",
    so the harness normalizes to a flat ordered list. None = invalid."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if not isinstance(value, list):
        return None
    nodes: list[str] = []
    for item in value:
        if isinstance(item, str):
            nodes.append(item)
        elif isinstance(item, list) and all(isinstance(inner, str) for inner in item):
            nodes.extend(item)
        else:
            return None
    return nodes


def _validate_instance(entry: object, index: int) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(entry, dict):
        return None, f"instance[{index}] 不是 JSON 对象"
    missing = [key for key in _REQUIRED_INSTANCE_FIELDS if key not in entry]
    if missing:
        return None, f"instance[{index}] 缺少字段: {missing}"
    for key in ("instance_id", "repo", "base_commit", "problem_statement", "test_patch"):
        if not isinstance(entry[key], str):
            return None, f"instance[{index}].{key} 应为字符串"
    for key in ("FAIL_TO_PASS", "PASS_TO_PASS"):
        nodes = _normalize_node_list(entry[key])
        if nodes is None:
            return None, (
                f"instance[{index}].{key} 应为字符串数组 "
                "(或字符串数组的数组/JSON 字符串)"
            )
        entry[key] = nodes
    if not str(entry["instance_id"]).strip():
        return None, f"instance[{index}].instance_id 为空"
    return cast(dict[str, Any], entry), ""


# -- fix registry ----------------------------------------------------------

def _build_fix_registry(fix_module: Path | None) -> dict[str, dict[str, FixFunction]]:
    registry: dict[str, dict[str, FixFunction]] = dict(SAMPLE_FIX_REGISTRY)
    if fix_module is None:
        return registry
    spec = importlib.util.spec_from_file_location("swebench_bench_fix_module", fix_module)
    if spec is None or spec.loader is None:
        raise HarnessError(f"--fix-module 无法加载: {fix_module}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    extra = getattr(module, "FIX_REGISTRY", None)
    if not isinstance(extra, dict):
        raise HarnessError("--fix-module 必须导出 FIX_REGISTRY: {instance_id: {key: 可调用}}")
    for instance_id, rules in extra.items():
        if not isinstance(instance_id, str) or not isinstance(rules, dict):
            raise HarnessError(f"--fix-module FIX_REGISTRY[{instance_id!r}] 类型错误")
        for key, fix in rules.items():
            if not isinstance(key, str) or not callable(fix):
                raise HarnessError(
                    f"--fix-module FIX_REGISTRY[{instance_id!r}][{key!r}] 应为可调用 fix 函数"
                )
        registry[instance_id] = cast(dict[str, FixFunction], rules)
    return registry


# -- per-instance stages ---------------------------------------------------

def _safe_dirname(instance_id: str) -> str:
    cleaned = "".join("_" if ch in r'<>:"/\|?*' else ch for ch in instance_id)
    return cleaned.strip() or "instance"


def _is_git_dir(path: Path) -> bool:
    """True only when path ITSELF is a git checkout (not a subdir of one)."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if proc.returncode != 0:
        return False
    try:
        return Path(proc.stdout.strip()).resolve() == path.resolve()
    except OSError:
        return False


def _checkout_instance(
    instance: dict[str, Any], repo_dir: Path, work_root: Path
) -> tuple[Path, dict[str, str]]:
    """Create the temp workdir: git worktree from a local checkout, clone
    from a URL when allowed, or a plain copy for the bundled (non-git)
    sample. Every failure becomes InstanceError with the real reason."""
    repo_spec = str(instance["repo"])
    base_commit = str(instance["base_commit"])
    instance_id = str(instance["instance_id"])
    slug = repo_spec.rstrip("/").rsplit("/", 1)[-1] or instance_id
    source: Path | None = None
    local_candidate = Path(repo_spec)
    if local_candidate.exists():
        source = local_candidate
    else:
        cached = repo_dir / slug
        if cached.exists():
            source = cached
    if source is None:
        if repo_spec.startswith(("http://", "https://", "git://", "git@", "ssh://")):
            cached = repo_dir / slug
            try:
                cached.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    ["git", "clone", repo_spec, str(cached)],
                    capture_output=True, text=True, timeout=3600, check=True,
                )
            except subprocess.CalledProcessError as exc:
                tail = (exc.stderr or exc.stdout or "").strip()
                raise InstanceError(f"repo clone failed: {tail[-800:]}") from exc
            except subprocess.TimeoutExpired as exc:
                raise InstanceError("repo clone failed: 超时 (3600s)") from exc
            except OSError as exc:
                raise InstanceError(f"repo clone failed to start: {exc}") from exc
            source = cached
        else:
            raise InstanceError(
                f"repo source unavailable: {repo_spec!r} 不是本地路径也不是可克隆 URL; "
                "本地 checkout 请放到 --repo-dir 下 (目录名=slug) 或使用可克隆 URL"
            )
    target = work_root / _safe_dirname(instance_id)
    if _is_git_dir(source):
        try:
            subprocess.run(
                [
                    "git", "-C", str(source), "worktree", "add", "--detach",
                    str(target), base_commit,
                ],
                capture_output=True, text=True, timeout=600, check=True,
            )
        except subprocess.CalledProcessError as exc:
            tail = (exc.stderr or exc.stdout or "").strip()
            raise InstanceError(
                f"worktree 创建失败 (base_commit={base_commit}): {tail[-800:]} "
                "(本地 checkout 需包含该 commit 的完整历史)"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise InstanceError("worktree 创建超时 (600s)") from exc
        except OSError as exc:
            raise InstanceError(f"worktree 创建失败: {exc}") from exc
        info = {
            "method": "worktree",
            "source": str(source),
            "base_commit": base_commit,
            "detail": "git worktree add --detach",
        }
    else:
        try:
            shutil.copytree(source, target)
        except OSError as exc:
            raise InstanceError(f"样例/目录拷贝失败 ({source}): {exc}") from exc
        info = {
            "method": "copy",
            "source": str(source),
            "base_commit": base_commit,
            "detail": "非 git 目录直接拷贝 (捆绑样例无 git 历史; base_commit 为标注值)",
        }
    return target, info


def _cleanup_workdir(workdir: Path, checkout_info: dict[str, str]) -> None:
    if checkout_info.get("method") == "worktree":
        source = checkout_info.get("source")
        if source:
            subprocess.run(
                ["git", "-C", source, "worktree", "remove", "--force", str(workdir)],
                capture_output=True, text=True, timeout=60, check=False,
            )
            return
    shutil.rmtree(workdir, ignore_errors=True)


def _apply_test_patch(workdir: Path, patch_text: str) -> dict[str, Any]:
    patch_path = workdir / ".swebench-test.patch"
    try:
        patch_path.write_text(patch_text, encoding="utf-8", newline="\n")
    except OSError as exc:
        return {"applied": False, "error": f"test_patch 无法写入: {exc}"}
    last_error = ""
    for extra_args in (["--whitespace=nowarn"], ["--whitespace=nowarn", "--ignore-whitespace"]):
        try:
            proc = subprocess.run(
                ["git", "-C", str(workdir), "apply", *extra_args, str(patch_path)],
                capture_output=True, text=True, timeout=120, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            last_error = f"git apply 无法启动/超时: {exc}"
            continue
        if proc.returncode == 0:
            return {"applied": True, "error": ""}
        last_error = f"{proc.stdout}\n{proc.stderr}".strip()
    return {"applied": False, "error": f"test_patch 应用失败: {last_error[-800:]}"}


def _append_log(log_path: Path, text: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        if not text.endswith("\n"):
            handle.write("\n")


def _run_one_test(
    workdir: Path, node_id: str, timeout: int, log_path: Path
) -> dict[str, Any]:
    command = [
        sys.executable, "-m", "pytest", "-q", "--no-header",
        "-p", "no:cacheprovider", node_id,
    ]
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command, cwd=workdir, capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        tail = f"<timeout after {timeout}s>"
        _append_log(log_path, f"$ {' '.join(command)}\n{tail}")
        return {
            "test": node_id,
            "outcome": "error",
            "output_tail": tail,
            "seconds": round(time.monotonic() - started, 1),
        }
    combined = f"{proc.stdout}\n{proc.stderr}".rstrip()
    _append_log(
        log_path,
        f"$ {' '.join(command)}\n{combined}\n[exit {proc.returncode}]",
    )
    if proc.returncode == 0:
        outcome = "passed"
    elif proc.returncode == 5 or "no tests ran" in combined or "collected 0 items" in combined:
        outcome = "error"
    else:
        outcome = "failed"
    return {
        "test": node_id,
        "outcome": outcome,
        "output_tail": combined[-500:],
        "seconds": round(time.monotonic() - started, 1),
    }


def _craft_failure_reason(report: dict[str, Any]) -> str:
    steps = report.get("steps")
    if not isinstance(steps, list):
        return "craft 未收敛 (无步骤级原因记录)"
    for wanted in ("failed", "stuck"):
        for entry in steps:
            if not isinstance(entry, dict) or entry.get("status") != wanted:
                continue
            evidence = entry.get("evidence")
            if isinstance(evidence, dict):
                reason = evidence.get("reason")
                if isinstance(reason, str) and reason:
                    return f"步骤 {entry.get('id')} ({entry.get('kind')}): {reason}"
    for entry in steps:
        if not isinstance(entry, dict):
            continue
        evidence = entry.get("evidence")
        if isinstance(evidence, dict):
            reason = evidence.get("reason")
            if isinstance(reason, str) and reason:
                return f"步骤 {entry.get('id')} ({entry.get('kind')}): {reason}"
    return "craft 未收敛 (无步骤级原因记录)"


def _run_craft(
    instance: dict[str, Any],
    workdir: Path,
    fix_rules: dict[str, FixFunction],
    artifact_dir: Path,
    exec_timeout: int,
    max_iterations: int,
) -> dict[str, Any]:
    """Run the real deterministic craft loop in-memory (exec_mode=local)."""
    spec = TaskSpec(
        title=f"[{instance['instance_id']}] 修复缺陷 (SWE-bench)",
        description=str(instance["problem_statement"]),
        acceptance_criteria=["FAIL_TO_PASS 测试全部通过", "PASS_TO_PASS 测试全部通过"],
        forbidden_changes=[],
        affected_area_hint="",
    )
    plan = compile_plan(spec)
    loop = CraftLoop(
        spec,
        plan,
        workdir,
        job_id=f"swebench-{instance['instance_id']}",
        artifact_dir=artifact_dir,
        fix_registry=fix_rules,
        exec_mode="local",
        exec_timeout=exec_timeout,
        budget=Budget(max_iterations=max_iterations),
    )
    return loop.run()


def _record_template(instance_id: str) -> dict[str, Any]:
    return {
        "instance_id": instance_id,
        "status": "unresolved",
        "resolved": False,
        "reason": "",
        "stage": "setup",
        "repo": "",
        "base_commit": "",
        "problem_statement_head": "",
        "checkout": {},
        "craft": None,
        "test_patch": {"applied": False, "error": ""},
        "fail_to_pass": [],
        "pass_to_pass": [],
        "note": "",
        "logs": {},
    }


def _invalid_record(index: int, problem: str) -> dict[str, Any]:
    record = _record_template(f"<invalid-{index}>")
    record["reason"] = f"instance schema invalid: {problem}"
    return record


def _crash_record(instance_id: str, exc: Exception) -> dict[str, Any]:
    record = _record_template(instance_id)
    record["reason"] = (
        f"harness internal error ({type(exc).__name__}): {exc} — "
        "已按 unresolved 记录, 未声称 resolved"
    )
    return record


def run_instance(
    instance: dict[str, Any],
    *,
    repo_dir: Path,
    work_root: Path,
    logs_dir: Path,
    fix_registry: dict[str, dict[str, FixFunction]],
    exec_timeout: int,
    max_iterations: int,
) -> dict[str, Any]:
    instance_id = str(instance["instance_id"])
    instance_logs = logs_dir / _safe_dirname(instance_id)
    tests_log = instance_logs / "tests.log"
    record = _record_template(instance_id)
    record["repo"] = str(instance["repo"])
    record["base_commit"] = str(instance["base_commit"])
    record["problem_statement_head"] = str(instance["problem_statement"])[:300]
    record["logs"] = {"tests_log": str(tests_log)}

    def fail(stage: str, reason: str) -> dict[str, Any]:
        record["stage"] = stage
        record["reason"] = reason
        return record

    workdir: Path | None = None
    checkout_info: dict[str, str] = {}
    try:
        try:
            workdir, checkout_info = _checkout_instance(instance, repo_dir, work_root)
        except InstanceError as exc:
            return fail("setup", str(exc))
        record["checkout"] = checkout_info
        fix_rules = fix_registry.get(instance_id)
        if fix_rules is None:
            record["note"] = "fix_registry 为空: craft 管道 SKIPPED (确定性模式绝不虚构修复)"
            return fail(
                "craft",
                f"no fix produced: 没有为 {instance_id} 注入确定性 fix 规则 "
                "(fix_registry 为空 → craft 管道 SKIPPED); 未运行测试, 未声称 resolved",
            )
        craft_artifact_dir = instance_logs / "craft"
        try:
            report = _run_craft(
                instance, workdir, fix_rules, craft_artifact_dir, exec_timeout, max_iterations
            )
        except Exception as exc:
            record["craft"] = {
                "result": "CRASH",
                "error": f"{type(exc).__name__}: {exc}",
                "report_path": str(craft_artifact_dir / "report.json"),
            }
            return fail("craft", f"craft 执行异常: {type(exc).__name__}: {exc}")
        craft_result = str(report.get("result", "CRASH"))
        diff_stat = report.get("diff_stat")
        edits = (
            sorted(str(path) for path in diff_stat.get("files", []))
            if isinstance(diff_stat, dict)
            else []
        )
        budget_used = report.get("budget_used")
        record["craft"] = {
            "result": craft_result,
            "mode": report.get("mode"),
            "edits": edits,
            "iterations": budget_used.get("iterations") if isinstance(budget_used, dict) else None,
            "seconds": budget_used.get("seconds") if isinstance(budget_used, dict) else None,
            "report_path": str(craft_artifact_dir / "report.json"),
        }
        if craft_result != "DONE":
            return fail("craft", f"craft 未收敛 ({craft_result}): {_craft_failure_reason(report)}")
        patch_info = _apply_test_patch(workdir, str(instance["test_patch"]))
        record["test_patch"] = patch_info
        if not patch_info["applied"]:
            return fail("test_patch", str(patch_info["error"]))
        fail_to_pass = [str(node) for node in instance["FAIL_TO_PASS"]]
        pass_to_pass = [str(node) for node in instance["PASS_TO_PASS"]]
        if not fail_to_pass:
            return fail("tests", "FAIL_TO_PASS 为空: 没有可判定的目标测试")
        record["fail_to_pass"] = [
            _run_one_test(workdir, node, exec_timeout, tests_log) for node in fail_to_pass
        ]
        record["pass_to_pass"] = [
            _run_one_test(workdir, node, exec_timeout, tests_log) for node in pass_to_pass
        ]
        record["stage"] = "tests"
        failed_f2p = [r["test"] for r in record["fail_to_pass"] if r["outcome"] != "passed"]
        if failed_f2p:
            return fail(
                "tests",
                f"FAIL_TO_PASS 未通过: {failed_f2p} (craft 已 DONE 但修复未满足隐藏测试)",
            )
        failed_p2p = [r["test"] for r in record["pass_to_pass"] if r["outcome"] != "passed"]
        if failed_p2p:
            return fail("tests", f"PASS_TO_PASS 回归: {failed_p2p}")
        if not edits:
            record["note"] = (
                "craft 未产生任何编辑但全部目标测试通过 "
                "(测试可能本就通过; 见 SWEBENCH_PLAN.md 的限制说明)"
            )
        record["status"] = "resolved"
        record["resolved"] = True
        record["reason"] = ""
        return record
    finally:
        if workdir is not None:
            _cleanup_workdir(workdir, checkout_info)


# -- results ---------------------------------------------------------------

def _write_results(payload: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(output_path, payload)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        instances, source = _load_instances(args.dataset, args.offline, args.tasks)
        registry = _build_fix_registry(args.fix_module)
    except HarnessError as exc:
        print(f"bench_swebench: 错误: {exc}", file=sys.stderr)
        print("提示: 离线验证可用 --offline (捆绑样例, 无需网络/Docker)", file=sys.stderr)
        return 2

    repo_dir = args.repo_dir if args.repo_dir is not None else (
        Path(tempfile.gettempdir()) / "specproof-swebench-repos"
    )
    explicit_work_root = args.work_root is not None
    work_root = args.work_root if args.work_root is not None else Path(
        tempfile.mkdtemp(prefix="swebench-work-")
    )
    logs_dir = args.output.parent / "swebench-logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    total = len(instances)
    for index, entry in enumerate(instances):
        instance, problem = _validate_instance(entry, index)
        if instance is None:
            record = _invalid_record(index, problem)
        else:
            try:
                record = run_instance(
                    instance,
                    repo_dir=repo_dir,
                    work_root=work_root,
                    logs_dir=logs_dir,
                    fix_registry=registry,
                    exec_timeout=args.exec_timeout,
                    max_iterations=args.max_iterations,
                )
            except Exception as exc:
                record = _crash_record(str(instance.get("instance_id")), exc)
        records.append(record)
        if record["resolved"]:
            print(f"[{index + 1}/{total}] {record['instance_id']} -> resolved")
        else:
            print(
                f"[{index + 1}/{total}] {record['instance_id']} -> unresolved "
                f"({record['stage']}): {record['reason'][:160]}"
            )

    if not args.keep_work and not explicit_work_root:
        shutil.rmtree(work_root, ignore_errors=True)

    resolved_count = sum(1 for record in records if record["resolved"])
    unresolved_count = len(records) - resolved_count
    dataset_info: dict[str, Any] = {
        "kind": source.get("kind"),
        "total_loaded": len(instances),
        "note": (
            "--tasks N 取数据集顺序前 N 个实例 (不是官方 SWE-bench-Lite 300 例的"
            "选取口径; 见 SWEBENCH_PLAN.md)"
        ),
    }
    if "path" in source:
        dataset_info["path"] = source["path"]
    if "dataset" in source:
        dataset_info["dataset"] = source["dataset"]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "harness": "scripts/bench_swebench.py",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": args.mode,
        "dataset": dataset_info,
        "run": {
            "exec_timeout": args.exec_timeout,
            "max_iterations": args.max_iterations,
            "work_root": str(work_root),
            "repo_dir": str(repo_dir),
            "logs_dir": str(logs_dir),
            "fix_rules_available": sorted(registry),
        },
        "instances": records,
        "summary": {
            "total": len(records),
            "resolved": resolved_count,
            "unresolved": unresolved_count,
            "resolved_rate_pct": (
                round(100.0 * resolved_count / len(records), 1) if records else 0.0
            ),
            "note": (
                "确定性模式只有显式注入 fix 规则的实例才可能 resolved; "
                "其余全部 unresolved 且 reason 非空 — resolved_rate 天然诚实, "
                "不代表 LLM agent 能力 (见 SWEBENCH_PLAN.md)"
            ),
        },
    }
    try:
        _write_results(payload, args.output)
    except Exception as exc:
        print(f"bench_swebench: 结果写入失败 ({args.output}): {exc}", file=sys.stderr)
        return 1
    print(f"汇总: total={len(records)} resolved={resolved_count} "
          f"unresolved={unresolved_count} "
          f"rate={payload['summary']['resolved_rate_pct']}%")
    print(f"结果 JSON: {args.output}")
    print(f"日志目录: {logs_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
