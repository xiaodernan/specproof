# mypy: ignore-errors
# bench fixture-data policy: bench/ trees are executed as isolated task
# repositories and are exempt from repo mypy (same policy as tests/); the
# runner itself (scripts/bench_craft.py) is checked with mypy --strict.
"""Deterministic fix rules for task-09 (explicitly injected via --fix-module)."""

from craft.editor import Editor
from craft.loop import FixFunction
from craft.planner import Step


def fix_add_authz(editor: Editor, step: Step, diagnosis: str) -> list[str]:
    editor.apply_edit(
        "svc.py",
        'DOC_AUTHORS = {"doc-1": "alice", "doc-2": "bob"}\n',
        'DOC_AUTHORS = {"doc-1": "alice", "doc-2": "bob"}\n\nADMIN_USERS = {"root"}\n',
    )
    editor.apply_edit(
        "svc.py",
        "def can_view_document(user: str, document_id: str) -> bool:\n    return True\n",
        (
            "def can_view_document(user: str, document_id: str) -> bool:\n"
            "    if user in ADMIN_USERS:\n"
            "        return True\n"
            "    return DOC_AUTHORS.get(document_id) == user\n"
        ),
    )
    return ["svc.py"]


FIXES: dict[str, FixFunction] = {"*": fix_add_authz}
