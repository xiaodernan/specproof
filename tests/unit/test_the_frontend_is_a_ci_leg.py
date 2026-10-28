"""The dashboard/Agent UI must be a CI leg, not just a local habit.

Measured on master before #507: `.github/workflows/ci.yml` had jobs for ruff,
mypy, the OpenAPI diff, security, the unit/infra suites and the eval cases —
and **nothing for `apps/web`**. No `npm`, no `tsc`, no `vitest`, no `vite`.
The local pre-push hook says "skipped npm build by default", so the only thing
standing between a broken frontend and master was somebody remembering to run
three commands by hand. The frontend happened to be green when this was
measured (tsc 0, 384 vitest cases, vite build 8.65s) — which is exactly why
nobody noticed there was no guard.

The legs pinned here are the ones the repo documents (`apps/web/package.json`):
`typecheck`, `test`, `build`. The scripts are checked too, so renaming one in
package.json turns this gate red instead of leaving a CI job that runs a
command nobody defined.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_PACKAGE_JSON = _REPO_ROOT / "apps" / "web" / "package.json"
_WEB_DIR = "apps/web"
_REQUIRED_SCRIPTS = ("typecheck", "test", "build")


def _workflow() -> dict[str, Any]:
    return yaml.safe_load(_CI.read_text(encoding="utf-8"))


def _web_steps() -> list[dict[str, Any]]:
    """Steps of the job(s) that operate inside apps/web."""
    workflow = _workflow()
    steps: list[dict[str, Any]] = []
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if step.get("working-directory") == _WEB_DIR:
                steps.append(step)
    return steps


def test_the_workflow_has_a_job_that_runs_inside_apps_web() -> None:
    assert _web_steps(), (
        "no CI step runs with working-directory: apps/web — the frontend has no "
        "automated guard (ruff/mypy/pytest are Python-only)"
    )


def test_the_frontend_leg_runs_the_three_documented_gates() -> None:
    runs = [str(step.get("run", "")) for step in _web_steps()]
    joined = "\n".join(runs)

    for script in _REQUIRED_SCRIPTS:
        assert f"npm run {script}" in joined, (
            f"CI never runs `npm run {script}` in {_WEB_DIR}; runs were: {runs}"
        )


def test_the_frontend_leg_installs_from_the_lockfile() -> None:
    runs = [str(step.get("run", "")) for step in _web_steps()]

    assert any(run.strip() == "npm ci" for run in runs), (
        "the frontend leg must install with `npm ci` (lockfile-exact); "
        f"runs were: {runs}"
    )
    assert not any(run.strip().startswith("npm install") for run in runs), (
        "`npm install` resolves versions afresh and can drift from the lockfile"
    )


def test_the_frontend_leg_pins_a_node_version() -> None:
    workflow = _workflow()
    node_steps = [
        step
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if str(step.get("uses", "")).startswith("actions/setup-node")
    ]

    assert node_steps, "no actions/setup-node step: the job would use whatever node the runner ships"
    for step in node_steps:
        with_block = step.get("with") or {}
        assert str(with_block.get("node-version", "")).strip(), (
            "setup-node without node-version pins nothing"
        )


def test_the_scripts_the_leg_calls_actually_exist() -> None:
    scripts = json.loads(_PACKAGE_JSON.read_text(encoding="utf-8"))["scripts"]

    missing = [name for name in _REQUIRED_SCRIPTS if name not in scripts]
    assert not missing, (
        f"apps/web/package.json has no {missing}; the CI legs would fail on a "
        f"command nobody defined (scripts: {sorted(scripts)})"
    )


def test_the_workflow_still_runs_on_push_and_pull_requests() -> None:
    """A job nobody triggers is not a gate."""
    triggers = _workflow().get("on", _workflow().get(True))

    assert triggers, "the workflow declares no trigger"
    assert "push" in triggers and "pull_request" in triggers
