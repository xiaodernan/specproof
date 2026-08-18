"""SpecCraft agent-task-suite generator (AGENT_PLAN_GAP_AUDIT 任务 10, V 车道).

从紧凑数据表生成 bench/ 下的 80 个新评测任务目录 (50 代码任务中新增的 40 个 +
20 对抗 + 10 断点恢复 + 10 危险动作审批), 生成结果落盘为真实目录; 生成幂等:
同一张表重复生成产出逐字节相同的内容, --check 用于发现漂移。

每个生成的任务目录与既有 bench/tasks/task-01..10 约定一致:
  task.spec        — 与 craft/spec.py 共享 schema 的 JSON (附加 id/category/
                     theme/appendix_e/trap 等 bench 元数据键);
  fixture/         — 初始仓库 (svc.py 等产品模块 + test_svc.py 可见测试);
  fixes.py         — 导出 FIXES: dict[str, Callable], 经 --fix-module 显式注入
                     (确定性修复规则, 绝不伪造智能);
  judge/test_judge.py — 隐藏验收/回归测试, craft 完成后由运行器拷入重放。

四类任务的判定口径 (详见 scripts/bench_craft.py 与 docs/eval/agent-task-suite.md):
  code        确定性修复收敛 + judge 全绿 -> COMPLETE;
  adversarial 对抗输入 (误导 Issue/注入/过时测试/隐藏禁止变更) 必须被拦 ->
              INTERCEPTED (trap=true);
  recovery    fixture 预置半程 .specraft/jobs/<id>/checkpoint.json, 运行器以
              craft resume 续跑, 恢复成功且 judge 幂等检查全绿 -> RECOVERED;
  approval    任务要求 git commit/push/网络等危险动作; craft 无审批服务, 确定性
              修复代表 Agent 拒绝执行并写入审批门拒绝记录; judge 验证危险动作
              零执行 -> APPROVAL_REFUSED (当前口径, 审批服务上线后升级)。

用法:
  python scripts/bench_gen_tasks.py           # 重新生成全部 80 个任务 (幂等)
  python scripts/bench_gen_tasks.py --check   # 与落盘内容逐字节比对, 漂移则 exit 1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench_gen_tasks_data import (  # noqa: E402  (数据表, 与本脚本同目录)
    ADVERSARIAL_ROWS,
    APPROVAL_ROWS,
    CODE_TASK_ROWS,
    RECOVERY_ROWS,
)

from craft.planner import Plan  # noqa: E402  (生成时校验恢复任务的 plan.json 形状)
from craft.spec import parse_spec_json  # noqa: E402  (生成时校验每个 task.spec)

BENCH_DIR = REPO_ROOT / "bench"
CODE_DIR = BENCH_DIR / "tasks"
ADVERSARIAL_DIR = BENCH_DIR / "adversarial"
RECOVERY_DIR = BENCH_DIR / "recovery"
APPROVAL_DIR = BENCH_DIR / "approval"

# 断点恢复任务 checkpoint.json 里 workspace 的占位符; 运行器在拷贝 fixture 后
# 把它替换为 scratch 工作区路径 (craft resume 的 from_checkpoint 需要真实路径)。
SCRATCH_PLACEHOLDER = "@@SCRATCH_WORKSPACE@@"

Row = dict[str, Any]


# ── 生成机件 ─────────────────────────────────────────────────────


def _split_piece(piece: str, limit: int = 60) -> list[str]:
    """把过长的单行内容拆成可独立成字面量的子串 (优先在空白处断开; repr 保证
    每个子串都是合法字面量, 隐式拼接后值不变)。"""
    if _display_width(repr(piece)) <= limit:
        return [repr(piece)]
    parts: list[str] = []
    remaining = piece
    while remaining:
        if _display_width(repr(remaining)) <= limit:
            parts.append(repr(remaining))
            break
        index = remaining.rfind(" ", 0, limit)
        if index <= 0:
            index = limit
        parts.append(repr(remaining[: index + 1]))
        remaining = remaining[index + 1 :]
    return parts


def _py_literal(text: str) -> str:
    """把任意文本渲染成 Python 字符串字面量 (隐式拼接, 每行 <= 100 字符,
    ruff E501 安全), 供 fixes.py 的 EDITS 表使用。"""
    parts = text.split("\n")
    pieces = [part + "\n" for part in parts[:-1]]
    pieces.append(parts[-1])
    if pieces == [""]:
        return ""
    tokens: list[str] = []
    for piece in pieces:
        tokens.extend(_split_piece(piece))
    chunks: list[str] = []
    current = ""
    for token in tokens:
        if not current:
            current = token
        elif _display_width(current) + 2 + _display_width(token) <= 82:
            current = current + " " + token
        else:
            chunks.append(current)
            current = token
    if current:
        chunks.append(current)
    if len(chunks) == 1:
        return chunks[0]
    return "(\n            " + "\n            ".join(chunks) + "\n        )"


def _render_edit(edit: dict[str, Any]) -> str:
    action = str(edit["action"])
    if action == "write_file":
        return (
            '{\n        "action": "write_file",\n        "path": '
            + repr(str(edit["path"]))
            + ',\n        "new":\n        '
            + _py_literal(str(edit["new"]))
            + ",\n    },"
        )
    if action == "apply_edit":
        return (
            '{\n        "action": "apply_edit",\n        "path": '
            + repr(str(edit["path"]))
            + ',\n        "old":\n        '
            + _py_literal(str(edit["old"]))
            + ',\n        "new":\n        '
            + _py_literal(str(edit["new"]))
            + ",\n    },"
        )
    if action == "delete":
        return (
            '{\n        "action": "delete",\n        "path": '
            + repr(str(edit["path"]))
            + ",\n    },"
        )
    if action == "move":
        return (
            '{\n        "action": "move",\n        "src": '
            + repr(str(edit["src"]))
            + ',\n        "dst": '
            + repr(str(edit["dst"]))
            + ",\n    },"
        )
    raise ValueError(f"未知编辑动作: {action!r}")


_WIDE_RANGES = (
    (0x1100, 0x115F),
    (0x2E80, 0xA4CF),
    (0xAC00, 0xD7A3),
    (0xF900, 0xFAFF),
    (0xFE30, 0xFE4F),
    (0xFF00, 0xFF60),
    (0xFFE0, 0xFFE6),
    (0x20000, 0x2FFFD),
    (0x30000, 0x3FFFD),
)


def _display_width(text: str) -> int:
    """终端显示宽度: CJK/全角字符计 2 列 (ruff E501 按显示宽度计算行宽)。"""
    width = 0
    for char in text:
        codepoint = ord(char)
        width += 2 if any(lo <= codepoint <= hi for lo, hi in _WIDE_RANGES) else 1
    return width


def _wrapped(text: str, width: int = 84) -> str:
    """按空格折行, 保证每行显示宽度不超过 width (ruff E501 安全)。"""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current:
            current = word
        elif _display_width(candidate) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return "\n".join(lines)


def _fixes_module(row: Row) -> str:
    task_id = str(row["id"])
    slug = str(row["slug"])
    theme = str(row["theme"])
    doc = str(
        row.get("fix_doc")
        or (
            "确定性修复规则, 由 scripts/bench_gen_tasks.py 生成 — 编辑表有序且幂等: "
            "每次调用只应用第一个尚未生效的编辑, 多阶段收敛跨循环迭代完成 "
            "(与真实 implement→test→refine 一致)。"
        ),
    )
    custom = row.get("fix_body")
    if custom:
        body = str(custom)
    else:
        edit_lines = "\n".join("    " + _render_edit(edit) for edit in row["edits"])
        body = (
            "EDITS: list[dict[str, str]] = [\n"
            + edit_lines
            + "\n]\n\n\ndef _read(editor: Editor, path: str) -> str | None:\n"
            "    try:\n"
            "        return \"\\n\".join(line for _, line in editor.read_file(path))\n"
            "    except Exception:\n"
            "        return None\n\n\n"
            + "def fix_"
            + slug
            + "(editor: Editor, step: Step, diagnosis: str) -> list[str]:\n"
            "    applied: list[str] = []\n"
            "    for edit in EDITS:\n"
            "        action = edit[\"action\"]\n"
            "        path = edit.get(\"path\") or edit.get(\"src\") or \"\"\n"
            "        if action == \"write_file\":\n"
            "            if _read(editor, path) == edit[\"new\"]:\n"
            "                continue\n"
            "            editor.write_file(path, edit[\"new\"])\n"
            "        elif action == \"apply_edit\":\n"
            "            if not edit.get(\"old\") or _read(editor, path) is None:\n"
            "                continue\n"
            "            try:\n"
            "                editor.apply_edit(path, edit[\"old\"], edit[\"new\"])\n"
            "            except Exception:\n"
            "                continue\n"
            "        elif action == \"delete\":\n"
            "            if _read(editor, path) is None:\n"
            "                continue\n"
            "            editor.delete(path)\n"
            "        elif action == \"move\":\n"
            "            if _read(editor, edit[\"dst\"]) is not None:\n"
            "                continue\n"
            "            editor.move(edit[\"src\"], edit[\"dst\"])\n"
            "        else:\n"
            "            continue\n"
            "        if path and path not in applied:\n"
            "            applied.append(path)\n"
            "    return applied\n"
        )
    header = (
        "# mypy: ignore-errors\n"
        "# bench fixture-data policy: bench/ trees are executed as isolated task\n"
        "# repositories and are exempt from repo mypy (same policy as tests/); the\n"
        "# runner itself (scripts/bench_craft.py) is checked with mypy --strict.\n"
        '"""Deterministic fix rules for '
        + task_id
        + ".\n\n"
        + _wrapped(theme, width=84)
        + "\n\n"
        + _wrapped(doc, width=84)
        + '\n"""\n\nfrom craft.editor import Editor\n'
        "from craft.loop import FixFunction\n"
        "from craft.planner import Step\n\n"
    )
    tail = "\nFIXES: dict[str, FixFunction] = {\"*\": fix_" + slug + "}\n"
    return header + body + tail



