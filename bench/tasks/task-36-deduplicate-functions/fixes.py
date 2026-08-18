# mypy: ignore-errors
# bench fixture-data policy: bench/ trees are executed as isolated task
# repositories and are exempt from repo mypy (same policy as tests/); the
# runner itself (scripts/bench_craft.py) is checked with mypy --strict.
"""Deterministic fix rules for task-36.

重构: 合并重复实现为参数化函数

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
            'def sum_even(values: list[int]) -> int:\n'
            '    return sum(v for v in values if v % 2 == 0)\n' '\n' '\n'
            'def sum_odd(values: list[int]) -> int:\n'
            '    return sum(v for v in values if v % 2 == 1)\n' ''
        ),
        "new":
        (
            'def sum_parity(values: list[int], parity: str) -> int:\n'
            '    if parity == "even":\n' '        remainder = 0\n'
            '    elif parity == "odd":\n' '        remainder = 1\n' '    else:\n'
            '        raise ValueError(f"非法 parity: {parity!r}")\n'
            '    return sum(v for v in values if v % 2 == remainder)\n' '\n' '\n'
            'def sum_even(values: list[int]) -> int:\n'
            '    return sum_parity(values, "even")\n' '\n' '\n'
            'def sum_odd(values: list[int]) -> int:\n'
            '    return sum_parity(values, "odd")\n' ''
        ),
    },
]


def _read(editor: Editor, path: str) -> str | None:
    try:
        return "\n".join(line for _, line in editor.read_file(path))
    except Exception:
        return None


def fix_dedupe(editor: Editor, step: Step, diagnosis: str) -> list[str]:
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

FIXES: dict[str, FixFunction] = {"*": fix_dedupe}
