# mypy: ignore-errors
# bench fixture-data policy: bench/ trees are executed as isolated task
# repositories and are exempt from repo mypy (same policy as tests/); the
# runner itself (scripts/bench_craft.py) is checked with mypy --strict.
"""Deterministic fix rules for task-01 (explicitly injected via --fix-module)."""

from craft.editor import Editor
from craft.loop import FixFunction
from craft.planner import Step


def fix_readonly_query(editor: Editor, step: Step, diagnosis: str) -> list[str]:
    editor.apply_edit(
        "svc.py",
        'raise NotImplementedError("read-only lookup not implemented yet")',
        "return users.get(email)",
    )
    return ["svc.py"]


FIXES: dict[str, FixFunction] = {"*": fix_readonly_query}
