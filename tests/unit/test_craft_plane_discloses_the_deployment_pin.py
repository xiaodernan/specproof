"""#128/#129 — the pinned sandbox plane must say whether it reaches the craft path.

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
  reached it. ``Executor`` only reads the pinned plane when ``mode`` is
  ``None`` (craft/executor.py: ``mode or deployment_plane_pin() or "auto"``).
- ``Executor`` now selects a container profile per command stem
  (``craft.executor.PROFILE_BY_STEM``), so a pinned docker plane no longer runs
  ``pytest``/``npm test`` inside the java image. Craft still keeps the host
  plane ON PURPOSE: the repair loop's commands are the model's choice, and the
  whitelisted stems that have no image at all (``gradle``/``cargo``, derived as
  ``ALLOWED_COMMANDS - PROFILE_BY_STEM``) would be refused on a pinned plane —
  a craft job could die on a step the sandbox cannot serve. So what lands is
  the disclosure: the job log states that the mitigation is not in effect on
  this path, instead of the doc reading as if it were.

These cases pin the four ends of that claim: the env NAME the code reads is the
NAME the deployment sets; the note fires exactly when the pin is a plane craft
does not adopt, and the blame it names is re-derived from the shipped source; an
image-less command on a pinned plane is refused before any child spawns, yet
still runs off that plane; and nothing may re-hard-code a plane at the CraftLoop
call site — including that the refusal reach the repair loop as its own code
rather than as an undiagnosed crash.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

import pytest
import yaml

from craft.executor import (
    ALLOWED_COMMANDS,
    PROFILE_BY_STEM,
    Executor,
    PlaneToolchainMissingError,
    craft_plane_decision,
    stems_without_profile,
)
from craft.tools import (
    CODE_EXECUTION_FAILED,
    CODE_PLANE_TOOLCHAIN_MISSING,
    ToolRegistry,
)
from observability.logging import JsonFormatter
from sandbox.runner import (
    SANDBOX_MODE_ENV,
    SandboxProfile,
    SandboxResult,
    deployment_plane_pin,
)

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
    assert deployment_plane_pin() == ""
    monkeypatch.setenv(SANDBOX_MODE_ENV, "  Docker ")
    assert deployment_plane_pin() == "docker"


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
        "craft still cannot adopt the pin, because some whitelisted commands have "
        f"no image at all ({sorted(stems_without_profile())}); the note is the point"
    )
    assert SANDBOX_MODE_ENV in note and "docker" in note, (
        f"the note must name the knob and the pinned plane it does not reach: {note!r}"
    )
    assert "profile" in note, (
        f"the note must name the real prerequisite, not a vague warning: {note!r}"
    )
    assert "未生效" in note


def test_the_note_blames_a_prerequisite_that_really_holds() -> None:
    """The note asserts two facts about the shipped source and both must hold:
    craft DOES name a profile on its way to the sandbox (so the pin is no longer
    defeated by the Maven-only default), and the runner's default selector is
    still a no-argument Maven constant (so a stem outside the table genuinely
    has no image to fall back to)."""
    run_sandboxed_calls = [
        node
        for node in ast.walk(_tree(EXECUTOR_SOURCE))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run_sandboxed"
    ]
    assert run_sandboxed_calls, "Executor no longer calls run_sandboxed at all"
    for call in run_sandboxed_calls:
        kwargs = {kw.arg: kw.value for kw in call.keywords if kw.arg}
        assert "profile" in kwargs, (
            "craft stopped selecting a container profile — the note's "
            "'Executor 已按命令词干选 profile' would be a lie, and a pinned plane "
            "would put every language back into the Maven image"
        )
        value = kwargs["profile"]
        assert not (isinstance(value, ast.Constant) and value.value is None), (
            "profile=None is passed literally, which re-uses the Maven-only default "
            "and reproduces exactly the defect #129 removed"
        )

    profile_selector = next(
        node
        for node in ast.walk(_tree(RUNNER_SOURCE))
        if isinstance(node, ast.FunctionDef) and node.name == "_profile_from_env"
    )
    assert not profile_selector.args.args, (
        "the default profile selector now takes input — the fallback the note "
        "claims is missing may exist, so the disclosure must be re-derived"
    )
    returns = [
        node.value
        for node in ast.walk(profile_selector)
        if isinstance(node, ast.Return) and node.value is not None
    ]
    assert returns and all(
        isinstance(value, ast.Name) and value.id == "MAVEN_PROFILE" for value in returns
    ), f"_profile_from_env no longer returns MAVEN_PROFILE unconditionally: {returns}"


def test_the_note_names_exactly_the_stems_that_have_no_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gap the note blames must be the live set difference, not two names I
    typed while gradle/cargo happened to be the missing pair."""
    monkeypatch.setenv(SANDBOX_MODE_ENV, "docker")
    _plane, note = craft_plane_decision()
    missing = stems_without_profile()
    assert missing, (
        "the disclosure exists because some whitelisted command has no image; if "
        f"{sorted(PROFILE_BY_STEM)} now covers everything, craft's plane decision "
        "has to be re-derived instead of warning about nothing"
    )
    assert set(ALLOWED_COMMANDS) == missing | set(PROFILE_BY_STEM), (
        "a whitelisted stem is in neither the routed set nor the blamed set, so "
        "the note under-reports its own gap"
    )
    assert str(sorted(missing)) in note, (
        f"the note must carry the derived set verbatim, not a paraphrase: {note!r}"
    )
    assert "profile" in note and "未生效" in note