def _task_spec(row: Row) -> str:
    payload: dict[str, Any] = {
        "id": row["id"],
        "category": row["category"],
        "theme": row["theme"],
        "appendix_e": row["appendix_e"],
        "trap": bool(row.get("trap", False)),
        "title": row["title"],
        "description": row["description"],
        "acceptance_criteria": list(row["acceptance"]),
        "forbidden_changes": list(row["forbidden"]),
        "affected_area_hint": row["hint"],
    }
    for key in ("adversarial_kind", "recovery", "approval"):
        if key in row:
            payload[key] = row[key]
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _judge_module(row: Row, header: str | None = None) -> str:
    """每行的 judge 内容自带 '# mypy: ignore-errors' 头与说明 docstring,
    这里只负责收尾换行 (不重复注入头部)。"""
    del header  # 保留签名兼容; 行内容已含完整头部
    return str(row["judge"]).rstrip() + "\n"


_STDLIB_MODULES = {
    "collections",
    "csv",
    "datetime",
    "decimal",
    "fnmatch",
    "inspect",
    "io",
    "json",
    "logging",
    "math",
    "os",
    "pathlib",
    "re",
    "sys",
    "time",
    "warnings",
}

# ruff isort 的自动 first-party 检测依据仓库根包目录: 与这些包同名的 fixture
# 模块 (如 api.py) 被归为 first-party 段, 其余同仓模块归为第三方段。
_FIRST_PARTY_MODULES = {
    "agent",
    "api",
    "apps",
    "cli",
    "contracts",
    "craft",
    "evidence",
    "experiments",
    "integrations",
    "mcp",
    "observability",
    "providers",
    "retrieval",
    "sandbox",
    "services",
    "storage",
}


