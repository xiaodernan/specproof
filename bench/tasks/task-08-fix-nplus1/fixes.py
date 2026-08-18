# mypy: ignore-errors
# bench fixture-data policy: bench/ trees are executed as isolated task
# repositories and are exempt from repo mypy (same policy as tests/); the
# runner itself (scripts/bench_craft.py) is checked with mypy --strict.
"""Deterministic fix rules for task-08 (explicitly injected via --fix-module)."""

from craft.editor import Editor
from craft.loop import FixFunction
from craft.planner import Step


def fix_nplus1(editor: Editor, step: Step, diagnosis: str) -> list[str]:
    editor.apply_edit(
        "svc.py",
        "    return [_fetch_one(item_id) for item_id in item_ids]\n",
        "    return list(_fetch_many(item_ids).values())\n",
    )
    return ["svc.py"]


FIXES: dict[str, FixFunction] = {"*": fix_nplus1}
