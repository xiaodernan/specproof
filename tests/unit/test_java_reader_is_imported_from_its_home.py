"""A module that imports a name under an alias is not thereby a source for it.

#494 moved the Java-tree reader into ``agent/nodes/_java_files.py`` and had
``run_static_checks`` import it as ``_read_java_files`` for its own use.
``run_deep_experiments`` kept importing ``_read_java_files`` **from
run_static_checks** — and importing a name into a module does not re-export it
(mypy's ``no-implicit-reexport``), so ``python -m mypy .`` reported

    agent/nodes/run_deep_experiments.py:77: error: Module
    "agent.nodes.run_static_checks" does not explicitly export attribute
    "_read_java_files"  [attr-defined]

and CI's type-check leg stayed red on master. The import still *worked* at
runtime — which is exactly why nobody noticed: a re-export chain is invisible
until a static check looks at it.

The fence is narrow on purpose. 43 modules import ``_``-prefixed names from
other modules today, so "no private imports" is not a rule this codebase
follows; the rule it does follow is that the *reader* lives in one module and
consumers point at it.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CANONICAL_MODULE = "agent.nodes._java_files"
_READER_NAMES = {
    "read_main_java_files",
    "read_test_java_files",
    "_read_java_files",
    "_read_test_files",
}


def _java_reader_imports(path: Path) -> list[tuple[int, str, str]]:
    """(lineno, module, name) for every import that pulls in the java reader."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if alias.name in _READER_NAMES:
                    found.append((node.lineno, node.module, alias.name))
    return found


def test_every_java_reader_import_points_at_the_module_that_defines_it() -> None:
    offenders: list[str] = []
    for path in sorted((_REPO_ROOT / "agent").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for lineno, module, name in _java_reader_imports(path):
            if module != _CANONICAL_MODULE:
                where = path.relative_to(_REPO_ROOT)
                offenders.append(f"{where}:{lineno} imports {name} from {module}")

    assert not offenders, (
        f"the java reader is defined in {_CANONICAL_MODULE}; import it from there, "
        "not from a module that merely aliases it (that is what kept CI's mypy "
        "leg red after #494): " + "; ".join(offenders)
    )


def test_the_alias_run_static_checks_uses_is_the_same_function() -> None:
    """The alias must stay a plain alias, or 'same reader' becomes two readers."""
    from agent.nodes import _java_files, run_static_checks

    assert run_static_checks._read_java_files is _java_files.read_main_java_files
    assert run_static_checks._read_test_files is _java_files.read_test_java_files


def test_deep_experiments_actually_reads_the_workspace_through_it() -> None:
    """Calling the canonical reader is the point; an unused import is not a fix."""
    target = _REPO_ROOT / "agent" / "nodes" / "run_deep_experiments.py"
    source = target.read_text(encoding="utf-8")
    tree = ast.parse(source)

    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "read_main_java_files" in called
