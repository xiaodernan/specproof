"""Honest Aider polyglot benchmark harness for SpecCraft (llm mode).

第二个工业级 agentic-coding 基准 (Aider-AI/polyglot-benchmark): 真实 repo
编辑任务 + 按任务语言的测试判定。口径与方法见 docs/eval/AIDER_PLAN.md。

每个任务: 从基准仓库扫描练习目录 (<lang>/exercises/practice/<slug>/),
复制到干净工作区 (排除 .meta 参考解), 把任务描述写成 PROMPT.md,
跑真实 craft 循环 (llm 模式: plan/edit, 无 fix_registry), 然后按任务语言
执行测试 (python=pytest / javascript=npm test), 记录 passed/failed。

判定 (唯一产生 resolved 的路径, 与 AIDER_PLAN.md 一致):
  1. craft 循环跑完且产生至少一个编辑;
  2. 任务测试文件与 package.json 与初始状态一致 (防作弊);
  3. 按语言执行的测试全部通过。
任何阶段失败 (下载/拷贝/描述缺失/llm 不可用/craft 异常/no edit produced/
deps unavailable/test fail) 都落成 unresolved + 非空 reason — 绝不伪造通过。

LLM 客户端: 从 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 经 craft.llm 构建
(lazy provider, 真实网络调用); 环境变量缺失在任何任务工作之前诚实退出。

离线/无网络可跑捆绑样例: python scripts/bench_aider.py --offline
(scripts/aider_sample/), 单元测试用它注入假客户端 (无网络无 Docker)。

CLI: --tasks N (默认 3) --offline | --benchmark-dir <path> | (自动 zip 下载)
     --languages python,javascript --output docs/eval/aider-results.json
     --md-output docs/eval/aider-results.md --no-venv
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from craft.budget import Budget  # noqa: E402
from craft.llm import LLMClient  # noqa: E402
from craft.loop import CraftLoop  # noqa: E402
from craft.planner import compile_plan, write_json_atomic  # noqa: E402
from craft.spec import TaskSpec  # noqa: E402

BENCHMARK_REPO = "Aider-AI/polyglot-benchmark"
BENCHMARK_URL = "https://github.com/Aider-AI/polyglot-benchmark"
ZIP_URL = "https://codeload.github.com/Aider-AI/polyglot-benchmark/zip/refs/heads/main"
EXTRACTED_DIRNAME = "polyglot-benchmark-main"
SAMPLE_DIR = Path(__file__).resolve().parent / "aider_sample"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "eval" / "aider-results.json"
DEFAULT_MD_OUTPUT = REPO_ROOT / "docs" / "eval" / "aider-results.md"
SCHEMA_VERSION = "1.0"
_LLM_ENV_VARS = ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")
_KNOWN_LANGUAGES = ("python", "javascript", "go", "java", "rust", "cpp")
# runner 支持优先级: pytest/npm test 在前, 其余语言诚实 unresolved (runner 未支持)。
_LANGUAGE_PRIORITY = ("python", "javascript", "go", "java", "rust", "cpp")
_RUNNER_BY_LANGUAGE: dict[str, str] = {"python": "pytest", "javascript": "npm"}
_UNSUPPORTED_RUNNERS: dict[str, str] = {
    lang: f"unsupported-{lang}"
    for lang in _KNOWN_LANGUAGES
    if lang not in _RUNNER_BY_LANGUAGE
}
# 防作弊保护: 任何测试/配置文件名 (相对路径) 在 craft 前后必须逐字节一致。
_TEST_FILE_RE = re.compile(
    r"(?:^test_.*\.py$|.*_test\.py$|.*\.spec\.(?:js|ts|jsx|tsx)$"
    r"|.*\.test\.(?:js|ts|jsx|tsx)$)"
)


class HarnessError(RuntimeError):
    """数据集 / 下载 / 用法 / 环境问题 (不是任务判定)。"""


class TaskError(RuntimeError):
    """单任务失败; 被转换成诚实的 unresolved 记录。"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="bench_aider",
        description=(
            "诚实的 Aider polyglot 评测 harness: 用 SpecCraft (llm 模式) 跑 "
            "polyglot-benchmark 练习, 按任务语言跑 pytest/npm test, 只记录真实结果"
        ),
    )
    parser.add_argument(
        "--tasks", type=int, default=3, help="最多评测的任务数 (默认 3; 0=全部)"
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="使用捆绑离线样例 (scripts/aider_sample/), 无需网络",
    )
    parser.add_argument(
        "--benchmark-dir", type=Path, default=None,
        help="本地 polyglot-benchmark 根目录 (跳过下载; 默认自动 zip 下载到 --cache-dir)",
    )
    parser.add_argument(
        "--cache-dir", type=Path, default=None,
        help=(
            "基准 zip 下载/解压缓存目录 (默认系统临时目录下 "
            "specproof-polyglot-benchmark)"
        ),
    )
    parser.add_argument(
        "--languages", default=None,
        help=(
            "只评测列出的语言 (逗号分隔, 如 python,javascript); 默认全部语言, "
            "按 runner 支持优先级排序 (python, javascript 在前)"
        ),
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT,
        help=f"结果 JSON 路径 (默认 {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--md-output", type=Path, default=DEFAULT_MD_OUTPUT,
        help=f"Markdown 汇总路径 (默认 {DEFAULT_MD_OUTPUT})",
    )
    parser.add_argument(
        "--no-venv", action="store_true",
        help=(
            "python 任务: 跳过共享 venv 创建, 直接以当前解释器跑 pytest "
            "(离线样例/单元测试路径; 真实运行默认建 venv)"
        ),
    )
    parser.add_argument(
        "--deps-timeout", type=int, default=600,
        help="npm install / venv 创建超时 (秒, 默认 600)",
    )
    parser.add_argument(
        "--fetch-timeout", type=int, default=600,
        help="基准 zip 下载超时 (秒, 默认 600)",
    )
    parser.add_argument("--exec-timeout", type=int, default=300, help="每步命令超时 (秒)")
    parser.add_argument(
        "--max-iterations", type=int, default=12, help="craft 循环迭代预算"
    )
    parser.add_argument(
        "--work-root", type=Path, default=None, help="临时工作区父目录 (默认系统临时目录)"
    )
    parser.add_argument("--keep-work", action="store_true", help="保留临时工作区 (调试)")
    return parser.parse_args(argv)


