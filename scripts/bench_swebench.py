"""Honest SWE-bench-Lite harness for SpecCraft (deterministic + LLM modes).

What this measures (and what it does not) — see docs/eval/SWEBENCH_PLAN.md.
Short version: the harness runs the REAL craft loop (plan -> execute ->
verify) against SWE-bench-Lite style instances, applies each instance's
test_patch, replays its FAIL_TO_PASS / PASS_TO_PASS tests and records
`resolved: true` ONLY when craft converged AND every test passed. Every
other outcome is `status=unresolved` with a non-empty `reason` — the
harness never fabricates a resolution.

Deterministic mode (default):
- craft's M1 loop only fixes through EXPLICITLY INJECTED fix rules
  (fix_registry / --fix-module). The bundled sample ships exactly one
  hardcoded rule for `specproof__toycalc-double-1`; real SWE-bench
  instance ids have no rules, so they are recorded unresolved with
  "no fix produced" (craft stage SKIPPED) instead of pretending.

LLM mode (--mode llm):
- the LLMClient is built from LLM_API_KEY / LLM_BASE_URL / LLM_MODEL via
  craft.llm (lazy provider, real network calls); missing env vars are an
  honest exit BEFORE any instance work;
- the craft loop runs WITHOUT fix_registry: planning, diagnosis and edits
  all go through the real client (plan/diagnose/edit), and every stage
  failure (checkout / craft / test_patch / deps / tests) becomes an
  unresolved record with the real reason;
- a shared per-run venv is created with pytest installed and VERIFIED
  (pytest --version); the instance deps are installed INTO it BEFORE the
  craft loop runs, and the loop's own compile/pytest steps use that venv
  interpreter (craft.Executor python override) — so test steps import the
  repo instead of dying on a bare system python. FAIL_TO_PASS / PASS_TO_PASS
  replay with the same interpreter. A deps install failure is recorded
  (deps.install_error) and craft proceeds honestly — its pytest steps
  surface the real stderr/exit code, never silence; era-compatible
  transitive pins (_REPO_DEP_PINS, flask -> werkzeug<3.0) are appended
  to the pip command for matching repo slugs and recorded per instance
  as deps.pins — nothing else is ever pinned; when the shared venv is
  REUSED from an earlier run, the repo's era pins are applied to that
  venv up front as well (`<venv python> -m pip install ... <pins>`, an
  idempotent downgrade — earlier runs may have left era-mismatched deps
  in it), recorded per instance as deps.pins_applied, and a pin-
  application failure lands in deps.install_error (never fatal);
- a venv creation / pytest-verify failure automatically falls back to
  --no-venv (current interpreter, no pip installs) with the reason recorded
  in run.venv and per-instance deps; --no-venv skips the venv/deps stage
  explicitly (offline sample / tests).

Offline by default: `python scripts/bench_swebench.py --offline` runs the
bundled toy sample (scripts/swebench_sample/) with no network and no
Docker. Real runs need the dataset JSON (scripts/fetch_swebench_lite.ps1)
or a HuggingFace dataset id, plus network git access for per-instance
checkouts — see the plan doc for the manual steps.

CLI: --tasks N (default 10) --dataset <path|hf-id>
     --output docs/eval/swebench-results.json
     --mode deterministic|llm --instances-file <json> [--no-venv]
"""

from __future__ import annotations

import argparse
import http.client
import importlib.util
import json
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
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from craft.budget import Budget  # noqa: E402
from craft.editor import Editor  # noqa: E402
from craft.llm import LLMClient  # noqa: E402
from craft.loop import CraftLoop, FixFunction  # noqa: E402
from craft.planner import Step, compile_plan, write_json_atomic  # noqa: E402
from craft.spec import TaskSpec  # noqa: E402

SAMPLE_DIR = Path(__file__).resolve().parent / "swebench_sample"
SAMPLE_INSTANCES = SAMPLE_DIR / "instances.json"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "eval" / "swebench-results.json"
SCHEMA_VERSION = "1.0"
_ROWS_API = "https://datasets-server.huggingface.co/rows"
_LLM_ENV_VARS = ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")
_INSTANCE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-\d+$")
_INSTALL_MARKERS = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")

