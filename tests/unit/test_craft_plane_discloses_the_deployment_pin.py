"""#128 — the pinned sandbox plane must say whether it reaches the craft path.

Measured, not assumed:

- ``compose.production.yml`` worker environment pins ``SPECPROOF_SANDBOX`` to
  ``docker``, and ``tests/fault/test_malicious_build.py``
  ``TestProductionPinsDockerMode`` asserts exactly that YAML value.
- ``docs/operations/THREAT_TESTING.md`` §1 then lists that pin as the
  "缓解事实" for its own pinned gap: "显式 local 模式无隔离"
  (``TestLocalModeTamperingGapPinned``, which really runs
  ``Executor(workspace, mode="local")`` and lets a whitelisted interpreter
  overwrite ``mvnw`` / write outside the workspace / delete a critical file).
- The product's code-modifying path — ``api/agent_runtime.py`` building the
  ``CraftLoop`` — passed ``exec_mode="local"`` literally, so the pin never
  reached it. ``Executor`` only reads ``SPECPROOF_SANDBOX`` when ``mode`` is
  ``None`` (craft/executor.py: ``mode or os.getenv(...)``).
- Honouring the pin blindly would be worse than the old hard-code: craft calls
  ``run_sandboxed`` without ``profile=``, whose default profile is Maven-only,
  so a pinned docker plane would run ``pytest`` / ``npm test`` inside the java
  image. So the plane stays ``local`` here ON PURPOSE, and what lands is the
  disclosure — the job log must state that the mitigation is not in effect on
  this path, instead of the doc reading as if it were.

These cases pin the three ends of that claim: the env NAME the code reads is
the NAME the deployment sets; the note fires exactly when the pin is a plane
craft cannot honour and names the real prerequisite; and nothing may re-
hard-code a plane at the CraftLoop call site.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

import pytest
import yaml

from craft.executor import (
    SANDBOX_MODE_ENV,
    craft_plane_decision,
    sandbox_pin_from_deployment,
)
from observability.logging import JsonFormatter

REPO = Path(__file__).resolve().parents[2]
PRODUCTION_COMPOSE = REPO / "compose.production.yml"
RUNTIME_SOURCE = REPO / "api" / "agent_runtime.py"
EXECUTOR_SOURCE = REPO / "craft" / "executor.py"
RUNNER_SOURCE = REPO / "sandbox" / "runner.py"


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _worker_env() -> dict[str, Any]:
    compose = yaml.safe_load(PRODUCTION_COMPOSE.read_text(encoding="utf-8"))
    services = compose["services"]
    application = [name for name, svc in services.items() if svc.get("build")]
    assert "worker" in application, f"worker is not a built service: {application}"
    env = services["worker"]["environment"]
    assert env, "the production worker sets no environment — the probe is broken"
    return env


# ── the knob is shared by code and deployment ────────────────────


def test_the_pin_reader_reads_the_env_the_deployment_sets() -> None:
    env = _worker_env()
    keys = {item.split(":", 1)[0].strip() for item in env if isinstance(item, str)}
    # compose also carries non-string (dict/list) entries; name the population
    # that actually declares a value so "not found" cannot mean "read nothing".
    declared = {k for k in (set(env) | keys) if k}
    assert declared, "no environment knob was parsed out of the production worker"
    assert SANDBOX_MODE_ENV in declared, (
        f"the code reads {SANDBOX_MODE_ENV!r} but the production worker pins none of it "
        f"(declared: {sorted(declared)})"
    )
    assert env[SANDBOX_MODE_ENV] == "docker", (
        "this suite's premise is that production pins docker; the compose file changed"
    )


def test_the_pin_reader_is_normally_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(SANDBOX_MODE_ENV, raising=False)
    assert sandbox_pin_from_deployment() == ""
    monkeypatch.setenv(SANDBOX_MODE_ENV, "  Docker ")
    assert sandbox_pin_from_deployment() == "docker"


# ── the disclosure itself ────────────────────────────────────────


def test_an_unpinned_deployment_produces_no_note(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(SANDBOX_MODE_ENV, raising=False)
    plane, note = craft_plane_decision()
    assert plane == "local"
    assert note == "", "a dev checkout that asked for no sandbox must not be warned at"


def test_a_pinned_sandbox_is_disclosed_as_not_in_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(SANDBOX_MODE_ENV, "docker")
    plane, note = craft_plane_decision()
    assert plane == "local", (
        "craft cannot honour the pin yet (no profile selection); the note is the point"
    )
    assert SANDBOX_MODE_ENV in note and "docker" in note, (
        f"the note must name the knob and the pinned plane it does not reach: {note!r}"
    )
    assert "profile" in note, (
        f"the note must name the real prerequisite, not a vague warning: {note!r}"
    )
    assert "未生效" in note


def test_the_note_blames_a_prerequisite_that_really_holds() -> None:
    """'craft never names a profile' must be true in the shipped source."""
    run_sandboxed_calls = [
        node
        for node in ast.walk(_tree(EXECUTOR_SOURCE))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run_sandboxed"
    ]
    assert run_sandboxed_calls, "Executor no longer calls run_sandboxed at all"
    for call in run_sandboxed_calls:
        assert "profile" not in {kw.arg for kw in call.keywords if kw.arg}, (
            "craft now selects a profile — the pinned plane may be honourable, "
            "so this disclosure must be re-checked, not left claiming '未生效'"
        )

    profile_selector = next(
        node
        for node in ast.walk(_tree(RUNNER_SOURCE))
        if isinstance(node, ast.FunctionDef) and node.name == "_profile_from_env"
    )
    assert not profile_selector.args.args, (
        "the default profile selector now takes input — it may vary per command, "
        "which is the prerequisite the note claims missing"
    )
    returns = [
        node.value
        for node in ast.walk(profile_selector)
        if isinstance(node, ast.Return) and node.value is not None
    ]
    assert returns and all(
        isinstance(value, ast.Name) and value.id == "MAVEN_PROFILE" for value in returns
    ), f"_profile_from_env no longer returns MAVEN_PROFILE unconditionally: {returns}"


# ── no product path may re-hard-code a plane ─────────────────────


def test_the_runtime_asks_instead_of_inventing_a_plane() -> None:
    tree = _tree(RUNTIME_SOURCE)
    craft_loop_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CraftLoop"
    ]
    assert craft_loop_calls, "the agent runtime no longer builds a CraftLoop at all"
    for call in craft_loop_calls:
        exec_mode = next(
            (kw.value for kw in call.keywords if kw.arg == "exec_mode"), None
        )
        assert exec_mode is not None, "the product CraftLoop call dropped exec_mode"
        assert not isinstance(exec_mode, ast.Constant), (
            "exec_mode is hard-coded again — the deployment's pin would be silently "
            "overridden on the code-modifying path"
        )
        assert isinstance(exec_mode, ast.Name), (
            f"exec_mode must come from one resolved decision, got {ast.dump(exec_mode)}"
        )

    decisions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "craft_plane_decision"
    ]
    assert len(decisions) == len(craft_loop_calls), (
        f"{len(craft_loop_calls)} CraftLoop call(s) but {len(decisions)} plane "
        "decision(s): a CraftLoop is being built without asking the deployment"
    )
    warnings = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "warning"
    ]
    assert any(
        isinstance(arg, ast.Name) and arg.id == "plane_note"
        for call in warnings
        for arg in call.args
    ), "the plane note is decided but never logged — the disclosure cannot be read"


def test_the_disclosure_survives_the_json_formatter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """observability renders only ts/level/logger/message, so a note carried in
    ``extra`` would reach no reader; the facts must be in the message."""
    monkeypatch.setenv(SANDBOX_MODE_ENV, "docker")
    _plane, note = craft_plane_decision()
    assert note
    record = logging.LogRecord(
        name="api.agent_runtime",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="作业 %s craft 执行面: %s",
        args=("job-1", note),
        exc_info=None,
    )
    rendered = JsonFormatter().format(record)
    assert SANDBOX_MODE_ENV in rendered
    assert "未生效" in rendered