# -- 下载与扫描 ------------------------------------------------------------

def _safe_extract_zip(archive: zipfile.ZipFile, dest: Path) -> None:
    """逐个条目解压, 拒绝绝对路径 / .. / 反斜杠越界 (zip-slip 防护)。"""
    for member in archive.infolist():
        if not member.filename or member.filename.endswith("/"):
            continue
        name = PurePosixPath(member.filename)
        if name.is_absolute() or ".." in name.parts or "\\" in member.filename:
            raise zipfile.BadZipFile(f"zip 内路径可疑: {member.filename!r}")
        archive.extract(member, dest)


def _fetch_benchmark(cache_dir: Path, timeout: int) -> Path:
    """下载并解压 polyglot-benchmark (走 HTTPS_PROXY/HTTP_PROXY 代理)。

    缓存命中直接复用。任何失败 → HarnessError 带人工回退方案
    (手动下载 + --benchmark-dir, 或 --offline)。
    """
    root = cache_dir / EXTRACTED_DIRNAME
    if root.is_dir():
        return root
    zip_path = cache_dir / "polyglot-benchmark.zip"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(ZIP_URL, timeout=timeout) as response:
            data = response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HarnessError(
            f"{BENCHMARK_REPO} 下载失败 (经 HTTPS_PROXY/HTTP_PROXY): {exc} — "
            f"回退: 手动下载 {BENCHMARK_URL}/archive/refs/heads/main.zip 解压后用 "
            "--benchmark-dir 指向它, 或 --offline 跑捆绑样例"
        ) from exc
    try:
        zip_path.write_bytes(data)
        with zipfile.ZipFile(zip_path) as archive:
            _safe_extract_zip(archive, cache_dir)
    except (OSError, zipfile.BadZipFile) as exc:
        shutil.rmtree(root, ignore_errors=True)
        raise HarnessError(
            f"{BENCHMARK_REPO} zip 写入/解压失败: {exc} — 可用 --benchmark-dir "
            "指向本地解压目录, 或 --offline 跑捆绑样例"
        ) from exc
    if not root.is_dir():
        raise HarnessError(
            f"下载解压后未找到 {EXTRACTED_DIRNAME}/ (目录结构异常); "
            "请用 --benchmark-dir 指向本地解压目录, 或 --offline 跑捆绑样例"
        )
    return root


def _read_description(ex_dir: Path) -> str:
    """.docs/instructions.md 优先, 否则练习目录下任意 .md (排除 .meta)。"""
    candidates = [ex_dir / ".docs" / "instructions.md"]
    candidates.extend(sorted(ex_dir.glob("*.md")))
    for candidate in candidates:
        if candidate.is_file():
            try:
                return candidate.read_text(encoding="utf-8")
            except OSError:
                continue
    return ""


def _python_test_files(ex_dir: Path) -> list[str]:
    """exercism 风格: <slug>_test.py; 排除 test_*.py 辅助文件 (如 test_utils.py)。"""
    return sorted(
        path.name
        for path in ex_dir.iterdir()
        if path.is_file()
        and path.name.endswith("_test.py")
        and not path.name.startswith("test_")
    )