def _import_module(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("from "):
        return stripped[5:].split(" import ", 1)[0].split(".")[0]
    return stripped[7:].split(".", 1)[0]


def _import_section(line: str) -> int:
    module = _import_module(line)
    if module in _STDLIB_MODULES:
        return 0
    if module in _FIRST_PARTY_MODULES:
        return 2
    return 1


def _normalize_imports(content: str) -> str:
    """把顶部 import 区规范化为 ruff isort 认可的形式: 标准库段在前, 其余段
    (pytest 与同仓模块) 在后, 段内按字母序, 段间恰好一个空行。bench 任务文件是
    隔离 mini-repo 数据, ruff 把 svc/api 等同仓模块归为第三方段。"""
    lines = content.split("\n")
    import_indices: list[int] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            import_indices.append(index)
    if not import_indices:
        return content
    # 连续段: 索引必须连续 (允许中间隔空行), 遇到非 import 非空行即截断。
    blocks: list[list[int]] = []
    current: list[int] = [import_indices[0]]
    for index in import_indices[1:]:
        gap = lines[current[-1] + 1 : index]
        if all(not g.strip() for g in gap):
            current.append(index)
        else:
            blocks.append(current)
            current = [index]
    blocks.append(current)
    # 从后往前整段重建 (避免索引位移): 标准库段在前, 其余段在后, 段间恰好一个空行。
    for block in reversed(blocks):
        def _sort_key(statement: str) -> tuple[int, str]:
            return (0, statement) if statement.startswith("import ") else (1, statement)

        sections: list[list[str]] = [[], [], []]
        for i in block:
            sections[_import_section(lines[i])].append(lines[i].strip())
        sections = [sorted(section, key=_sort_key) for section in sections]
        new_span: list[str] = []
        for section in sections:
            if section:
                if new_span:
                    new_span.append("")
                new_span.extend(section)
        lines = lines[: block[0]] + new_span + lines[block[-1] + 1 :]
    return "\n".join(lines)


def _task_artifacts(row: Row) -> dict[str, str]:
    files: dict[str, str] = {}
    for rel, content in row["files"].items():
        text = str(content)
        if rel.endswith(".py"):
            text = _normalize_imports(text)
        files[str(row["dirname"]) + "/" + rel] = text
    files[f'{row["dirname"]}/task.spec'] = _task_spec(row)
    files[f'{row["dirname"]}/fixes.py'] = _normalize_imports(_fixes_module(row))
    files[str(row["dirname"]) + "/judge/test_judge.py"] = _normalize_imports(
        _judge_module(row)
    )
    return files


# ── 断点恢复任务专用生成 ─────────────────────────────────────────


def _recovery_plan(row: Row) -> str:
    title = str(row["title"])
    hint = str(row["hint"])
    plan: dict[str, Any] = {
        "task_title": title,
        "mode": "deterministic",
        "steps": [
            {
                "id": "s1",
                "kind": "understand",
                "target_files": [hint],
                "intent": "阅读目标代码与既有约定 (M1 仅做可读性检查, 不注入上下文)",
                "success_criteria": {"type": "grep", "value": ""},
                "deps": [],
            },
            {
                "id": "s2",
                "kind": "modify",
                "target_files": [hint],
                "intent": "按任务修改实现代码",
                "success_criteria": {"type": "compile", "value": ""},
                "deps": [],
            },
            {
                "id": "s3",
                "kind": "test",
                "target_files": [],
                "intent": "运行测试套件并保证全绿",
                "success_criteria": {"type": "test_green", "value": ""},
                "deps": [],
            },
            {
                "id": "s4",
                "kind": "verify",
                "target_files": [],
                "intent": "机械核验变更已落地且测试全绿",
                "success_criteria": {"type": "test_green", "value": ""},
                "deps": [],
            },
        ],
        "risk_classification": {
            "auth": False,
            "migration": False,
            "mq": False,
            "public_api": False,
        },
        "budget_alloc": {"iterations": 12, "tokens": 500000},
    }
    Plan.from_dict(plan)  # 生成时即校验形状
    return json.dumps(plan, ensure_ascii=False, indent=2) + "\n"


def _recovery_checkpoint(row: Row) -> str:
    rec = row["recovery"]
    payload: dict[str, Any] = {
        "job_id": rec["job_id"],
        "workspace": SCRATCH_PLACEHOLDER,
        "task_key": rec["task_key"],
        "last_green_step": rec["last_green_step"],
        "entries": rec["entries"],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _recovery_memory(row: Row) -> str:
    rec = row["recovery"]
    payload: dict[str, Any] = {
        "schema_version": 1,
        "entries": rec.get("memory_entries", []),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


# ── 各套件构建 ───────────────────────────────────────────────────


def build_code_tasks(rows: list[Row]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in rows:
        mapping.update(_task_artifacts(row))
    return mapping


def build_adversarial_tasks(rows: list[Row]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in rows:
        mapping.update(_task_artifacts(row))
    return mapping


def build_recovery_tasks(rows: list[Row]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in rows:
        mapping.update(_task_artifacts(row))
        rec = row["recovery"]
        job_dir = str(row["dirname"]) + "/fixture/.specraft/jobs/" + str(rec["job_id"])
        mapping[f"{job_dir}/plan.json"] = _recovery_plan(row)
        mapping[f"{job_dir}/checkpoint.json"] = _recovery_checkpoint(row)
        mapping[f"{job_dir}/memory.json"] = _recovery_memory(row)
    return mapping


def build_approval_tasks(rows: list[Row]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in rows:
        mapping.update(_task_artifacts(row))
    return mapping


# ── 校验与落盘 ───────────────────────────────────────────────────


def _validate(mapping: dict[str, str]) -> list[str]:
    """生成物自检: 每个 task.spec 通过 craft 共享 schema; 每个 .py 语法可编译;
    恢复任务 plan.json 通过 Plan 校验。返回问题列表 (空 = 通过)。"""
    problems: list[str] = []
    for rel, content in mapping.items():
        if rel.endswith("task.spec"):
            try:
                parse_spec_json(json.loads(content))
            except (ValueError, TypeError) as exc:
                problems.append(f"{rel}: task.spec 校验失败: {exc}")
        elif rel.endswith(".py"):
            try:
                compile(content, rel, "exec")
            except SyntaxError as exc:
                problems.append(f"{rel}: 语法错误: {exc}")
        elif rel.endswith("plan.json"):
            try:
                Plan.from_dict(json.loads(content))
            except ValueError as exc:
                problems.append(f"{rel}: plan.json 校验失败: {exc}")
    return problems


def build_suite() -> tuple[dict[str, str], dict[str, int]]:
    """构建全部 80 个新任务; 返回 (相对 bench/ 的路径→内容, 计数)。"""
    code = build_code_tasks(CODE_TASK_ROWS)
    adversarial = build_adversarial_tasks(ADVERSARIAL_ROWS)
    recovery = build_recovery_tasks(RECOVERY_ROWS)
    approval = build_approval_tasks(APPROVAL_ROWS)
    mapping: dict[str, str] = {}
    mapping.update(code)
    mapping.update(adversarial)
    mapping.update(recovery)
    mapping.update(approval)
    counts = {
        "code": len(CODE_TASK_ROWS),
        "adversarial": len(ADVERSARIAL_ROWS),
        "recovery": len(RECOVERY_ROWS),
        "approval": len(APPROVAL_ROWS),
    }
    problems = _validate(mapping)
    if problems:
        raise SystemExit("生成物自检失败:\n" + "\n".join(f"  - {p}" for p in problems))
    return mapping, counts


def write_suite(target: Path) -> tuple[dict[str, int], list[Path]]:
    mapping, counts = build_suite()
    written: list[Path] = []
    for rel, content in mapping.items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        written.append(path)
    return counts, written


def check_suite(target: Path) -> bool:
    """--check: 与落盘内容逐字节比对, 漂移返回 False。

    只核对生成器产出的目录; 跳过 legacy 手工任务 (task-01..10)、__pycache__ 与
    *.pyc (运行器 import fixes.py 时产生的缓存, 属 gitignore 范围)。
    """
    mapping, _counts = build_suite()
    drift: list[str] = []
    disk_files: set[Path] = set()
    for root_dir in (CODE_DIR, ADVERSARIAL_DIR, RECOVERY_DIR, APPROVAL_DIR):
        if root_dir.is_dir():
            disk_files.update(path for path in root_dir.rglob("*") if path.is_file())
    legacy_prefixes = tuple(f"tasks/task-{index:02d}-" for index in range(1, 11))
    for path in disk_files:
        rel = path.relative_to(BENCH_DIR).as_posix()
        if "__pycache__" in Path(rel).parts or rel.endswith(".pyc"):
            continue
        if rel.startswith(legacy_prefixes):
            continue
        if rel not in mapping:
            drift.append(f"{rel}: 落盘存在但生成表没有 (手工新增?)")
            continue
        if path.read_text(encoding="utf-8") != mapping[rel]:
            drift.append(f"{rel}: 内容与生成表不一致")
    for rel in mapping:
        if not (target / rel).is_file():
            drift.append(f"{rel}: 生成表有但落盘缺失")
    for message in drift:
        print("drift:", message, file=sys.stderr)
    return not drift


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SpecCraft agent-task-suite 生成器 (bench/)")
    parser.add_argument(
        "--check",
        action="store_true",
        help="与落盘内容逐字节比对 (漂移则 exit 1), 不写文件",
    )
    args = parser.parse_args(argv)
    if args.check:
        ok = check_suite(BENCH_DIR)
        print("check:", "OK (无漂移)" if ok else "DRIFT", file=sys.stderr)
        return 0 if ok else 1
    counts, written = write_suite(BENCH_DIR)
    print(
        f"生成完成: code={counts['code']} adversarial={counts['adversarial']} "
        f"recovery={counts['recovery']} approval={counts['approval']} "
        f"(共 {sum(counts.values())} 个任务, {len(written)} 个文件)"
    )
    return 0


# ── 任务表 (分块定义, 见下方各节) ───────────────────────────────

if __name__ == "__main__":
    raise SystemExit(main())
