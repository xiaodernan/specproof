# mypy: ignore-errors
# bench fixture-data policy: bench/ trees are executed as isolated task
# repositories and are exempt from repo mypy (same policy as tests/); the
# runner itself (scripts/bench_craft.py) is checked with mypy --strict.
"""Deterministic fix rules for task-05 (explicitly injected via --fix-module)."""

from craft.editor import Editor
from craft.loop import FixFunction
from craft.planner import Step

_EDGE_CASES_MODULE = '''\
"""Documented edge cases for upper_first (added by the task-05 fix)."""

from collections.abc import Callable


def run_edge_cases(fn: Callable[[str], str]) -> bool:
    checks = {"": "", "a": "A", "alice": "Alice", "éclair": "Éclair"}
    return all(fn(text) == expected for text, expected in checks.items())
'''


def fix_add_tests(editor: Editor, step: Step, diagnosis: str) -> list[str]:
    editor.write_file("edge_cases.py", _EDGE_CASES_MODULE)
    return ["edge_cases.py"]


FIXES: dict[str, FixFunction] = {"*": fix_add_tests}