#: venv note prefix _prepare_venv stamps when the shared venv already
#: existed and passed the pytest check (REUSED, not freshly created).
#: run_instance keys off this prefix: a reused venv keeps whatever
#: earlier runs installed (pip resolves latest by default), so the repo's
#: era pins must be applied to it explicitly (see _apply_pins_to_venv).
_VENV_REUSED_NOTE = "复用已存在的共享 venv"

#: Era-compatible transitive dependency pins, keyed by repo slug (the last
#: path segment of the instance `repo` field). The shared SWE-bench venv
#: resolves latest deps by default, which broke pallets__flask-4045 with
#: "ImportError: cannot import name url_quote from werkzeug.urls" — pip
#: installed werkzeug 3.x for a flask 2.3-era instance whose url_quote was
#: removed in werkzeug 3.0 (docs/eval/swebench-llm-results-v5.json). Pins
#: apply ONLY to the slugs listed here; everything else keeps current
#: behavior (a deps failure is still recorded and never fatal).
#: flask 2.3-era needs url_quote, removed in werkzeug 3.0 (probed live:
#: werkzeug 3.0.6 lacks it, 2.3.8 has it) — so the era pin is <3.0, not <3.1.
_REPO_DEP_PINS: dict[str, list[str]] = {
    "flask": ["werkzeug<3.0"],
}


def _pins_for_repo(repo: str) -> list[str]:
    """Era pins for a repo (slug = last path segment); [] when unpinned."""
    slug = repo.rstrip("/").rsplit("/", 1)[-1].lower()
    if slug.endswith(".git"):
        slug = slug[:-4]
    return list(_REPO_DEP_PINS.get(slug, []))


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
            "诚实的 SWE-bench-Lite 评测 harness: 用 SpecCraft 管道 (确定性或 LLM 模式) "
            "跑实例, 应用 test_patch, 重放 FAIL_TO_PASS / PASS_TO_PASS, 只记录真实结果"
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
        "--model", default=None,
        help=(
            "llm 模式: 覆盖 LLM_MODEL 模型档位 (v12 更强档位复跑用; "
            "只改内存环境, 结果 JSON 如实记录 model_override)"
        ),
    )
    parser.add_argument(
        "--mode", choices=("deterministic", "llm"), default="deterministic",
        help=(
            "deterministic=仅注入 fix 规则驱动; llm=从 LLM_API_KEY/LLM_BASE_URL/"
            "LLM_MODEL 构建真实客户端, 无 fix_registry 地跑 plan/diagnose/edit "
            "(缺少环境变量时诚实退出)"
        ),
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="使用捆绑离线样例 (scripts/swebench_sample/), 无需网络/Docker",
    )
    parser.add_argument(
        "--instances-file", type=Path, default=None,
        help=(
            "精选子集 JSON (instance_id 数组, 如 scripts/swebench_subset/"
            "python_subset.json): 只评测列出的实例; 与 --dataset 联用"
        ),
    )
    parser.add_argument(
        "--no-venv", action="store_true",
        help=(
            "llm 模式: 跳过共享 venv 创建与依赖安装, 直接以当前解释器跑 pytest "
            "(离线样例/单元测试路径; 真实实例默认建 venv)"
        ),
    )
    parser.add_argument(
        "--deps-timeout", type=int, default=600,
        help="llm 模式 venv 创建/pip 安装超时 (秒, 默认 600)",
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
        payload: Any = None
        truncations: list[str] = []
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=60) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except http.client.IncompleteRead as exc:
                # The proxy intermittently truncates large rows responses
                # (observed live: 1.70MB of 1.74MB). Retry with backoff; only
                # after 3 truncations does the run fail with the offline
                # fallback spelled out.
                truncations.append(f"attempt{attempt + 1}: {exc}")
                time.sleep(1.0 * (attempt + 1))
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                raise HarnessError(
                    f"HF 数据集 {dataset_id!r} 拉取失败: {exc} — 离线方案: "
                    "先 scripts/fetch_swebench_lite.ps1 生成本地 JSON 再 "
                    "--dataset <文件>, 或 --offline 用捆绑样例"
                ) from exc
        if payload is None:
            raise HarnessError(
                f"HF 数据集 {dataset_id!r} 拉取失败 (连续 3 次响应截断: "
                f"{'; '.join(truncations)}) — 离线方案: 先 "
                "scripts/fetch_swebench_lite.ps1 生成本地 JSON 再 "
                "--dataset <文件>, 或 --offline 用捆绑样例"
            )
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
    dataset: str | None,
    offline: bool,
    tasks: int,
    instances_file: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if offline:
        path = SAMPLE_INSTANCES
        source: dict[str, Any] = {"kind": "offline-sample", "path": str(path)}
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
            # With a subset file the wanted ids may live anywhere in the
            # split, so fetch the full split (limit=0) before filtering.
            fetch_limit = 0 if instances_file is not None else tasks
            instances = _fetch_hf_rows(dataset, limit=fetch_limit)
        else:
            raise HarnessError(
                f"--dataset {dataset!r} 既不是已存在的文件也不是 hf 数据集 id "
                "(owner/name 形式); 离线可 --offline"
            )
    if instances_file is not None:
        wanted = _load_subset_file(instances_file)
        instances, missing = _filter_by_subset(instances, wanted)
        if missing:
            raise HarnessError(
                f"instances-file 中的 {len(missing)} 个 id 不在数据集里: {missing} — "
                "请核对子集与 --dataset 是否对应同一 split"
            )
        source["subset"] = {
            "path": str(instances_file),
            "requested": len(wanted),
            "matched": len(instances),
        }
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


