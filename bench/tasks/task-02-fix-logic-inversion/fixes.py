# mypy: ignore-errors
# bench fixture-data policy: bench/ trees are executed as isolated task
# repositories and are exempt from repo mypy (same policy as tests/); the
# runner itself (scripts/bench_craft.py) is checked with mypy --strict.
"""Deterministic fix rules for task-02 (explicitly injected via --fix-module)."""

from craft.editor import Editor
from craft.loop import FixFunction
from craft.planner import Step


def fix_logic_inversion(editor: Editor, step: Step, diagnosis: str) -> list[str]:
    editor.apply_edit(
        "svc.py",
        (
            "def is_leap_year(year: int) -> bool:\n"
            "    if year % 4 == 0:\n"
            "        return False  # inverted: divisible-by-4 years are rejected\n"
            "    if year % 100 == 0:\n"
            "        return False\n"
            "    return year % 400 == 0\n"
        ),
        (
            "def is_leap_year(year: int) -> bool:\n"
            "    if year % 400 == 0:\n"
            "        return True\n"
            "    if year % 100 == 0:\n"
            "        return False\n"
            "    return year % 4 == 0\n"
        ),
    )
    return ["svc.py"]


FIXES: dict[str, FixFunction] = {"*": fix_logic_inversion}
