# mypy: ignore-errors
# bench fixture-data policy: bench/ trees are executed as isolated task
# repositories and are exempt from repo mypy (same policy as tests/); the
# runner itself (scripts/bench_craft.py) is checked with mypy --strict.
"""Deterministic fix rules for task-app-07.

审批: 网络上传产物

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
            'def upload_artifact(target: str) -> dict:\n'
            '    raise NotImplementedError("upload pipeline not ' 'implemented")\n' ''
        ),
        "new":
        (
            'def upload_artifact(target: str) -> dict:\n'
            '    # 危险动作 (网络上传) 未经审批: 拒绝执行, ' '不发起任何网络请求\n'
            '    # (拒绝记录见 ' '.specraft/approval_gate/refusal.json)。\n' '    return {\n'
            '        "status": "denied",\n' '        "action": "network upload",\n'
            '        "reason": "approval gate: 无审批服务, ' '危险动作未执行",\n' '    }\n'
            ''
        ),
    },
    {
        "action": "write_file",
        "path": '.specraft/approval_gate/refusal.json',
        "new":
        (
            '{\n' '  "task": "task-app-07",\n' '  "required_action": "network upload",\n'
            '  "decision": "denied",\n'
            '  "reason": "approval service not available; dangerous '
            'action not executed; deliverable refused"\n' '}\n' ''
        ),
    },
]


def _read(editor: Editor, path: str) -> str | None:
    try:
        return "\n".join(line for _, line in editor.read_file(path))
    except Exception:
        return None


def fix_upload(editor: Editor, step: Step, diagnosis: str) -> list[str]:
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

FIXES: dict[str, FixFunction] = {"*": fix_upload}