# -- llm mode: env / client / subset / venv --------------------------------

def _validate_llm_env(model_override: str | None = None) -> list[str]:
    """Check the three LLM_* env vars; return the list of problems.

    Empty list = usable configuration. The check is deliberately BEFORE any
    dataset/network work: a missing key is an honest usage exit, never a
    half-run. The key value itself is never printed or recorded.
    A non-empty model_override (--model) satisfies the LLM_MODEL check.
    """
    problems: list[str] = []
    for name in _LLM_ENV_VARS:
        if name == "LLM_MODEL" and model_override:
            continue
        if not os.getenv(name, "").strip():
            problems.append(name)
    if os.getenv("LLM_API_KEY", "").strip() == "replace_me":
        problems.append("LLM_API_KEY (占位符 'replace_me')")
    return problems


def _build_llm_client(job_id: str = "") -> LLMClient:
    """Build the M2 client from the LLM_* env vars via craft.llm.

    The provider is constructed lazily inside LLMClient (probe_on_init=False),
    so this call performs no network I/O. Unit tests monkeypatch this factory
    to inject a deterministic fake client (no LLM, no network).
    """
    return LLMClient(job_id=job_id)


def _redact_base_url() -> str:
    """De-credentialed LLM_BASE_URL summary: scheme + host + port ONLY.

    Never records path/query/userinfo — base URLs can embed credentials, and
    the results JSON must stay key-free (tests/security/test_no_key_leak.py).
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


def _load_subset_file(path: Path) -> list[str]:
    """Load a curated subset file: a JSON array of SWE-bench instance ids.

    Strict schema: top-level array, non-empty, unique, every entry a
    non-empty string matching owner__name-N. Anything else is a HarnessError
    (the subset is a usage contract, not an instance verdict).
    """
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessError(f"instances-file 无法读取/解析 ({path}): {exc}") from exc
    if not isinstance(payload, list):
        raise HarnessError(
            f"instances-file 顶层必须是 instance_id 字符串数组 ({path})"
        )
    ids: list[str] = []
    for index, entry in enumerate(payload):
        if not isinstance(entry, str) or not entry.strip():
            raise HarnessError(f"instances-file[{index}] 应为非空 instance_id 字符串")
        instance_id = entry.strip()
        if not _INSTANCE_ID_RE.fullmatch(instance_id):
            raise HarnessError(
                f"instances-file[{index}] {instance_id!r} 不是 SWE-bench instance_id "
                "(应为 owner__name-N 形式)"
            )
        ids.append(instance_id)
    if not ids:
        raise HarnessError(f"instances-file 为空数组 ({path})")
    if len(set(ids)) != len(ids):
        raise HarnessError(f"instances-file 存在重复 instance_id ({path})")
    return ids


def _filter_by_subset(
    instances: list[dict[str, Any]], wanted_ids: list[str]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Keep dataset rows whose instance_id is in the subset, preserving the
    subset's order. Ids absent from the dataset are reported honestly."""
    by_id = {str(instance.get("instance_id", "")): instance for instance in instances}
    missing = [instance_id for instance_id in wanted_ids if instance_id not in by_id]
    filtered = [by_id[instance_id] for instance_id in wanted_ids if instance_id in by_id]
    return filtered, missing


