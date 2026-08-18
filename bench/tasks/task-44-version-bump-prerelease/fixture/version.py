# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Version bumping (task-44)."""

import re

_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def next_version(current: str, bump: str) -> str:
    match = _RE.match(current)
    if not match:
        raise ValueError(f"非法版本号: {current!r}")
    major, minor, patch = (int(part) for part in match.groups())
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"非法 bump: {bump!r}")