def _javascript_spec_files(ex_dir: Path) -> list[str]:
    return sorted(
        path.name
        for path in ex_dir.iterdir()
        if path.is_file() and (path.name.endswith(".spec.js") or path.name.endswith(".test.js"))
    )


def _normalize_exercise(lang: str, ex_dir: Path) -> dict[str, Any] | None:
    """把一个练习目录规范化成任务条目; 不是练习的目录返回 None。

    python/javascript 只有检测到测试文件才算练习 (runner pytest/npm);
    go/java/rust/cpp 按语言标记 runner=unsupported-<lang> (harness 只实现
    pytest/npm test, 这些语言诚实 unresolved)。
    """
    runner = _RUNNER_BY_LANGUAGE.get(lang, _UNSUPPORTED_RUNNERS.get(lang))
    if runner is None:
        return None
    if lang == "python":
        test_files = _python_test_files(ex_dir)
    elif lang == "javascript":
        test_files = _javascript_spec_files(ex_dir)
    elif lang == "go":
        test_files = sorted(
            path.name
            for path in ex_dir.iterdir()
            if path.is_file() and path.name.endswith("_test.go")
        )
    elif lang == "java":
        test_files = [path.name for path in ex_dir.iterdir()
                      if path.is_file() and path.name.endswith("Test.java")]
    elif lang == "rust":
        test_files = [path.name for path in ex_dir.iterdir()
                      if path.is_file() and path.name.endswith(".rs")]
    else:  # cpp
        test_files = [path.name for path in ex_dir.iterdir()
                      if path.is_file() and path.name.endswith("_test.cpp")]
    if not test_files and lang in _RUNNER_BY_LANGUAGE:
        return None  # 没有测试文件的目录不是练习
    if lang == "javascript" and not (ex_dir / "package.json").is_file():
        return None  # npm test 需要 package.json, 缺失则不是可评测练习
    return {
        "task_id": f"{lang}/{ex_dir.name}",
        "language": lang,
        "runner": runner,
        "source_dir": str(ex_dir),
        "test_file": test_files[0] if test_files else "",
        "description": _read_description(ex_dir),
    }


def _scan_benchmark(root: Path) -> list[dict[str, Any]]:
    """扫描 <lang>/exercises/practice/<slug>/ 布局, 返回任务条目列表。"""
    tasks: list[dict[str, Any]] = []
    for lang in sorted(path.name for path in root.iterdir() if path.is_dir()):
        practice = root / lang / "exercises" / "practice"
        if not practice.is_dir():
            continue
        for ex_dir in sorted(path for path in practice.iterdir() if path.is_dir()):
            task = _normalize_exercise(lang, ex_dir)
            if task is not None:
                tasks.append(task)
    return tasks


def _order_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """runner 支持优先级排序 (python, javascript, ... 在前), 同语言按 task_id。"""
    priority = {lang: index for index, lang in enumerate(_LANGUAGE_PRIORITY)}
    return sorted(
        tasks,
        key=lambda task: (priority.get(str(task.get("language")), 999), str(task["task_id"])),
    )


def _filter_languages(
    tasks: list[dict[str, Any]], languages: str
) -> list[dict[str, Any]]:
    wanted = [entry.strip() for entry in languages.split(",") if entry.strip()]
    unknown = [lang for lang in wanted if lang not in _KNOWN_LANGUAGES]
    if unknown:
        raise HarnessError(f"--languages 含未知语言: {unknown} (可选 {_KNOWN_LANGUAGES})")
    if not wanted:
        raise HarnessError("--languages 为空 (请给逗号分隔的语言列表)")
    return [task for task in tasks if str(task["language"]) in wanted]


