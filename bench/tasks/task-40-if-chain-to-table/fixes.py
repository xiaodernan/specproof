# mypy: ignore-errors
# bench fixture-data policy: bench/ trees are executed as isolated task
# repositories and are exempt from repo mypy (same policy as tests/); the
# runner itself (scripts/bench_craft.py) is checked with mypy --strict.
"""Deterministic fix rules for task-40.

重构: if 链 → 表驱动 (行为零变化)

确定性修复规则, 由 scripts/bench_gen_tasks.py 生成 — 编辑表有序且幂等:
每次调用只应用第一个尚未生效的编辑, 多阶段收敛跨循环迭代完成 (与真实
implement→test→refine 一致)。
"""

from craft.editor import Editor
from craft.loop import FixFunction
from craft.planner import Step

EDITS: list[dict[str, str]] = [
    {
        "action": "apply_edit",
        "path": 'svc.py',
        "old":
        (
            'def tier(score: int) -> str:\n' '    if score >= 90:\n' '        return "A"\n'
            '    if score >= 80:\n' '        return "B"\n' '    if score >= 70:\n'
            '        return "C"\n' '    return "D"\n' ''
        ),
        "new":
        (
            'TIER_TABLE = ((90, "A"), (80, "B"), (70, "C"))\n' '\n' '\n'
            'def tier(score: int) -> str:\n' '    for threshold, label in TIER_TABLE:\n'
            '        if score >= threshold:\n' '            return label\n'
            '    return "D"\n' ''
        ),
    },
]


def _read(editor: Editor, path: str) -> str | None:
    try:
        return "\n".join(line for _, line in editor.read_file(path))
    except Exception:
        return None


def fix_tiertable(editor: Editor, step: Step, diagnosis: str) -> list[str]:
    applied: list[str] = []
    for edit in EDITS:
        action = edit["action"]
        path = edit.get("path") or edit.get("src") or ""
        if action == "write_file":
            if _read(editor, path) == edit["new"]:
                continue
            editor.write_file(path, edit["new"])
        elif action == "apply_edit":
            if not edit.get("old") or _read(editor, path) is None:
                continue
            try:
                editor.apply_edit(path, edit["old"], edit["new"])
            except Exception:
                continue
        elif action == "delete":
            if _read(editor, path) is None:
                continue
            editor.delete(path)
        elif action == "move":
            if _read(editor, edit["dst"]) is not None:
                continue
            editor.move(edit["src"], edit["dst"])
        else:
            continue
        if path and path not in applied:
            applied.append(path)
    return applied

FIXES: dict[str, FixFunction] = {"*": fix_tiertable}
