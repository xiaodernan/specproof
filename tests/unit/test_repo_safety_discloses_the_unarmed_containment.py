"""#130 — repo_safety must know which plane the deployment pinned, and say when
its containment guard is not armed.

Measured, not assumed:

- ``compose.production.yml`` pins the worker to ``SPECPROOF_SANDBOX: docker``
  and runs untrusted repositories there; the worktrees ``prepare_base`` /
  ``prepare_head`` create are the directories mounted into those sandbox
  containers (``TMPDIR=/workspaces`` is the shared volume).
- ``agent/repo_safety.py`` guards exactly that hand-off:
  ``repo_under_allowed_root`` refuses a repository outside the allowed root, and
  the sandbox branch of ``execution_mode_signal`` fails closed without one.
  Both are armed only by ``SPECPROOF_EXEC_MODE`` / ``SPECPROOF_ALLOWED_ROOT``,
  and no shipped deployment sets either one -- the two ``monkeypatch.setenv``
  calls in ``tests/unit/test_repo_safety.py`` were the only sites in the
  repository. So on the plane that promises containment the module answered
  "local mode: host filesystem access allowed" and its fail-closed branch was
  dead code.
- The "not enforced" admission already existed in ``report.warnings``, and no
  product reader touched that list: both prepare nodes read ``ok`` and
  ``fail_reason`` only, so the guard's own admission was discarded.

What lands is the disclosure, not enforcement: arming containment on a
deployment that sets no root would fail every job closed instead of fixing
anything, and adding the root to ``compose.production.yml`` changes production
behaviour.  These cases pin that the plane name has one shipped definition (the
code reads the name the deployment sets), that the note fires exactly on a
containment-promising pin whose guard is unarmed and names the real
prerequisites, that the note rides the report without changing the verdict, and
that ``warnings`` now has a reader -- every module that asks for a safety report
reads and logs its warnings, in a shape the shipped log renderer preserves.
"""

from __future__ import annotations

import ast
import logging
import os
from pathlib import Path
from typing import Any

import pytest
import yaml

from agent.nodes import prepare_base, prepare_head
from agent.repo_safety import (
    ALLOWED_ROOT_ENV,
    CHECK_EXECUTION_MODE_SIGNAL,
    CHECK_REPO_UNDER_ALLOWED_ROOT,
    DEFAULT_EXEC_MODE,
    EXEC_MODE_ENV,
    SafetyCheck,
    SafetyReport,
    check_repo_safety,
    safety_plane_truth,
)
from observability.logging import JsonFormatter
from sandbox.runner import ISOLATION_PLANES, SANDBOX_MODE_ENV

REPO = Path(__file__).resolve().parents[2]
PRODUCTION_COMPOSE = REPO / "compose.production.yml"
PIN_OWNER = "sandbox/runner.py"

#: Directories that are not shipped product code (harnesses, vendored trees,
#: generated artifacts).  Named here so an empty population cannot masquerade
#: as "nothing hand-types the pin name".
NON_PRODUCT_PARTS: frozenset[str] = frozenset(
    {
        ".git", ".venv", ".venv312", "node_modules", "bench", ".scratch",
        "tests", "scripts", "docs", "experiments", "evidence", "data",
    }
)
#: Packages that must appear in the walked population, otherwise "clean" only
#: proves the walk read nothing.
REQUIRED_PACKAGES: tuple[str, ...] = ("agent", "api", "craft", "sandbox", "storage")


