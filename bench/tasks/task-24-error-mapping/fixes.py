# mypy: ignore-errors
# bench fixture-data policy: bench/ trees are executed as isolated task
# repositories and are exempt from repo mypy (same policy as tests/); the
# runner itself (scripts/bench_craft.py) is checked with mypy --strict.
"""Deterministic fix rules for task-24.

多文件: 服务异常到 API 错误映射

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
        "path": 'api.py',
        "old":
        (
            'from service import get_user\n' '\n' '\n'
            'def user_endpoint(store: dict, uid: str) -> dict:\n' '    try:\n'
            '        user = get_user(store, uid)\n' '    except Exception:\n'
            '        return {"status": 500, "error": "unknown"}\n'
            '    return {"status": 200, "user": user}\n' ''
        ),
        "new":
        (
            'from service import NotFoundError, get_user\n' '\n' '\n'
            'def user_endpoint(store: dict, uid: str) -> dict:\n' '    try:\n'
            '        user = get_user(store, uid)\n' '    except NotFoundError:\n'
            '        return {"status": 404, "error": "not_found"}\n'
            '    return {"status": 200, "user": user}\n' ''
        ),
    },
]


def _read(editor: Editor, path: str) -> str | None:
    try:
        return "\n".join(line for _, line in editor.read_file(path))
    except Exception:
        return None


def fix_errormapping(editor: Editor, step: Step, diagnosis: str) -> list[str]:
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

FIXES: dict[str, FixFunction] = {"*": fix_errormapping}