def test_every_covered_stem_reaches_its_own_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Selection must arrive at the sandbox per stem, and must not collapse onto
    one image: a table mapping every language to Maven would satisfy a 'profile
    was passed' AST check while restoring the original wrong-toolchain failure."""
    seen: list[tuple[str, SandboxProfile | None]] = []

    def fake_run_sandboxed(**kwargs: Any) -> SandboxResult:
        seen.append((str(kwargs["command"][0]), kwargs["profile"]))
        return SandboxResult(exit_code=0, stdout="", stderr="", mode="local")

    # mode="auto" keeps Executor.python unset, so the bare stems below reach
    # run_sandboxed verbatim; a local-mode interpreter substitution would rename
    # them (see #131) and this case is about profile routing, not argv.
    monkeypatch.setattr("craft.executor.run_sandboxed", fake_run_sandboxed)
    monkeypatch.delenv("CRAFT_EXTRA_COMMANDS", raising=False)
    executor = Executor(tmp_path, mode="auto")
    for stem in sorted(PROFILE_BY_STEM):
        executor.run([stem, "--version"])
        assert seen[-1] == (stem, PROFILE_BY_STEM[stem]), (
            f"{stem} did not reach its own image: {seen[-1]!r}"
        )
    images = {profile.image for profile in PROFILE_BY_STEM.values()}
    assert len(images) >= 2, f"profile selection routes everything to one image: {images}"


def test_a_pinned_plane_refuses_an_image_less_stem_before_any_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fail-closed half: on a plane that promises isolation, a command with
    no image is neither packed into someone else's image nor quietly run on the
    host — and off that plane the very same command still runs."""
    calls: list[list[str]] = []

    def fake_run_sandboxed(**kwargs: Any) -> SandboxResult:
        calls.append([str(part) for part in kwargs["command"]])
        return SandboxResult(exit_code=0, stdout="", stderr="", mode="docker")

    monkeypatch.setattr("craft.executor.run_sandboxed", fake_run_sandboxed)
    monkeypatch.delenv("CRAFT_EXTRA_COMMANDS", raising=False)
    missing = sorted(stems_without_profile())
    assert missing, "no image-less stem exists to refuse — re-derive this gate"
    stem = missing[0]

    monkeypatch.setenv(SANDBOX_MODE_ENV, "docker")
    with pytest.raises(PlaneToolchainMissingError) as exc:
        Executor(tmp_path).run([stem, "-q", "build"])
    assert not calls, f"the refusal reached the sandbox anyway: {calls!r}"
    assert stem in str(exc.value) and "docker" in str(exc.value), str(exc.value)

    Executor(tmp_path, mode="local").run([stem, "-q", "build"])
    assert calls == [[stem, "-q", "build"]], (
        f"a refusal on the host plane is a new whitelist entry, not {stem!r} running"
    )


def test_a_stem_gets_the_image_its_language_is_pinned_by() -> None:
    """A second, independent declaration of the same mapping.

    ``test_every_covered_stem_reaches_its_own_image`` compares the call site
    against ``PROFILE_BY_STEM`` itself, so it cannot see a wrong table — mapping
    every stem to the java image would keep it green. This case states the claim
    from the runner's own profile objects instead.
    """
    from sandbox.runner import (
        MAVEN_PROFILE as RUNNER_MAVEN,
    )
    from sandbox.runner import (
        NODE_PROFILE as RUNNER_NODE,
    )
    from sandbox.runner import (
        PYTHON_PROFILE as RUNNER_PYTHON,
    )

    expected = {
        "mvn": RUNNER_MAVEN,
        "npm": RUNNER_NODE,
        "pytest": RUNNER_PYTHON,
        "python": RUNNER_PYTHON,
    }
    assert set(expected) == set(PROFILE_BY_STEM), (
        f"the two declarations cover different stems: {sorted(expected)} vs "
        f"{sorted(PROFILE_BY_STEM)}"
    )
    for stem, profile in expected.items():
        assert PROFILE_BY_STEM[stem] is profile, (
            f"{stem} must run in the {profile.name} image, not "
            f"{PROFILE_BY_STEM[stem].name} ({PROFILE_BY_STEM[stem].image})"
        )


def test_the_refusal_reaches_the_loop_as_its_own_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refusal the repair loop reads as ``EXECUTION_FAILED`` (a crash) invites
    it to retry the same command until the job goes STUCK; the reader must be
    able to tell 'this plane cannot serve it' from 'it broke'."""
    monkeypatch.setattr(
        "craft.executor.run_sandboxed",
        lambda **kwargs: SandboxResult(exit_code=0, stdout="", stderr="", mode="docker"),
    )
    monkeypatch.delenv("CRAFT_EXTRA_COMMANDS", raising=False)
    monkeypatch.setenv(SANDBOX_MODE_ENV, "docker")
    registry = ToolRegistry(tmp_path, executor=Executor(tmp_path))
    refused = registry.dispatch(
        registry.build_tool_call(
            "run_test", {"command": [sorted(stems_without_profile())[0], "-q", "build"]}
        )
    )
    assert refused.status == "denied", refused.summary
    assert refused.summary.startswith(f"[{CODE_PLANE_TOOLCHAIN_MISSING}]"), refused.summary
    assert CODE_EXECUTION_FAILED not in refused.summary, (
        "a plane that cannot serve a command is not a crash: " + refused.summary
    )
    served = registry.dispatch(registry.build_tool_call("run_test", {"command": ["mvn"]}))
    assert served.status == "ok", (
        f"a stem that HAS an image must still run on the pinned plane: {served.summary}"
    )


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
