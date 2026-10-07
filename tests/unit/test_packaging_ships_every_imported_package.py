"""#207 — the distribution must ship every top-level package that shipped code imports.

``[tool.setuptools.packages.find].include`` in ``pyproject.toml`` is an
ALLOW-LIST, and an omission there is silent: the working copy resolves the
import through the current directory, so the test suite, the editable install
and every local run pass — and only a real (non-editable) install fails, at the
moment that code path runs, with ``ModuleNotFoundError``.

That is what happened. ``experiments`` is imported by
``agent/nodes/run_differential.py`` (6 sites), ``run_deep_experiments.py`` (2)
and ``generate_counterexamples.py`` (1), and ``devtools`` by 3 more; neither was
in the list. ``run_differential`` is the node that produces
``base_pass_head_fail`` / ``differential_test`` evidence, so in a deployed
install the flagship evidence path died on its last step — while every gate in
this repository stayed green, because all of them run from the working copy.

This gate reconciles the two lists. It is deliberately written as "every local
package that shipped code imports must be covered", not "these two names must
be present", so the next package cannot be forgotten either.
"""
from __future__ import annotations

import ast
import fnmatch
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PYPROJECT = REPO / "pyproject.toml"
SECTION = "[tool.setuptools.packages.find]"


def _find_block() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    assert SECTION in text, f"{SECTION} moved — probe broken"
    return text.split(SECTION)[1].split("\n[tool.")[0]


def include_patterns() -> list[str]:
    match = re.search(r"include = \[(.*?)\]", _find_block(), re.S)
    assert match, "the include list moved — probe broken"
    patterns = re.findall(r'"([^"]+)"', match.group(1))
    assert len(patterns) >= 5, f"only {patterns} parsed — probe broken"
    return patterns


def exclude_patterns() -> list[str]:
    match = re.search(r"exclude = \[(.*?)\]", _find_block(), re.S)
    assert match, "the exclude list moved — probe broken"
    return re.findall(r'"([^"]+)"', match.group(1))


def local_packages() -> set[str]:
    """Top-level directories that are importable packages."""
    found = {
        child.name
        for child in REPO.iterdir()
        if child.is_dir() and (child / "__init__.py").exists()
    }
    assert len(found) >= 10, f"only {sorted(found)} found — probe broken"
    return found


def shipped_packages() -> list[str]:
    """The local packages the include list already claims to ship."""
    patterns = include_patterns()
    return sorted(
        name for name in local_packages()
        if any(fnmatch.fnmatch(name, pattern) for pattern in patterns)
    )


def imported_top_level() -> set[str]:
    """Top-level module names imported anywhere under the shipped packages."""
    names: set[str] = set()
    for package in shipped_packages():
        for path in (REPO / package).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names |= {alias.name.split(".")[0] for alias in node.names}
                elif (
                    isinstance(node, ast.ImportFrom)
                    and node.level == 0
                    and node.module
                ):
                    names.add(node.module.split(".")[0])
    assert len(names) >= 20, f"only {sorted(names)} imported — probe broken"
    return names


def test_every_imported_local_package_is_shipped() -> None:
    patterns = include_patterns()
    excluded = exclude_patterns()
    offenders: list[str] = []
    for name in sorted(imported_top_level() & local_packages()):
        if any(fnmatch.fnmatch(name, pattern) for pattern in patterns):
            continue
        if any(fnmatch.fnmatch(name, pattern) for pattern in excluded):
            continue  # deliberately not shipped, and said so
        offenders.append(name)
    assert not offenders, (
        f"shipped code imports {offenders}, but [tool.setuptools.packages.find] "
        "neither includes nor excludes them: an editable install resolves those "
        "imports through the working directory, so only a REAL install fails — "
        "at runtime, on the code path that needs them"
    )


def test_the_differential_evidence_paths_are_covered() -> None:
    """Name the flagship case so a future edit has to think about it.

    `run_differential` is where `base_pass_head_fail` / `differential_test`
    evidence comes from; its late imports are what broke in a deployed install.
    """
    patterns = include_patterns()
    for needed in ("experiments", "devtools"):
        assert (REPO / needed / "__init__.py").exists(), (
            f"{needed}/ is no longer a package — update this clause"
        )
        assert any(fnmatch.fnmatch(needed, pattern) for pattern in patterns), (
            f"{needed} is imported by shipped node code but not shipped"
        )