def _load_tasks(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if args.offline:
        root = SAMPLE_DIR / "repo"
        source: dict[str, Any] = {"kind": "offline-sample", "path": str(root)}
        if not root.is_dir():
            raise HarnessError(f"捆绑样例缺失: {root}")
    elif args.benchmark_dir is not None:
        root = args.benchmark_dir
        if not root.is_dir():
            raise HarnessError(f"--benchmark-dir 不存在或不是目录: {root}")
        source = {"kind": "local-dir", "path": str(root)}
    else:
        cache_dir = args.cache_dir or (
            Path(tempfile.gettempdir()) / "specproof-polyglot-benchmark"
        )
        root = _fetch_benchmark(cache_dir, args.fetch_timeout)
        source = {
            "kind": "downloaded",
            "repo": BENCHMARK_REPO,
            "url": BENCHMARK_URL,
            "path": str(root),
        }
    tasks = _scan_benchmark(root)
    if not tasks:
        raise HarnessError(
            f"未扫描到任何练习任务 ({root}) — 目录结构应为 "
            "<lang>/exercises/practice/<slug>/"
        )
    counts: dict[str, int] = {}
    for task in tasks:
        counts[str(task["language"])] = counts.get(str(task["language"]), 0) + 1
    source["total_scanned"] = len(tasks)
    source["language_counts"] = counts
    tasks = _order_tasks(tasks)
    if args.languages is not None:
        tasks = _filter_languages(tasks, args.languages)
    if args.tasks > 0:
        tasks = tasks[: args.tasks]
    return tasks, source


def _validate_task(entry: object, index: int) -> tuple[dict[str, Any] | None, str]:
    """任务条目 schema 校验; 非法条目返回 (None, 原因), 绝不静默跳过。"""
    if not isinstance(entry, dict):
        return None, f"task[{index}] 不是 JSON 对象"
    task_id = entry.get("task_id")
    language = entry.get("language")
    runner = entry.get("runner")
    test_file = entry.get("test_file")
    source_dir = entry.get("source_dir")
    description = entry.get("description")
    if not isinstance(task_id, str) or not task_id.strip():
        return None, f"task[{index}].task_id 为空"
    if not isinstance(language, str) or language not in _KNOWN_LANGUAGES:
        return None, f"task[{index}].language 非法: {language!r}"
    if not isinstance(runner, str) or not runner.strip():
        return None, f"task[{index}].runner 为空"
    if not isinstance(description, str) or not description.strip():
        return None, f"task[{index}].description 为空"
    if not isinstance(source_dir, str) or not Path(source_dir).is_dir():
        return None, f"task[{index}].source_dir 不存在: {source_dir!r}"
    if runner in ("pytest", "npm"):
        if not isinstance(test_file, str) or not test_file.strip():
            return None, f"task[{index}].test_file 为空 (runner={runner})"
        if not (Path(source_dir) / test_file).is_file():
            return None, f"task[{index}].test_file 不在 source_dir 里: {test_file!r}"
    return cast(dict[str, Any], entry), ""


# -- llm 模式: env / 客户端 --------------------------------------------------

def _validate_llm_env() -> list[str]:
    """检查三个 LLM_* 环境变量; 返回问题列表 (空列表 = 可用)。

    检查刻意放在任何下载/任务工作之前: 缺 key 是诚实的用法退出, 绝不半途而废。
    key 的值本身绝不打印/落盘。
    """
    problems: list[str] = []
    for name in _LLM_ENV_VARS:
        if not os.getenv(name, "").strip():
            problems.append(name)
    if os.getenv("LLM_API_KEY", "").strip() == "replace_me":
        problems.append("LLM_API_KEY (占位符 'replace_me')")
    return problems


def _build_llm_client(job_id: str = "") -> LLMClient:
    """从 LLM_* 环境变量经 craft.llm 构建客户端。

    provider 在 LLMClient 内部 lazy 构建 (probe_on_init=False), 此调用不做网络
    I/O。单元测试 monkeypatch 此工厂注入确定性假客户端 (无 LLM 无网络)。
    """
    return LLMClient(job_id=job_id)


def _redact_base_url() -> str:
    """去敏感 LLM_BASE_URL 摘要: 仅 scheme + host + port。

    绝不记录 path/query/userinfo — base URL 可能内嵌凭据, 结果 JSON 必须无 key
    (tests/security/test_no_key_leak.py)。
    """
    raw = os.getenv("LLM_BASE_URL", "").strip()
    if not raw:
        return "(unset)"
    try:
        parts = urllib.parse.urlsplit(raw)
    except ValueError:
        return "(unparseable)"
    host = parts.hostname or raw
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme or 'http'}://{host}{port}"


# -- 共享 venv (python 任务) --------------------------------------------------

def _prepare_venv(work_root: Path, *, enabled: bool, timeout: int) -> dict[str, str]:
    """python 任务用的共享 venv + pytest。--no-venv 直接当前解释器。

    失败返回 python="" + 真实错误 — 调用方转为诚实 "deps unavailable", 不崩溃。
    """
    if not enabled:
        return {
            "python": "",
            "error": "",
            "note": "--no-venv: 直接使用当前解释器, 跳过 venv 创建 (样例/测试路径)",
        }
    venv_dir = work_root / "venv"
    python = (
        str(venv_dir / "Scripts" / "python.exe")
        if os.name == "nt"
        else str(venv_dir / "bin" / "python")
    )
    if Path(python).is_file():
        return {"python": python, "error": "", "note": "复用已存在的共享 venv"}
    try:
        create = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"python": "", "error": f"venv 创建失败: {exc}", "note": ""}
    if create.returncode != 0:
        tail = f"{create.stdout}\n{create.stderr}".strip()
        return {"python": "", "error": f"venv 创建失败: {tail[-800:]}", "note": ""}
    try:
        pip = subprocess.run(
            [python, "-m", "pip", "install", "--no-input",
             "--disable-pip-version-check", "pytest"],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"python": python, "error": f"venv pytest 安装失败: {exc}", "note": ""}
    if pip.returncode != 0:
        tail = f"{pip.stdout}\n{pip.stderr}".strip()
        return {"python": python, "error": f"venv pytest 安装失败: {tail[-800:]}", "note": ""}
    return {"python": python, "error": "", "note": "共享 venv + pytest 已就绪"}