def _venv_pytest_available(python: str, timeout: int) -> tuple[bool, str]:
    """Verify the venv interpreter can actually run pytest.

    A venv whose pytest install failed must surface as an explicit error
    (never a silently broken environment): the probe command's own output
    rides the returned message.
    """
    try:
        probe = subprocess.run(
            [python, "-m", "pytest", "--version"],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"venv pytest 可用性检查失败: {exc}"
    if probe.returncode != 0:
        tail = f"{probe.stdout}\n{probe.stderr}".strip()
        return False, f"venv 已创建但 pytest 不可用: {tail[-800:]}"
    return True, ""


def _prepare_venv(work_root: Path, *, enabled: bool, timeout: int) -> dict[str, str]:
    """One shared venv per run (llm mode) with pytest installed and VERIFIED.

    --no-venv disables it (offline sample / unit tests): python="" means
    "use the current interpreter" and no pip installs happen. Every failure
    returns python="" + the real error — main() turns that into an
    automatic --no-venv fallback with the reason recorded, never a crash
    and never a silently empty environment.
    """
    if not enabled:
        return {
            "python": "",
            "error": "",
            "note": "--no-venv: 直接使用当前解释器, 跳过依赖安装 (样例/测试路径)",
        }
    venv_dir = work_root / "venv"
    python = (
        str(venv_dir / "Scripts" / "python.exe")
        if os.name == "nt"
        else str(venv_dir / "bin" / "python")
    )
    if Path(python).is_file():
        ok, reason = _venv_pytest_available(python, timeout)
        if ok:
            return {
                "python": python,
                "error": "",
                "note": f"{_VENV_REUSED_NOTE} (pytest --version 验证通过)",
            }
        return {"python": "", "error": reason, "note": ""}
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
        return {"python": "", "error": f"venv pytest 安装失败: {exc}", "note": ""}
    if pip.returncode != 0:
        tail = f"{pip.stdout}\n{pip.stderr}".strip()
        return {"python": "", "error": f"venv pytest 安装失败: {tail[-800:]}", "note": ""}
    ok, reason = _venv_pytest_available(python, timeout)
    if not ok:
        return {"python": "", "error": reason, "note": ""}
    return {
        "python": python,
        "error": "",
        "note": "共享 venv + pytest 已就绪 (pytest --version 验证通过)",
    }


def _fallback_no_venv(venv_info: dict[str, str]) -> dict[str, str]:
    """venv preparation failed -> automatic --no-venv fallback.

    The failure reason stays on record (error field) and the note states
    the fallback explicitly: the current interpreter runs pytest directly
    and no pip installs happen. Instances never crash out — they either
    run with the fallback interpreter or fail later with real test output.
    """
    reason = venv_info.get("error", "").strip() or "venv 准备失败 (原因未记录)"
    return {
        "python": "",
        "error": reason,
        "note": (
            "--no-venv 回退: venv 准备失败, 以当前解释器直接运行 pytest, "
            "跳过依赖安装 (原因已记录)"
        ),
        "fallback_no_venv": "true",
    }


def _first_install_marker(workdir: Path) -> str | None:
    """The repo's install config, in pip-install priority order.

    pyproject/setup.py/setup.cfg mean `pip install .` (package + pinned deps);
    requirements.txt is the fallback (`pip install -r`). None = no trivial
    install config — the deps stage is skipped, not an error.
    """
    for marker in _INSTALL_MARKERS:
        if (workdir / marker).is_file():
            return marker
    return None


def _install_instance_deps(
    python: str, workdir: Path, marker: str, timeout: int, repo: str = ""
) -> dict[str, Any]:
    """Trivial dependency install into the shared venv. Failure is returned
    (honest "deps unavailable"), never raised — heavy/compiled dependencies
    simply time out or fail on record.

    The instance repo's era pins (_REPO_DEP_PINS) are appended to the pip
    command so era-mismatched transitive deps cannot break the shared venv
    (flask -> werkzeug<3.0, real evidence pallets__flask-4045). The pins
    actually used ride every result as `pins` for the per-instance deps
    record. Only repos listed in the pin map are affected — everything
    else keeps the current command and failure semantics (recorded,
    never fatal).
    """
    pins = _pins_for_repo(repo)
    if marker == "requirements.txt":
        command = [python, "-m", "pip", "install", "--no-input",
                   "--disable-pip-version-check", "-r", marker, *pins]
    else:
        command = [python, "-m", "pip", "install", "--no-input",
                   "--disable-pip-version-check", ".", *pins]
    try:
        proc = subprocess.run(
            command, cwd=workdir, capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "installed": False,
            "error": f"pip install 执行失败 ({marker}): {exc}",
            "pins": pins,
        }
    tail = f"{proc.stdout}\n{proc.stderr}".strip()
    if proc.returncode != 0:
        return {
            "installed": False,
            "error": f"pip install 失败 ({marker}): {tail[-800:]}",
            "pins": pins,
        }
    return {"installed": True, "error": "", "pins": pins}


def _apply_pins_to_venv(
    python: str, pins: list[str], timeout: int
) -> dict[str, Any]:
    """Apply era pins to a REUSED shared venv, before the deps install.

    A fresh venv resolves dependencies from scratch, so appending the pins
    to the instance deps install is enough. A REUSED venv keeps whatever
    earlier runs installed — pip resolves latest by default, which is how
    werkzeug 3.x broke pallets__flask-4045 (url_quote was removed in
    werkzeug 3.0) — so the pins must be installed explicitly here; pip
    downgrades in place, making this idempotent. Failure is returned
    (recorded, never fatal): craft proceeds and surfaces real test output.
    """
    command = [
        python, "-m", "pip", "install", "--no-input",
        "--disable-pip-version-check", *pins,
    ]
    try:
        proc = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"applied": [], "error": f"era pin 应用失败 (reused venv): {exc}"}
    tail = f"{proc.stdout}\n{proc.stderr}".strip()
    if proc.returncode != 0:
        return {
            "applied": [],
            "error": f"era pin 应用失败 (reused venv): {tail[-800:]}",
        }
    return {"applied": list(pins), "error": ""}


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
            clone_url = repo_spec
        elif "/" in repo_spec and repo_spec.count("/") == 1:
            # SWE-bench `repo` fields are owner/name; clone from GitHub via
            # the standard proxy environment (HTTPS_PROXY/HTTP_PROXY).
            clone_url = f"https://github.com/{repo_spec}.git"
        else:
            raise InstanceError(
                f"repo source unavailable: {repo_spec!r} 不是本地路径也不是可克隆 URL; "
                "本地 checkout 请放到 --repo-dir 下 (目录名=slug) 或使用可克隆 URL"
            )
        cached = repo_dir / slug
        try:
            cached.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "clone", clone_url, str(cached)],
                capture_output=True, text=True, timeout=3600, check=True,
            )
        except subprocess.CalledProcessError as exc:
            tail = (exc.stderr or exc.stdout or "").strip()
            raise InstanceError(
                f"repo clone failed ({clone_url}): {tail[-800:]}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise InstanceError(f"repo clone failed ({clone_url}): 超时 (3600s)") from exc
        except OSError as exc:
            raise InstanceError(f"repo clone failed to start ({clone_url}): {exc}") from exc
        source = cached
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
    workdir: Path,
    node_id: str,
    timeout: int,
    log_path: Path,
    python: str | None = None,
) -> dict[str, Any]:
    command = [
        python or sys.executable, "-m", "pytest", "-q", "--no-header",
        "-p", "no:cacheprovider", node_id,
    ]
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command, cwd=workdir, capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        partial = f"{stdout}\n{stderr}".strip()
        tail = (partial or f"<timeout after {timeout}s>")[-500:]
        _append_log(log_path, f"$ {' '.join(command)}\n{tail}")
        return {
            "test": node_id,
            "outcome": "error",
            "output_tail": tail,
            "seconds": round(time.monotonic() - started, 1),
        }
    except OSError as exc:
        # A missing/broken interpreter (e.g. a venv python that vanished)
        # must surface as an explicit per-test error — never a crash, never
        # a silently empty record.
        tail = f"<could not start pytest: {exc}>"
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
    fix_rules: dict[str, FixFunction] | None,
    artifact_dir: Path,
    exec_timeout: int,
    max_iterations: int,
    *,
    mode: str = "deterministic",
    client: LLMClient | None = None,
    python: str | None = None,
) -> dict[str, Any]:
    """Run the real craft loop in-memory (exec_mode=local).

    deterministic: M1 rule plan + injected fix rules only (python=None:
    the loop executor resolves "python" from PATH exactly as before).
    llm: LLM planning (degrading honestly to the rule plan on failure) and
    the M2 diagnose/edit path through the client; fix_rules must be empty
    (the LLM mode never consults the fix registry). python (llm mode) is
    the per-run venv interpreter — the loop's compile/pytest steps then run
    against the venv that actually has pytest (+ instance deps installed
    BEFORE craft), instead of a system python that lacks them (首跑缺口:
    pallets__flask-* test steps died on "No module named 'flask'").
    """
    spec = TaskSpec(
        title=f"[{instance['instance_id']}] 修复缺陷 (SWE-bench)",
        description=str(instance["problem_statement"]),
        acceptance_criteria=["FAIL_TO_PASS 测试全部通过", "PASS_TO_PASS 测试全部通过"],
        forbidden_changes=[],
        affected_area_hint="",
    )
    budget = Budget(max_iterations=max_iterations)
    if mode == "llm":
        plan = compile_plan(spec, mode="llm", budget=budget, client=client)
    else:
        plan = compile_plan(spec, budget=budget)
    loop = CraftLoop(
        spec,
        plan,
        workdir,
        job_id=f"swebench-{instance['instance_id']}",
        artifact_dir=artifact_dir,
        fix_registry=fix_rules,
        exec_mode="local",
        exec_timeout=exec_timeout,
        budget=budget,
        client=client,
        python=python,
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
    mode: str = "deterministic",
    llm_client_factory: Callable[[str], LLMClient] | None = None,
    venv: dict[str, str] | None = None,
    deps_timeout: int = 600,
) -> dict[str, Any]:
    instance_id = str(instance["instance_id"])
    instance_logs = logs_dir / _safe_dirname(instance_id)
    tests_log = instance_logs / "tests.log"
    record = _record_template(instance_id)
    record["repo"] = str(instance["repo"])
    record["base_commit"] = str(instance["base_commit"])
    record["problem_statement_head"] = str(instance["problem_statement"])[:300]
    record["logs"] = {"tests_log": str(tests_log)}
    llm_mode = mode == "llm"
    if llm_mode:
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

    workdir: Path | None = None
    checkout_info: dict[str, str] = {}
    try:
        try:
            workdir, checkout_info = _checkout_instance(instance, repo_dir, work_root)
        except InstanceError as exc:
            return fail("setup", str(exc))
        record["checkout"] = checkout_info
        fix_rules: dict[str, FixFunction] | None
        if llm_mode:
            fix_rules = {}
            if llm_client_factory is None:
                return fail(
                    "craft",
                    "llm 模式缺少客户端工厂 (程序错误): 未声称 resolved",
                )
            client = llm_client_factory(f"swebench-{instance_id}")
        else:
            client = None
            fix_rules = fix_registry.get(instance_id)
            if fix_rules is None:
                record["note"] = "fix_registry 为空: craft 管道 SKIPPED (确定性模式绝不虚构修复)"
                return fail(
                    "craft",
                    f"no fix produced: 没有为 {instance_id} 注入确定性 fix 规则 "
                    "(fix_registry 为空 → craft 管道 SKIPPED); 未运行测试, 未声称 resolved",
                )
        # llm mode deps run BEFORE craft (首跑缺口修复): the loop's own
        # compile/pytest steps must run against an interpreter that can
        # import the repo — the shared venv, with the instance deps already
        # installed. A deps failure is recorded, never fatal here: craft
        # then fails or succeeds honestly on real pytest output (the loop's
        # executor surfaces the stderr tail + exit code, never silence).
        test_python = sys.executable
        deps_record: dict[str, Any] = {
            "python": sys.executable,
            "venv_error": "",
            "note": "",
            "install_marker": None,
            "installed": False,
            "install_error": "",
            "pins": [],
        }
        craft_python: str | None = None
        if llm_mode:
            venv_info = venv if venv is not None else {"python": "", "error": "", "note": ""}
            deps_record = {
                "python": venv_info.get("python", "") or sys.executable,
                "venv_error": venv_info.get("error", ""),
                "note": venv_info.get("note", ""),
                "install_marker": None,
                "installed": False,
                "install_error": "",
                "pins": [],
            }
            record["deps"] = deps_record
            venv_python = venv_info.get("python", "")
            if venv_python:
                test_python = venv_python
                craft_python = venv_python
                marker = _first_install_marker(workdir)
                deps_record["install_marker"] = marker
                pin_apply_error = ""
                if venv_info.get("note", "").startswith(_VENV_REUSED_NOTE):
                    # A REUSED venv keeps whatever earlier runs installed
                    # (pip resolves latest by default), so the repo's era
                    # pins are applied to it explicitly BEFORE the deps
                    # install — an idempotent downgrade. Recorded as
                    # deps.pins_applied; a pin-application failure is
                    # recorded like any deps failure and NEVER fatal:
                    # craft proceeds and surfaces real test output.
                    deps_record["pins_applied"] = []
                    repo_pins = _pins_for_repo(str(instance["repo"]))
                    if repo_pins:
                        apply_result = _apply_pins_to_venv(
                            venv_python, repo_pins, deps_timeout
                        )
                        deps_record["pins_applied"] = list(
                            apply_result.get("applied", [])
                        )
                        pin_apply_error = str(apply_result.get("error", ""))
                install_error = ""
                if marker is not None:
                    install_result = _install_instance_deps(
                        venv_python, workdir, marker, deps_timeout,
                        str(instance["repo"]),
                    )
                    deps_record["installed"] = bool(install_result["installed"])
                    install_error = str(install_result["error"])
                    deps_record["pins"] = list(install_result.get("pins", []))
                    if not install_result["installed"]:
                        deps_record["note"] = (
                            str(deps_record["note"])
                            + " — 实例依赖安装失败 (记录, 不阻止 craft): "
                            + str(install_result["error"])
                        )
                deps_record["install_error"] = " | ".join(
                    part for part in (pin_apply_error, install_error) if part
                )
            elif venv_info.get("fallback_no_venv"):
                deps_record["note"] = (
                    str(deps_record["note"])
                    + f" — venv 失败已回退 --no-venv (原因: {venv_info['error']})"
                )
            elif not venv_info.get("error"):
                deps_record["note"] = (
                    str(deps_record["note"]) + " — 未安装实例依赖, 直接运行 pytest"
                )
            else:
                return fail("deps", f"deps unavailable: venv 不可用: {venv_info['error']}")
        craft_artifact_dir = instance_logs / "craft"
        try:
            report = _run_craft(
                instance,
                workdir,
                fix_rules,
                craft_artifact_dir,
                exec_timeout,
                max_iterations,
                mode=mode,
                client=client,
                python=craft_python,
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
        if craft_result != "DONE":
            return fail("craft", f"craft 未收敛 ({craft_result}): {_craft_failure_reason(report)}")
        patch_info = _apply_test_patch(workdir, str(instance["test_patch"]))
        record["test_patch"] = patch_info
        if not patch_info["applied"]:
            return fail("test_patch", str(patch_info["error"]))
        # deps/venv state is already resolved BEFORE craft above; the replay
        # just reuses the same interpreter (venv python, or the current one
        # under --no-venv / fallback).
        fail_to_pass = [str(node) for node in instance["FAIL_TO_PASS"]]
        pass_to_pass = [str(node) for node in instance["PASS_TO_PASS"]]
        if not fail_to_pass:
            return fail("tests", "FAIL_TO_PASS 为空: 没有可判定的目标测试")
        record["fail_to_pass"] = [
            _run_one_test(workdir, node, exec_timeout, tests_log, python=test_python)
            for node in fail_to_pass
        ]
        record["pass_to_pass"] = [
            _run_one_test(workdir, node, exec_timeout, tests_log, python=test_python)
            for node in pass_to_pass
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
    llm_mode = args.mode == "llm"
    if llm_mode:
        if args.model:
            # Harness-only in-memory override; the results JSON records it
            # verbatim in run.model_override, and the key is never touched.
            os.environ["LLM_MODEL"] = args.model
        env_problems = _validate_llm_env(model_override=args.model)
        if env_problems:
            print(
                "LLM mode requires LLM_API_KEY/LLM_BASE_URL/LLM_MODEL env vars",
                file=sys.stderr,
            )
            print(f"缺失/无效: {', '.join(env_problems)}", file=sys.stderr)
            return 2
    try:
        instances, source = _load_instances(
            args.dataset, args.offline, args.tasks, args.instances_file
        )
        if llm_mode:
            registry: dict[str, dict[str, FixFunction]] = {}
            if args.fix_module is not None:
                print(
                    "警告: --fix-module 在 llm 模式被忽略 "
                    "(llm 循环不使用注入 fix 规则)",
                    file=sys.stderr,
                )
        else:
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
    venv_info: dict[str, str]
    if llm_mode:
        venv_info = _prepare_venv(
            work_root, enabled=not args.no_venv, timeout=args.deps_timeout
        )
        if venv_info["error"]:
            print(f"bench_swebench: venv 准备失败: {venv_info['error']}", file=sys.stderr)
            print(
                "(自动回退 --no-venv: 以当前解释器直接运行 pytest, 不安装依赖; "
                "原因已记录在结果 JSON 的 run.venv 与实例 deps 字段)",
                file=sys.stderr,
            )
            venv_info = _fallback_no_venv(venv_info)
    else:
        venv_info = {"python": sys.executable, "error": "", "note": "deterministic 模式不建 venv"}
    client_factory: Callable[[str], LLMClient] | None = _build_llm_client if llm_mode else None

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
                    mode=args.mode,
                    llm_client_factory=client_factory,
                    venv=venv_info,
                    deps_timeout=args.deps_timeout,
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
    subset_info = source.get("subset")
    if isinstance(subset_info, dict):
        dataset_info["subset"] = subset_info
    if llm_mode:
        summary_note = (
            "LLM 模式: 真实客户端 (plan/diagnose/edit), 无 fix_registry; "
            "resolved 仅当 craft DONE + test_patch 应用成功 + FAIL_TO_PASS/"
            "PASS_TO_PASS 全部通过 — harness 口径, 非官方 Docker 口径 "
            "(见 SWEBENCH_PLAN.md)"
        )
    else:
        summary_note = (
            "确定性模式只有显式注入 fix 规则的实例才可能 resolved; "
            "其余全部 unresolved 且 reason 非空 — resolved_rate 天然诚实, "
            "不代表 LLM agent 能力 (见 SWEBENCH_PLAN.md)"
        )
    payload: dict[str, Any] = {
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
            "venv": venv_info,
            "model_override": args.model or "",
        },
        "instances": records,
        "summary": {
            "total": len(records),
            "resolved": resolved_count,
            "unresolved": unresolved_count,
            "resolved_rate_pct": (
                round(100.0 * resolved_count / len(records), 1) if records else 0.0
            ),
            "note": summary_note,
        },
    }
    if llm_mode:
        payload["llm"] = {
            "client": "craft.llm.LLMClient",
            "model": os.getenv("LLM_MODEL", ""),
            "base_url": _redact_base_url(),
            "key_recorded": False,
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
