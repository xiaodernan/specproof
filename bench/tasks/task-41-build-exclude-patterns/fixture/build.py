# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Build helpers (task-41)."""

import os


def collect_sources(root: str, exclude: list[str]) -> list[str]:
    names = os.listdir(root)
    picked: list[str] = []
    for name in names:
        if name in exclude:
            continue
        if name.endswith(".py") and not name.startswith("."):
            picked.append(name)
    return sorted(picked)