# -- 任务执行 ---------------------------------------------------------------

def _safe_dirname(task_id: str) -> str:
    cleaned = "".join("_" if ch in r'<>:"/\|?*' else ch for ch in task_id)
    return cleaned.strip() or "task"


def _copy_exercise(source: Path, workdir: Path) -> None:
    """复制练习目录到干净工作区; .meta/ (参考解) 绝不进入工作区。"""
    shutil.copytree(source, workdir, ignore=shutil.ignore_patterns(".meta"))


def _write_prompt(workdir: Path, task: dict[str, Any]) -> Path:
    """把任务描述写成工作区内的 PROMPT.md (craft 的输入之一)。"""
    runner = str(task["runner"])
    command_desc = (
        f"pytest {task['test_file']}" if runner == "pytest" else "npm test"
    )
    content = (
        f"# 任务: {task['task_id']}\n\n"
        f"{task['description']}\n\n"
        "## 判题方式\n\n"
        f"测试命令: {command_desc}\n\n"
        "禁止修改任何测试文件或 package.json 的 test 脚本; "
        "判定时这些文件必须与初始状态完全一致。\n"
    )
    prompt_path = workdir / "PROMPT.md"
    prompt_path.write_text(content, encoding="utf-8", newline="\n")
    return prompt_path


def _is_protected_name(rel_path: str) -> bool:
    if Path(rel_path).name == "package.json":
        return True
    return bool(_TEST_FILE_RE.match(rel_path))


