# mypy: ignore-errors
# bench fixture-data policy: bench/ trees are executed as isolated task
# repositories and are exempt from repo mypy (same policy as tests/); the
# runner itself (scripts/bench_craft.py) is checked with mypy --strict.
"""Deterministic fix rules for task-06 (explicitly injected via --fix-module)."""

from craft.editor import Editor
from craft.loop import FixFunction
from craft.planner import Step

_REFACTORED_SVC = '''\
"""Geometry helpers (task-06) — refactored: shared _area helper."""


def _area(width: int, height: int) -> int:
    return width * height


def area_rectangle(width: int, height: int) -> int:
    return _area(width, height)


def area_square(side: int) -> int:
    return _area(side, side)
'''


def fix_equivalent_refactor(editor: Editor, step: Step, diagnosis: str) -> list[str]:
    editor.write_file("svc.py", _REFACTORED_SVC)
    return ["svc.py"]


FIXES: dict[str, FixFunction] = {"*": fix_equivalent_refactor}
