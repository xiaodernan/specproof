"""The two tools whose verdict *is* the gate must have one version, not three.

`ruff check .` and `mypy .` are the CI steps that decide whether a change may
reach master, so "which version answered" is not a detail — it is the answer.
Before #528 the repo held three different answers at once:

    installed in the dev venv   ruff 0.17.1   mypy 2.4.0
    uv.lock (tracked, 543 KB)   ruff 0.16.9   mypy 2.3.1
    pyproject dev extra         ruff>=0.8.0   mypy>=1.13.0   (a floor, so CI
                                resolved whatever pip served that day)

Three sources, three answers, and no authority among them. Nothing read the
lockfile (CI installs with `pip install -e ".[dev]"`), so it was a 543 KB
declaration that was already false. And a floor means a new release can turn
master red with no code change — #491 had already measured the neighbouring
failure (a typeshed change flipping `mcp/client.py`'s verdict).

Measured honestly: on 2026-10-30 both tools agree today (2.3.1 and 2.4.0 both
`Success: no issues found in 263 source files`; 0.16.9 and 0.17.1 both
`All checks passed`). So this is a **latent** trap, not an active red. Pinning
does not fix a failure; it makes the next drift land in a commit that bumps the
pin (and re-runs the gates) instead of silently in CI.

These legs keep the three sources from disagreeing again.
"""

from __future__ import annotations

import tomllib
from importlib import metadata
from pathlib import Path
from typing import Any

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO / "pyproject.toml"
_LOCK = _REPO / "uv.lock"
_CI = _REPO / ".github" / "workflows" / "ci.yml"

#: The tools whose exit status *is* the gate. Adding one here is how a new
#: verdict-deciding tool gets the same treatment.
_GATE_TOOLS = ("mypy", "ruff")


def _requirements(section: str = "dev") -> list[str]:
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    return list(data["project"]["optional-dependencies"][section])


def _pinned(name: str) -> str:
    """The exact version `name` is pinned to in the dev extra."""
    prefix = f"{name}=="
    hits = [r for r in _requirements() if r.replace(" ", "").startswith(prefix)]
    assert len(hits) == 1, (
        f"expected exactly one `{name}==…` in the dev extra, found {hits!r}. "
        f"A floor (`{name}>=…`) lets CI resolve a different version than the one "
        "the change was validated under"
    )
    return hits[0].replace(" ", "").split("==", 1)[1]


def _installed(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _locked_versions() -> dict[str, str]:
    """name -> version, read out of the lockfile's `[[package]]` tables."""
    if not _LOCK.exists():
        return {}
    data = tomllib.loads(_LOCK.read_text(encoding="utf-8"))
    return {
        pkg["name"]: pkg.get("version", "")
        for pkg in data.get("package", [])
        if "name" in pkg
    }


@pytest.mark.parametrize("tool", _GATE_TOOLS)
def test_each_gate_tool_is_pinned_exactly(tool: str) -> None:
    pinned = _pinned(tool)

    assert ".*" not in pinned and "," not in pinned, (
        f"{tool} is pinned to {pinned!r}, which is a range, not a version"
    )


@pytest.mark.parametrize("tool", _GATE_TOOLS)
def test_the_pin_is_the_version_this_repo_was_validated_under(tool: str) -> None:
    """Local green must predict CI green, so the pin must be what runs here."""
    pinned = _pinned(tool)
    installed = _installed(tool)
    if installed is None:
        pytest.skip(
            f"{tool} is not installed in this interpreter, so this leg cannot "
            "compare the pin with reality; run it in the dev environment "
            '(`pip install -e ".[dev]"`)'
        )

    assert pinned == installed, (
        f"{tool} is pinned to {pinned} but this interpreter runs {installed}. "
        "Either bump the pin (and re-run the gate) or install the pin — a gate "
        "you validated under a different version than CI's is not evidence"
    )


@pytest.mark.parametrize("tool", _GATE_TOOLS)
def test_the_lockfile_does_not_contradict_the_pin(tool: str) -> None:
    """A tracked lockfile nobody reads is still a claim; it must be true."""
    locked = _locked_versions()
    if not locked:
        pytest.skip(
            "there is no uv.lock; nothing can contradict the pin (CI installs "
            'with `pip install -e ".[dev]"`)'
        )

    assert tool in locked, (
        f"uv.lock is tracked but records no {tool}; it cannot be the lockfile "
        "for this project"
    )
    assert locked[tool] == _pinned(tool), (
        f"uv.lock says {tool} {locked[tool]}, pyproject pins {_pinned(tool)}. "
        "Anyone who runs `uv sync --frozen` would gate on a different version "
        "than CI and than the pin — regenerate the lock in the same change"
    )


def test_ci_installs_the_gate_tools_from_the_project() -> None:
    """The pin only reaches CI if CI installs the extras (not an ad-hoc tool)."""
    workflow: dict[str, Any] = yaml.safe_load(_CI.read_text(encoding="utf-8"))
    offenders: list[str] = []

    for job_name, job in workflow.get("jobs", {}).items():
        runs = [
            str(step.get("run", ""))
            for step in job.get("steps", [])
            if step.get("run")
        ]
        uses_tool = [
            r for r in runs if any(t in r for t in _GATE_TOOLS)
        ]
        if not uses_tool:
            continue

        installs_project = any(
            'pip install -e ".[dev]"' in r
            or "pip install -e '.[dev]'" in r
            or "uv sync" in r
            for r in runs
        )
        if not installs_project:
            offenders.append(
                f"{job_name}: runs {uses_tool[0].strip()!r} but never installs "
                'the project extras (`pip install -e ".[dev]"` or `uv sync`)'
            )
        for r in runs:
            for tool in _GATE_TOOLS:
                if f"pip install {tool}" in r or f"pip install --upgrade {tool}" in r:
                    offenders.append(
                        f"{job_name}: installs {tool} ad hoc ({r.strip()!r}) — "
                        "that version is not the pin, so the job's verdict is not "
                        "the pinned tool's verdict"
                    )

    assert not offenders, "\n".join(offenders)


def test_no_doc_claims_a_floor_for_a_gate_tool() -> None:
    """`DEPENDENCY_LOCK.md` quoted `ruff>=0.8.0, mypy>=1.13.0` until #528.

    A doc that describes the current policy has to describe the current policy:
    a reader who installs "mypy>=1.13.0" because the doc said so gets whatever
    pip serves, which is the thing this gate exists to prevent. Only that one
    doc is scanned on purpose — the ledger (`DEEP_OPTIMIZATION_PLAN.md`) quotes
    the old floors as *history*, and history is allowed to be out of date.
    """
    doc = _REPO / "docs" / "architecture" / "DEPENDENCY_LOCK.md"
    text = doc.read_text(encoding="utf-8")

    stale = [f"{tool}>=" for tool in _GATE_TOOLS if f"{tool}>=" in text]

    assert not stale, (
        f"{doc.name} still describes a floor for {stale}; the dev extra pins "
        "them exactly. Update the doc in the same change as the pin"
    )


def test_the_three_sources_agree() -> None:
    """One table, three columns, one answer — the whole point of #528."""
    locked = _locked_versions()
    table: dict[str, tuple[str, str | None, str | None]] = {}
    for tool in _GATE_TOOLS:
        table[tool] = (_pinned(tool), _installed(tool), locked.get(tool))

    disagreements = {
        tool: row
        for tool, row in table.items()
        if len({v for v in row if v is not None}) > 1
    }

    assert not disagreements, (
        "pin / installed / lockfile disagree (pin, installed, locked): "
        f"{disagreements}"
    )