def _rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def _product_python_files() -> list[Path]:
    """Every shipped ``*.py`` under the repo, with non-product trees pruned
    before descent (an unpruned walk would wander into ``node_modules`` and
    measure the wrong population at the wrong speed)."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(REPO):
        parts = set(Path(dirpath).relative_to(REPO).parts) & NON_PRODUCT_PARTS
        if parts:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in NON_PRODUCT_PARTS]
        found += [Path(dirpath) / name for name in filenames if name.endswith(".py")]
    return sorted(found)


def _worker_env() -> dict[str, Any]:
    compose = yaml.safe_load(PRODUCTION_COMPOSE.read_text(encoding="utf-8"))
    services = compose["services"]
    assert "worker" in services, f"no worker service in {sorted(services)}"
    env = services["worker"]["environment"]
    assert env, "the production worker sets no environment -- the probe is broken"
    return env


# ── one name, one owner ──────────────────────────────────────────


def test_the_pin_name_has_exactly_one_definition_in_product_code() -> None:
    files = _product_python_files()
    assert files, f"the census walked nothing under {REPO}"
    for package in REQUIRED_PACKAGES:
        assert any(_rel(path).startswith(f"{package}/") for path in files), (
            f"{package}/ is missing from the walked population ({len(files)} file(s)) "
            "-- the census read nothing it could vouch for"
        )

    definitions: list[str] = []
    literals: list[str] = []
    callers: set[str] = set()
    for path in files:
        relative = _rel(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        declared_values = {
            id(node.value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and node.value.value == SANDBOX_MODE_ENV
            for _target in node.targets
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and id(node.value) in declared_values:
                definitions += [f"{relative}:{node.lineno} {getattr(t, 'id', '?')}"
                               for t in node.targets]
            elif (
                isinstance(node, ast.Constant)
                and node.value == SANDBOX_MODE_ENV
                and id(node) not in declared_values
            ):
                # Exact equality: prose that merely mentions the knob in a
                # docstring is a different constant and stays out of this list.
                literals.append(f"{relative}:{node.lineno}")
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "deployment_plane_pin"
            ):
                callers.add(relative)

    assert len(definitions) == 1, (
        f"{SANDBOX_MODE_ENV!r} must be declared exactly once so code and "
        f"deployment cannot drift apart: {definitions}"
    )
    assert definitions[0].startswith(f"{PIN_OWNER}:"), (
        f"the shared declaration is at {definitions[0]}: sandbox.runner owns the "
        "plane knob because it is the lowest layer both craft and the agent "
        "pipeline already depend on (it imports nothing from them)"
    )
    assert not literals, (
        f"{SANDBOX_MODE_ENV!r} is hand-typed outside its owner's declaration, so a "
        f"reader could judge a plane the deployment never pinned: {literals}"
    )
    # The floor that makes "no stray spellings" mean "readers go through the
    # helper", not "nothing reads the knob at all".
    for required in (PIN_OWNER, "agent/repo_safety.py", "craft/executor.py", "craft/gates.py"):
        assert required in callers, (
            f"{required} no longer resolves the execution plane through "
            f"deployment_plane_pin(); the shipped callers are {sorted(callers)}"
        )


# ── the deployment fact the note is allowed to claim ─────────────


def test_the_production_worker_pins_the_plane_but_arms_no_containment() -> None:
    env = _worker_env()
    declared = {key for key in env if isinstance(key, str)}
    assert SANDBOX_MODE_ENV in declared, (
        f"the worker no longer pins {SANDBOX_MODE_ENV}: {sorted(declared)}"
    )
    pinned = str(env[SANDBOX_MODE_ENV])
    assert pinned in ISOLATION_PLANES, (
        "this suite's premise is that production pins a plane whose promise is "
        f"isolation; the compose value is {pinned!r} and the isolation planes "
        f"are {sorted(ISOLATION_PLANES)}"
    )
    assert EXEC_MODE_ENV not in declared and ALLOWED_ROOT_ENV not in declared, (
        f"the worker now arms containment itself ({sorted(declared)}) -- the "
        "disclosure must be re-derived, not left claiming the guard is unarmed"
    )


def test_a_pinned_container_plane_is_disclosed_as_unarmed_containment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(SANDBOX_MODE_ENV, "docker")
    monkeypatch.delenv(EXEC_MODE_ENV, raising=False)
    monkeypatch.delenv(ALLOWED_ROOT_ENV, raising=False)
    mode, note = safety_plane_truth()
    assert mode == DEFAULT_EXEC_MODE, (
        "repo_safety still decides on the un-armed default -- that is the fact "
        "the note exists to tell the operator, not a licence to hide it"
    )
    assert SANDBOX_MODE_ENV in note and "docker" in note, (
        f"the note must name the knob and the pinned plane: {note!r}"
    )
    assert EXEC_MODE_ENV in note and ALLOWED_ROOT_ENV in note, (
        f"the note must name both missing arming knobs so the operator has the "
        f"fix in the same line: {note!r}"
    )
    assert CHECK_REPO_UNDER_ALLOWED_ROOT in note, (
        f"the note must name the check that is not armed: {note!r}"
    )


def test_an_explicitly_armed_mode_silences_the_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(SANDBOX_MODE_ENV, "docker")
    monkeypatch.setenv(EXEC_MODE_ENV, "sandbox")
    monkeypatch.setenv(ALLOWED_ROOT_ENV, str(REPO))
    mode, note = safety_plane_truth()
    assert mode == "sandbox"
    assert note == "", (
        f"the deployment armed the guard explicitly, so the note may not still "
        f"claim it is unarmed: {note!r}"
    )


def test_an_unpinned_deployment_has_nothing_to_disclose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(SANDBOX_MODE_ENV, raising=False)
    monkeypatch.delenv(EXEC_MODE_ENV, raising=False)
    mode, note = safety_plane_truth()
    assert mode == DEFAULT_EXEC_MODE
    assert note == "", f"no isolation plane was pinned, so nothing may be claimed: {note!r}"


def test_the_note_rides_the_report_without_changing_the_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(SANDBOX_MODE_ENV, "docker")
    monkeypatch.delenv(EXEC_MODE_ENV, raising=False)
    monkeypatch.delenv(ALLOWED_ROOT_ENV, raising=False)
    report = check_repo_safety(
        repo_path=str(tmp_path / "does-not-exist"),
        ref="HEAD",
        worktree_target=str(tmp_path / "wt"),
    )
    assert any(
        SANDBOX_MODE_ENV in warning for warning in report.warnings
    ), f"the safety report dropped the plane disclosure: {report.warnings}"
    assert not report.ok, (
        "a missing repository must still fail -- the disclosure rides the "
        "report, it does not replace the verdict"
    )
    signal = next(
        (check for check in report.checks if check.name == CHECK_EXECUTION_MODE_SIGNAL),
        None,
    )
    assert signal is not None and signal.passed, (
        f"landing the disclosure may not flip execution_mode_signal: {signal}"
    )


# ── the warnings list must have a product reader ─────────────────


def _safety_report_readers() -> dict[Path, ast.Module]:
    readers: dict[Path, ast.Module] = {}
    for package in ("agent", "api", "craft"):
        for path in (REPO / package).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            called = {
                node.func.id
                for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            }
            if "check_repo_safety" in called:
                readers[path] = tree
    return readers


def test_every_module_that_asks_for_a_safety_report_reads_its_warnings() -> None:
    readers = _safety_report_readers()
    assert len(readers) >= 2, (
        "the shipped callers of check_repo_safety must be on record, got "
        f"{sorted(_rel(path) for path in readers)}"
    )
    blind: list[str] = []
    for path, tree in readers.items():
        report_names = {
            target.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "check_repo_safety"
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        assert report_names, f"{_rel(path)} calls check_repo_safety without binding it"
        if not any(
            isinstance(node, ast.Attribute)
            and node.attr == "warnings"
            and isinstance(node.value, ast.Name)
            and node.value.id in report_names
            for node in ast.walk(tree)
        ):
            blind.append(_rel(path))
    assert not blind, (
        "these modules trust a safety report but never read its warnings, so an "
        f"unarmed guard would be discarded silently: {blind}"
    )


@pytest.mark.parametrize(
    ("node_name", "module", "node", "ref_key", "workspace_key"),
    [
        pytest.param(
            "prepare_base",
            prepare_base,
            prepare_base.prepare_base_node,
            "base_ref",
            "base_workspace",
            id="base",
        ),
        pytest.param(
            "prepare_head",
            prepare_head,
            prepare_head.prepare_head_node,
            "head_ref",
            "head_workspace",
            id="head",
        ),
    ],
)
def test_a_shipped_prepare_node_logs_the_warnings_and_they_survive_the_renderer(
    node_name: str,
    module: Any,
    node: Any,
    ref_key: str,
    workspace_key: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The behavioural end: the disclosure is only real if running the shipped
    node puts it into a record the shipped JsonFormatter still renders.  A
    warning carried in ``extra`` would vanish (observability emits only
    ts/level/logger/message), and a node that never reads ``warnings`` would
    keep the guard silent."""
    monkeypatch.setenv(SANDBOX_MODE_ENV, "docker")
    monkeypatch.delenv(EXEC_MODE_ENV, raising=False)
    _mode, note = safety_plane_truth()
    assert note, "no disclosure to log -- re-derive this case"
    monkeypatch.setattr(
        module,
        "check_repo_safety",
        lambda **_kwargs: SafetyReport(
            ok=True,
            checks=[
                SafetyCheck(
                    name=CHECK_EXECUTION_MODE_SIGNAL, passed=True, detail="stubbed"
                )
            ],
            warnings=[note],
        ),
    )

    ref_key = "base_ref" if node_name == "prepare_base" else "head_ref"
    workspace_key = "base_workspace" if node_name == "prepare_base" else "head_workspace"
    with caplog.at_level(logging.WARNING):
        result = node(
            {"repo_path": str(tmp_path), ref_key: "no-such-ref", "job_id": "j-130"}
        )

    assert result[workspace_key] == "", (
        f"a bogus ref must still fail the {node_name} node -- this case reads the "
        f"warning path on a job that never got a workspace, not a success path: "
        f"{result}"
    )
    records = [
        record for record in caplog.records if record.name == f"agent.nodes.{node_name}"
    ]
    assert any(note in record.getMessage() for record in records), (
        f"the {node_name} node discarded the report's warnings: "
        f"{[record.getMessage() for record in records]}"
    )
    logged = next(record for record in records if note in record.getMessage())
    assert logged.levelno == logging.WARNING, (
        f"an operator's default level filters out a disclosed containment gap: "
        f"{logged.levelname}"
    )
    assert "j-130" in logged.getMessage(), (
        "the disclosure must name the job it was decided for, or it cannot be "
        f"attributed in a worker log: {logged.getMessage()!r}"
    )
    rendered = JsonFormatter().format(logged)
    for fact in (SANDBOX_MODE_ENV, EXEC_MODE_ENV, ALLOWED_ROOT_ENV):
        assert fact in rendered, (
            f"{fact} reached the log record but not the rendered line, so no "
            f"reader sees the fix: {rendered}"
        )
