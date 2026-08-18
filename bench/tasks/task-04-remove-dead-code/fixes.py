# mypy: ignore-errors
# bench fixture-data policy: bench/ trees are executed as isolated task
# repositories and are exempt from repo mypy (same policy as tests/); the
# runner itself (scripts/bench_craft.py) is checked with mypy --strict.
"""Deterministic fix rules for task-04 (explicitly injected via --fix-module)."""

from craft.editor import Editor
from craft.loop import FixFunction
from craft.planner import Step


def fix_remove_dead_code(editor: Editor, step: Step, diagnosis: str) -> list[str]:
    editor.apply_edit(
        "svc.py",
        (
            "\n\ndef format_amount(cents: int) -> str:"
            "  # noqa: F811 — dead shadowing copy, the defect\n"
            "    # dead duplicate: truncates cents instead of formatting them\n"
            "    return str(cents // 100)\n"
        ),
        "\n",
    )
    return ["svc.py"]


FIXES: dict[str, FixFunction] = {"*": fix_remove_dead_code}
