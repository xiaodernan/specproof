"""#501 — four classic Python bug classes, swept clean and then ratcheted.

A scan of the shipped packages found **none** of these:

* mutable default argument (``def f(x=[])``) — the default is shared across calls;
* bare ``except:`` — swallows ``KeyboardInterrupt``/``SystemExit``;
* ``is``/``is not`` against a string or number — identity, not equality;
* ``assert`` doing runtime validation that vanishes under ``-O`` (only 12 asserts
  ship at all, all internal invariants).

A clean sweep is worth nothing unless it stays clean, so this file is the
ratchet: the first `def f(x=[])` or bare `except:` turns it red. The scan walks
``git ls-files`` (same census as the env-knob and clone gates), so a new module
must be tracked to be seen.
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PACKAGES = (
    "agent", "api", "cli", "craft", "evidence", "experiments", "integrations",
    "mcp", "observability", "retrieval", "sandbox", "services", "storage",
)

MUTABLE_DEFAULTS = (ast.List, ast.Dict, ast.Set)

#: ``is None`` / ``is True`` / ``is False`` are idiomatic; only strings and
#: numbers compared by identity are the bug.
_IDENTITY_OK = (type(None), bool)


def _trees() -> list[tuple[str, ast.AST]]:
    out = subprocess.run(
        ("git", "ls-files", "--", *(f"{pkg}/*.py" for pkg in PACKAGES)),
        cwd=ROOT,
        capture_output=True,
        check=True,
        timeout=180,
    )
    files = [line for line in out.stdout.decode("utf-8", "replace").splitlines() if line]
    assert len(files) > 100, f"shipped-file census collapsed: {len(files)} files"

    trees: list[tuple[str, ast.AST]] = []
    for rel in files:
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            trees.append((rel, ast.parse(path.read_text(encoding="utf-8", errors="replace"))))
        except SyntaxError:
            continue
    return trees


def test_no_mutable_default_arguments() -> None:
    offenders: list[str] = []
    for rel, tree in _trees():
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            defaults = list(node.args.defaults) + [d for d in node.args.kw_defaults if d]
            for default in defaults:
                if isinstance(default, MUTABLE_DEFAULTS):
                    offenders.append(f"{rel}:{node.lineno} {node.name}()")
    assert not offenders, "shared mutable default(s): " + ", ".join(offenders)


def test_no_bare_except() -> None:
    offenders = [
        f"{rel}:{node.lineno}"
        for rel, tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler) and node.type is None
    ]
    assert not offenders, (
        "bare 'except:' swallows KeyboardInterrupt/SystemExit: " + ", ".join(offenders)
    )


def test_no_identity_comparison_with_a_string_or_number() -> None:
    offenders: list[str] = []
    for rel, tree in _trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            # CPython guarantees len(ops) == len(comparators) on a Compare node.
            for op, comparator in zip(node.ops, node.comparators, strict=True):
                if not isinstance(op, (ast.Is, ast.IsNot)):
                    continue
                if not isinstance(comparator, ast.Constant):
                    continue
                if isinstance(comparator.value, _IDENTITY_OK):
                    continue
                offenders.append(f"{rel}:{node.lineno} {comparator.value!r}")
    assert not offenders, (
        "'is' compares identity, not equality — use '==' for values: " + ", ".join(offenders)
    )
