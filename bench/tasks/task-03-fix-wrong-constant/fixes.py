# mypy: ignore-errors
# bench fixture-data policy: bench/ trees are executed as isolated task
# repositories and are exempt from repo mypy (same policy as tests/); the
# runner itself (scripts/bench_craft.py) is checked with mypy --strict.
"""Deterministic fix rules for task-03 (explicitly injected via --fix-module)."""

from craft.editor import Editor
from craft.loop import FixFunction
from craft.planner import Step


def fix_wrong_constant(editor: Editor, step: Step, diagnosis: str) -> list[str]:
    editor.apply_edit(
        "svc.py",
        "TOO_MANY_REQUESTS_STATUS = 500  # wrong constant: the standard is 429",
        "TOO_MANY_REQUESTS_STATUS = 429",
    )
    return ["svc.py"]


FIXES: dict[str, FixFunction] = {"*": fix_wrong_constant}