def _snapshot_protected(workdir: Path) -> dict[str, bytes]:
    """测试/配置文件在 craft 前的逐字节快照 (防作弊基线)。"""
    protected: dict[str, bytes] = {}
    for path in sorted(workdir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(workdir).as_posix()
        if _is_protected_name(rel):
            protected[rel] = path.read_bytes()
    return protected


def _protected_violations(before: dict[str, bytes], workdir: Path) -> list[str]:
    """craft 后比对: 被修改/删除的受保护文件, 或新增的测试类文件 = 违规。"""
    violations: list[str] = []
    for rel, data in before.items():
        path = workdir / rel
        if not path.is_file():
            violations.append(f"{rel} (被删除)")
        elif path.read_bytes() != data:
            violations.append(f"{rel} (被修改)")
    for path in sorted(workdir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(workdir).as_posix()
        if rel not in before and _is_protected_name(rel):
            violations.append(f"{rel} (新增)")
    return violations


def _run_craft(
    task: dict[str, Any],
    workdir: Path,
    artifact_dir: Path,
    exec_timeout: int,
    max_iterations: int,
    *,
    client: LLMClient,
) -> dict[str, Any]:
    """跑真实 craft 循环 (llm 模式: plan/edit, 无 fix_registry)。"""
    spec = TaskSpec(
        title=f"[{task['task_id']}] 完成任务 (Aider polyglot)",
        description=str(task["description"]),
        acceptance_criteria=[f"{task['runner']} 测试通过"],
        forbidden_changes=["测试文件与 package.json test 脚本 (禁止修改)"],
        affected_area_hint="",
    )
    budget = Budget(max_iterations=max_iterations)
    plan = compile_plan(spec, mode="llm", budget=budget, client=client)
    loop = CraftLoop(
        spec,
        plan,
        workdir,
        job_id=f"aider-{_safe_dirname(str(task['task_id']))}",
        artifact_dir=artifact_dir,
        fix_registry={},
        exec_mode="local",
        exec_timeout=exec_timeout,
        budget=budget,
        client=client,
    )
    return loop.run()


def _append_log(log_path: Path, text: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        if not text.endswith("\n"):
            handle.write("\n")


def _run_command(
    command: list[str], *, cwd: Path, timeout: int, log_path: Path
) -> dict[str, Any]:
    """跑一条测试命令并记录 outcome=passed|failed|error + 输出尾部。"""
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command, cwd=cwd, capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        tail = f"<timeout after {timeout}s>"
        _append_log(log_path, f"$ {' '.join(command)}\n{tail}")
        return {
            "outcome": "error",
            "output_tail": tail,
            "seconds": round(time.monotonic() - started, 1),
        }
    except OSError as exc:
        tail = f"<无法启动: {exc}>"
        _append_log(log_path, f"$ {' '.join(command)}\n{tail}")
        return {
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
        "outcome": outcome,
        "output_tail": combined[-500:],
        "seconds": round(time.monotonic() - started, 1),
    }


def _find_npm() -> str | None:
    return shutil.which("npm")


def _npm_install(workdir: Path, npm_path: str, timeout: int) -> dict[str, Any]:
    """工作区内 npm install (devDependencies, 继承代理环境变量)。"""
    command = [npm_path, "install", "--no-audit", "--no-fund", "--loglevel=error"]
    try:
        proc = subprocess.run(
            command, cwd=workdir, capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"installed": False, "error": f"npm install 超时 ({timeout}s)"}
    except OSError as exc:
        return {"installed": False, "error": f"npm install 无法启动: {exc}"}
    tail = f"{proc.stdout}\n{proc.stderr}".strip()
    if proc.returncode != 0:
        return {"installed": False, "error": f"npm install 失败: {tail[-800:]}"}
    return {"installed": True, "error": ""}


def _record_template(task_id: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "status": "unresolved",
        "resolved": False,
        "reason": "",
        "stage": "setup",
        "language": "",
        "runner": "",
        "test_file": "",
        "source_dir": "",
        "description_head": "",
        "prompt": {},
        "craft": None,
        "deps": None,
        "test_run": None,
        "note": "",
        "logs": {},
    }


def _invalid_record(index: int, problem: str) -> dict[str, Any]:
    record = _record_template(f"<invalid-{index}>")
    record["reason"] = f"task schema invalid: {problem}"
    return record


def _crash_record(task_id: str, exc: Exception) -> dict[str, Any]:
    record = _record_template(task_id)
    record["reason"] = (
        f"harness internal error ({type(exc).__name__}): {exc} — "
        "已按 unresolved 记录, 未声称 resolved"
    )
    return record


def run_task(
    task: dict[str, Any],
    *,
    work_root: Path,
    logs_dir: Path,
    exec_timeout: int,
    max_iterations: int,
    llm_client_factory: Callable[[str], LLMClient],
    venv: dict[str, str],
    deps_timeout: int,
) -> dict[str, Any]:
    task_id = str(task["task_id"])
    task_logs = logs_dir / _safe_dirname(task_id)
    tests_log = task_logs / "tests.log"
    record = _record_template(task_id)
    record["language"] = str(task["language"])
    record["runner"] = str(task["runner"])
    record["test_file"] = str(task["test_file"])
    record["source_dir"] = str(task["source_dir"])
    record["description_head"] = str(task["description"])[:300]
    record["logs"] = {"tests_log": str(tests_log)}
    record["llm"] = {
        "client": "craft.llm.LLMClient",
        "model": os.getenv("LLM_MODEL", ""),
        "base_url": _redact_base_url(),
        "key_recorded": False,
    }

    def fail(stage: str, reason: str) -> dict[str, Any]:
        record["stage"] = stage
        record["reason"] = reason
        return record

    runner = str(task["runner"])
    if runner not in ("pytest", "npm"):
        return fail(
            "tests",
            f"runner 未支持: 语言 {record['language']} 的测试执行本 harness 未实现 "
            "(仅支持 pytest/npm test); 未运行 craft, 未声称 resolved",
        )
    source = Path(str(task["source_dir"]))
    workdir = work_root / _safe_dirname(task_id)
    try:
        _copy_exercise(source, workdir)
        prompt_path = _write_prompt(workdir, task)
    except OSError as exc:
        return fail("setup", f"任务工作区准备失败 ({source}): {exc}")
    record["prompt"] = {"path": str(prompt_path)}
    protected_before = _snapshot_protected(workdir)
    craft_artifact_dir = task_logs / "craft"
    try:
        report = _run_craft(
            task,
            workdir,
            craft_artifact_dir,
            exec_timeout,
            max_iterations,
            client=llm_client_factory(f"aider-{_safe_dirname(task_id)}"),
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
    craft_record: dict[str, Any] = {
        "result": craft_result,
        "mode": report.get("mode"),
        "edits": edits,
        "iterations": budget_used.get("iterations") if isinstance(budget_used, dict) else None,
        "seconds": budget_used.get("seconds") if isinstance(budget_used, dict) else None,
        "report_path": str(craft_artifact_dir / "report.json"),
    }
    if report.get("llm_fallback_reason"):
        craft_record["llm_fallback_reason"] = str(report["llm_fallback_reason"])
    llm_usage = report.get("llm_usage")
    if isinstance(llm_usage, dict):
        craft_record["llm_usage"] = llm_usage
    record["craft"] = craft_record
    violations = _protected_violations(protected_before, workdir)
    if violations:
        return fail(
            "craft",
            f"任务测试/配置文件被修改 — 判定无效: {violations[:5]}",
        )
    if not edits:
        return fail(
            "craft",
            f"no edit produced: craft 未产生任何编辑 (终态 {craft_result}); "
            "未运行测试, 未声称 resolved",
        )
    if runner == "pytest":
        venv_python = venv.get("python", "")
        deps_record: dict[str, Any] = {
            "python": venv_python or sys.executable,
            "venv_error": venv.get("error", ""),
            "installed": bool(venv_python),
            "install_error": "",
            "note": venv.get("note", ""),
        }
        record["deps"] = deps_record
        if venv_python:
            test_python = venv_python
        elif venv.get("error"):
            return fail("deps", f"deps unavailable: venv 不可用: {venv['error']}")
        else:
            test_python = sys.executable
            deps_record["note"] = (
                f"{deps_record['note']} — 未安装实例依赖, 直接运行 pytest"
            )
        command = [
            test_python, "-m", "pytest", "-q", "--no-header",
            "-p", "no:cacheprovider", str(task["test_file"]),
        ]
        test_run = _run_command(command, cwd=workdir, timeout=exec_timeout, log_path=tests_log)
        test_run["runner"] = "pytest"
        test_run["command"] = command
    else:  # npm
        npm_path = _find_npm()
        if npm_path is None:
            return fail(
                "deps",
                "deps unavailable: 未找到 npm (Node.js 未安装或不在 PATH); "
                "未运行测试, 未声称 resolved",
            )
        install = _npm_install(workdir, npm_path, deps_timeout)
        record["deps"] = {
            "npm": npm_path,
            "installed": bool(install["installed"]),
            "install_error": str(install["error"]),
            "note": "npm install (devDependencies; 经 HTTPS_PROXY/HTTP_PROXY)",
        }
        if not install["installed"]:
            return fail("deps", f"deps unavailable: {install['error']}")
        command = [npm_path, "test"]
        test_run = _run_command(command, cwd=workdir, timeout=exec_timeout, log_path=tests_log)
        test_run["runner"] = "npm"
        test_run["command"] = command
    record["test_run"] = test_run
    record["stage"] = "tests"
    if test_run["outcome"] != "passed":
        return fail(
            "tests",
            f"任务测试未通过 ({test_run.get('runner')}): {test_run['output_tail'][-400:]}",
        )
    if craft_result != "DONE":
        record["note"] = (
            f"craft 终态 {craft_result} (内部 pytest 判据), 但按任务语言的测试通过 — "
            "resolved 判定以任务测试为准 (见 AIDER_PLAN.md)"
        )
    record["status"] = "resolved"
    record["resolved"] = True
    record["reason"] = ""
    return record


# -- 结果 --------------------------------------------------------------------

def _write_results(payload: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(output_path, payload)


def _write_md(payload: dict[str, Any], md_path: Path) -> None:
    summary = payload["summary"]
    llm = payload["llm"]
    benchmark = payload["benchmark"]
    lines = [
        "# Aider polyglot benchmark — SpecCraft llm harness 结果",
        "",
        f"- 生成时间: {payload['generated_at']}",
        f"- 基准: {benchmark['name']} (source: {benchmark['source'].get('kind')})",
        f"- LLM: {llm['model']} @ {llm['base_url']} (key 不记录)",
        "- 判定: resolved 仅当 craft 产生编辑 + 任务测试/配置文件未被修改 + "
        "按语言执行的测试全部通过 (见 docs/eval/AIDER_PLAN.md)",
        "",
        "## 汇总",
        "",
        f"- total={summary['total']} resolved={summary['resolved']} "
        f"unresolved={summary['unresolved']} pass_rate={summary['resolved_rate_pct']}%",
        f"- 说明: {summary['note']}",
        "",
        "## 任务明细",
        "",
        "| task_id | language | runner | status | stage | reason (前 160 字) |",
        "|---|---|---|---|---|---|",
    ]
    for record in payload["tasks"]:
        reason = str(record["reason"]).replace("|", "/")[:160]
        lines.append(
            f"| {record['task_id']} | {record['language']} | {record['runner']} "
            f"| {record['status']} | {record['stage']} | {reason} |"
        )
    lines.extend(
        [
            "",
            "## 诚实性说明",
            "",
            "- 这是 harness 口径, 非官方 aider 口径 (官方口径在 aider 仓库的 "
            "benchmark harness + 完整语言工具链; 见 AIDER_PLAN.md)",
            "- 每个非 resolved 记录都携带真实阶段 (setup/craft/deps/tests) 与原因; "
            "绝不伪造通过。",
        ]
    )
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    env_problems = _validate_llm_env()
    if env_problems:
        print(
            "LLM mode requires LLM_API_KEY/LLM_BASE_URL/LLM_MODEL env vars",
            file=sys.stderr,
        )
        print(f"缺失/无效: {', '.join(env_problems)}", file=sys.stderr)
        return 2
    try:
        tasks, source = _load_tasks(args)
    except HarnessError as exc:
        print(f"bench_aider: 错误: {exc}", file=sys.stderr)
        print("提示: 离线验证可用 --offline (捆绑样例, 无需网络/Docker)", file=sys.stderr)
        return 2

    explicit_work_root = args.work_root is not None
    work_root = args.work_root if args.work_root is not None else Path(
        tempfile.mkdtemp(prefix="aider-work-")
    )
    logs_dir = args.output.parent / "aider-logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    needs_python = any(str(task["runner"]) == "pytest" for task in tasks)
    if needs_python:
        venv_info = _prepare_venv(
            work_root, enabled=not args.no_venv, timeout=args.deps_timeout
        )
        if venv_info["error"]:
            print(f"bench_aider: venv 准备失败: {venv_info['error']}", file=sys.stderr)
            print(
                "(相关 python 任务将以 unresolved reason='deps unavailable' 诚实记录)",
                file=sys.stderr,
            )
    else:
        venv_info = {"python": "", "error": "", "note": "无 pytest 任务, 未建 venv"}
    client_factory: Callable[[str], LLMClient] = _build_llm_client

    records: list[dict[str, Any]] = []
    total = len(tasks)
    for index, entry in enumerate(tasks):
        task, problem = _validate_task(entry, index)
        if task is None:
            record = _invalid_record(index, problem)
        else:
            try:
                record = run_task(
                    task,
                    work_root=work_root,
                    logs_dir=logs_dir,
                    exec_timeout=args.exec_timeout,
                    max_iterations=args.max_iterations,
                    llm_client_factory=client_factory,
                    venv=venv_info,
                    deps_timeout=args.deps_timeout,
                )
            except Exception as exc:
                record = _crash_record(str(entry.get("task_id")), exc)
        records.append(record)
        if record["resolved"]:
            print(f"[{index + 1}/{total}] {record['task_id']} -> resolved")
        else:
            print(
                f"[{index + 1}/{total}] {record['task_id']} -> unresolved "
                f"({record['stage']}): {record['reason'][:160]}"
            )

    if not args.keep_work and not explicit_work_root:
        shutil.rmtree(work_root, ignore_errors=True)

    resolved_count = sum(1 for record in records if record["resolved"])
    unresolved_count = len(records) - resolved_count
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "harness": "scripts/bench_aider.py",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "benchmark": {
            "name": BENCHMARK_REPO,
            "url": BENCHMARK_URL,
            "source": source,
            "tasks_selected": len(records),
            "note": (
                "--tasks N 取 runner 支持优先级顺序 (python, javascript, ...) 的"
                "前 N 个任务; 这是 harness 子集口径, 非官方 aider 选取口径 "
                "(见 AIDER_PLAN.md)"
            ),
        },
        "run": {
            "exec_timeout": args.exec_timeout,
            "max_iterations": args.max_iterations,
            "deps_timeout": args.deps_timeout,
            "work_root": str(work_root),
            "logs_dir": str(logs_dir),
            "venv": venv_info,
        },
        "llm": {
            "client": "craft.llm.LLMClient",
            "model": os.getenv("LLM_MODEL", ""),
            "base_url": _redact_base_url(),
            "key_recorded": False,
        },
        "tasks": records,
        "summary": {
            "total": len(records),
            "resolved": resolved_count,
            "unresolved": unresolved_count,
            "resolved_rate_pct": (
                round(100.0 * resolved_count / len(records), 1) if records else 0.0
            ),
            "note": (
                "harness 口径: resolved 仅当 craft 产生编辑 + 任务测试/配置文件未被"
                "修改 + 按任务语言执行的测试全部通过; 失败阶段如实记录, 绝不伪造 "
                "通过 (见 docs/eval/AIDER_PLAN.md)"
            ),
        },
    }
    try:
        _write_results(payload, args.output)
    except Exception as exc:
        print(f"bench_aider: 结果写入失败 ({args.output}): {exc}", file=sys.stderr)
        return 1
    try:
        _write_md(payload, args.md_output)
    except Exception as exc:
        print(f"bench_aider: md 汇总写入失败 ({args.md_output}): {exc}", file=sys.stderr)
        return 1
    print(f"汇总: total={len(records)} resolved={resolved_count} "
          f"unresolved={unresolved_count} "
          f"rate={payload['summary']['resolved_rate_pct']}%")
    print(f"结果 JSON: {args.output}")
    print(f"md 汇总: {args.md_output}")
    print(f"日志目录: {logs_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
