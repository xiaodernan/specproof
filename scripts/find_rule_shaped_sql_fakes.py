"""Which hand-written SQL fakes actually hand-write a RULE?

The queue item was "replace the remaining hand-written fakes with an
evaluator". The measurement (#363) showed only 20 of 252 fakes speak a
SQL surface at all. This script narrows it further: of those 20, which
ones DECIDE by looking at the SQL text?

- a fake that dispatches on `sql.startswith(...)` / parses a WHERE
  clause decides by the statement's TEXT — that is a hand-written second
  opinion, and the evaluator (tests/unit/fake_sql_engine.py) is exactly
  the replacement for it;
- a fake that only RECORDS statements, or serves canned rows regardless
  of the statement, is not a rule — an evaluator adds nothing there,
  because the test is not about SQL semantics.

Usage:
    python scripts/find_rule_shaped_sql_fakes.py
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS = REPO_ROOT / "tests"

#: Calls that mean "this fake looks at the statement text to decide".
RULE_SHAPED_CALLS = frozenset({"startswith", "endswith", "split", "partition"})

#: Names that suggest the fake is reading the statement's structure.
STRUCTURE_WORDS = ("where", "select ", "update ", "delete ", "insert ")


@dataclass
class RuleShaped:
    path: str
    line: int
    name: str
    evidence: list[str]


def _is_fake(name: str) -> bool:
    lowered = name.lower()
    return (
        lowered.startswith(("fake", "stub", "mock", "dummy"))
        or "fake" in lowered
    )


def _rule_evidence(node: ast.ClassDef) -> list[str]:
    """The lines that show the fake deciding by the statement text."""
    evidence: list[str] = []
    for item in ast.walk(node):
        if not isinstance(item, ast.Call):
            continue
        func = item.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr not in RULE_SHAPED_CALLS:
            continue
        # The argument must be the SQL, not some unrelated string.
        for arg in item.args:
            source = ast.unparse(arg).lower() if arg is not None else ""
            if "sql" in source or any(w in source for w in STRUCTURE_WORDS):
                evidence.append(
                    f"line {item.lineno}: {ast.unparse(item)[:90]}"
                )
                break
    return evidence


def collect() -> list[RuleShaped]:
    found: list[RuleShaped] = []
    for path in sorted(TESTS.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or not _is_fake(node.name):
                continue
            evidence = _rule_evidence(node)
            if evidence:
                found.append(RuleShaped(
                    path=str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                    line=node.lineno,
                    name=node.name,
                    evidence=evidence,
                ))
    return found


def main() -> int:
    found = collect()
    print(f"SQL fakes that DECIDE by the statement text: {len(found)}\n")
    for item in found:
        print(f"{item.path}:{item.line} {item.name}")
        for line in item.evidence:
            print(f"    {line}")
        print()
    if not found:
        print("  (none — the remaining SQL fakes only RECORD statements or")
        print("   serve canned rows, so an evaluator would add nothing)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
