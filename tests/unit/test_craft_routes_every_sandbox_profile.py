"""#366 — sandbox/runner.py's image roster and craft's whitelist are one fact.

Measured off the delivered tree before the fix (``.scratch/m308_probe.py`` read
the AST of both files):

- ``sandbox/runner.py`` defined **7** module-level ``SandboxProfile`` objects,
  including ``GRADLE_PROFILE`` (image ``gradle:8.10-jdk21``) and ``GO_PROFILE``
  (``golang:1.23-alpine``). Both ran on the plane production pins:
  ``experiments/adapters.py`` hands ``GRADLE_PROFILE`` to ``run_sandboxed`` at
  :1519 and ``GO_PROFILE`` at :1739.
- ``craft/executor.py`` whitelisted 6 stems and routed 4 of them. ``gradle``
  was therefore legal to ask for yet refused on a pinned plane with
  「命令词干 'gradle' 没有容器镜像」 — a sentence the same tree contradicts — and
  ``go`` was not even whitelisted while its image existed. The gap set the job
  log blames (``stems_without_profile()``) named both.
- The refusal was reachable, not hypothetical: ``craft/gates.py`` emits
  ``["gradle", "-q", "compileJava"]`` for every repository holding a
  ``build.gradle``, and ``_run_commands`` turns a raise into gate ``error``.
  ``.scratch/m308_probe2.py`` ran that shipped caller on a one-file gradle
  workspace with ``SPECPROOF_SANDBOX=docker`` and measured ``run_build
  status=error`` carrying the false reason. After the table was completed the
  same fixture measures ``status=passed`` with ``profile=GRADLE_PROFILE``
  reaching the sandbox, and the gap set shrank from ``['cargo', 'gradle']`` to
  ``['cargo']``.

So the two sides are read together here: nothing craft blames on 「no image」 may
have an image a shipped caller already uses, no image the runner defines may be
unreachable, every command the shipped gates emit must be whitelisted *and*
routable, and the threat doc that lists the routes must list exactly them.
Every figure below is derived from the AST of those files, never typed.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any

import pytest

import sandbox.runner as runner_module
from craft.executor import (
    ALLOWED_COMMANDS,
    EXTRA_COMMANDS_ENV,
    PROFILE_BY_STEM,
    Executor,
    PlaneToolchainMissingError,
    craft_plane_decision,
    effective_allowed_commands,
    stems_without_profile,
)
from craft.gates import run_build_gate
from sandbox.runner import (
    GO_PROFILE,
    GRADLE_PROFILE,
    SANDBOX_MODE_ENV,
    SandboxProfile,
    SandboxResult,
)

REPO = Path(__file__).resolve().parents[2]
RUNNER_SOURCE = REPO / "sandbox" / "runner.py"
CRAFT_DIR = REPO / "craft"
THREAT_DOC = REPO / "docs" / "operations" / "THREAT_TESTING.md"

#: Not product code. ``tests`` stays out on purpose: a profile only a test hands
#: to the sandbox is an orphan in the product, which is the drift this gate
#: exists to catch. ``bench``/``golden-cases`` are untrusted fixtures whose text
#: must not be able to green-wash the orphan clause by mentioning a name.
_PRUNED_DIR_NAMES = frozenset(
    {
        "__pycache__", "artifacts", "bench", "build", "dist", "golden-cases",
        "node_modules", "tests",
    }
)


def _pruned(dirname: str) -> bool:
    return dirname.startswith(".") or dirname in _PRUNED_DIR_NAMES


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _product_files() -> list[Path]:
    """Every product .py file, with the non-source trees pruned on the walk.

    Pruning rather than filtering matters here: the delivered tree carries a
    ``.venv312`` and a ``node_modules`` with tens of thousands of files, and a
    post-hoc filter would still pay for traversing them.
    """
    found: list[Path] = []
    for root, dirnames, filenames in os.walk(REPO):
        dirnames[:] = sorted(d for d in dirnames if not _pruned(d))
        found.extend(Path(root) / name for name in filenames if name.endswith(".py"))
    return sorted(found)


def _module_assignments(path: Path, prefix: str, suffix: str) -> dict[str, int]:
    """Module-level ``NAME = ...`` bindings whose name carries both affixes."""
    found: dict[str, int] = {}
    for node in _tree(path).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if target.id.startswith(prefix) and target.id.endswith(suffix):
            found[target.id] = node.lineno
    return found


def _roster() -> dict[str, SandboxProfile]:
    """The runner's image roster: every module-level ``X = SandboxProfile(...)``."""
    objects: dict[str, SandboxProfile] = {}
    for name, line in sorted(_module_assignments(RUNNER_SOURCE, "", "_PROFILE").items()):
        value = getattr(runner_module, name)
        assert isinstance(value, SandboxProfile), (
            f"{RUNNER_SOURCE.name}:{line} binds {name} to {type(value).__name__}, "
            "not a SandboxProfile — the roster scan is reading the wrong shape"
        )
        objects[name] = value
    return objects


def _profile_arguments_in_product_code() -> dict[str, list[str]]:
    """Where product code hands a named profile to the sandbox.

    ``run_sandboxed``'s ``profile`` is keyword-only (sandbox/runner.py:642), so a
    file without the literal ``profile=`` cannot reach it; the byte prefilter is
    that fact, and it keeps this leg from AST-parsing the whole tree (measured:
    the unprefixed walk cost the leg 26.9 s, which is a gate, not a unit test).
    """
    used: dict[str, list[str]] = {}
    for path in _product_files():
        if b"profile=" not in path.read_bytes():
            continue
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(_tree(path)):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                value = keyword.value
                if (
                    keyword.arg == "profile"
                    and isinstance(value, ast.Name)
                    and value.id.endswith("_PROFILE")
                ):
                    used.setdefault(value.id, []).append(f"{rel}:{value.lineno}")
    return used


def _default_profile_names() -> set[str]:
    """Names the runner's own default selector returns."""
    selector = next(
        node
        for node in ast.walk(_tree(RUNNER_SOURCE))
        if isinstance(node, ast.FunctionDef) and node.name == "_profile_from_env"
    )
    return {
        node.value.id
        for node in ast.walk(selector)
        if isinstance(node, ast.Return)
        and isinstance(node.value, ast.Name)
        and node.value.id.endswith("_PROFILE")
    }


def _literal_stem(node: ast.expr) -> str | None:
    """The argv[0] of a command literal.

    A plain constant reads directly; ``self.python or "python"`` (the interpreter
    substitution in ``Executor.run_pytest``) is a BoolOp whose legal stem is the
    literal it falls back to, because that is the name the whitelist judges.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            return child.value
    return None


def _command_lists(node: ast.expr) -> list[ast.List]:
    """Read ``["mvn", "-q", "test"]`` and ``[["mvn", ...], ["gradle", ...]]``."""
    if not isinstance(node, ast.List) or not node.elts:
        return []
    if all(isinstance(element, ast.List) for element in node.elts):
        return [element for element in node.elts if isinstance(element, ast.List)]
    return [node]


def _emitted_commands() -> dict[str, list[str]]:
    """Every command stem craft's shipped call sites ask the sandbox to run.

    ``subprocess.run`` is left out: that is the host, not the sandbox, and its
    argv (``git``) is not what the whitelist or the routing table governs.
    """
    found: dict[str, list[str]] = {}
    for path in sorted(CRAFT_DIR.glob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(_tree(path)):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute | ast.Name):
                continue
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "subprocess"
            ):
                continue
            attr = func.attr if isinstance(func, ast.Attribute) else func.id
            if attr not in {"run", "append", "_run_commands"}:
                continue
            for arg in node.args:
                for command in _command_lists(arg):
                    stem = _literal_stem(command.elts[0])
                    if stem is None:
                        continue
                    assert not stem.startswith("-"), (
                        f"{rel}:{node.lineno} passes a list headed by the flag "
                        f"{stem!r} to {attr}() — the scan found a mis-nested argv "
                        "and would report the wrong command vocabulary"
                    )
                    found.setdefault(stem, []).append(f"{rel}:{node.lineno}")
    return found


# ── the roster is read from the shipped objects, not from names I typed ──


def test_the_runner_roster_has_seven_images_and_no_two_share_a_name() -> None:
    roster = _roster()
    assert len(roster) >= 7, (
        f"sandbox/runner.py carried 7 module-level SandboxProfile objects when "
        f"#366 measured it; the scan now finds {len(roster)} ({sorted(roster)}) — "
        "a blind census would make every parity leg below pass on an empty set"
    )
    names = [profile.name for profile in roster.values()]
    assert len(names) == len(set(names)), f"two images share a profile name: {names}"
    for constant, profile in roster.items():
        assert profile.image, f"{constant} declares no image"
        assert re.fullmatch(r"[a-z][a-z0-9_-]*", profile.name), (
            f"{constant}.name = {profile.name!r} is not a toolchain name that the "
            "routing table and the threat doc can both spell"
        )


# ── the refusal's reason may not contradict the runner ─────────────


def test_no_refused_stem_has_an_image_the_runner_defines() -> None:
    blamed = stems_without_profile()
    assert blamed, (
        f"{sorted(ALLOWED_COMMANDS)} is now fully routed, so craft_plane_decision's "
        "gap clause and the refusal's '缺镜像的词干' list describe nothing — "
        "re-derive both before trusting this leg"
    )
    assert blamed == set(ALLOWED_COMMANDS) - set(PROFILE_BY_STEM), (
        "the gap set is not the whitelist minus the routing table, so a whitelisted "
        f"stem is in neither list: {sorted(blamed)} vs "
        f"{sorted(set(ALLOWED_COMMANDS) - set(PROFILE_BY_STEM))}"
    )
    assert set(PROFILE_BY_STEM) <= set(ALLOWED_COMMANDS), (
        "a stem is routed to an image the whitelist would never admit, so that "
        f"route is unreachable: {sorted(set(PROFILE_BY_STEM) - set(ALLOWED_COMMANDS))}"
    )
    roster = _roster()
    roster_lines = _module_assignments(RUNNER_SOURCE, "", "_PROFILE")
    images = _module_assignments(RUNNER_SOURCE, "DEFAULT_", "_IMAGE")
    for stem in sorted(blamed):
        constant = f"{stem.upper()}_PROFILE"
        assert constant not in roster, (
            f"{stem} is refused as having 「没有容器镜像」 while sandbox/runner.py "
            f"binds {constant} at line {roster_lines[constant]} — #366 measured "
            "exactly this for gradle: the refusal named an image that existed and "
            "that experiments/adapters.py was already using on the pinned plane"
        )
        assert f"DEFAULT_{stem.upper()}_IMAGE" not in images, (
            f"{stem} is blamed on a missing image while the runner binds "
            f"DEFAULT_{stem.upper()}_IMAGE at line {images['DEFAULT_' + stem.upper() + '_IMAGE']}"
        )


# ── the other direction: no image may be defined and unreachable ───


def test_every_image_the_runner_defines_reaches_a_shipped_caller() -> None:
    roster = _roster()
    routed = {
        constant
        for constant, profile in roster.items()
        if any(profile is value for value in PROFILE_BY_STEM.values())
    }
    call_sites = _profile_arguments_in_product_code()
    defaults = _default_profile_names()
    orphans = set(roster) - routed - set(call_sites) - defaults
    assert not orphans, (
        f"{sorted(orphans)} are module-level SandboxProfile objects that craft does "
        "not route, no product code passes to run_sandboxed(profile=...) and the "
        "default selector does not return — an unused image is #366's divergence "
        "seen from the other side"
    )
    assert routed, "no runner profile is reachable through craft's routing table"
    assert call_sites, (
        f"the product scan read {len(_product_files())} files and found zero "
        "profile= arguments: it is blind, so the clause above proves nothing"
    )
    assert defaults, "_profile_from_env no longer returns a named profile"


# ── the product path that actually hit the defect ──────────────────


def test_craft_never_emits_a_command_it_cannot_route() -> None:
    emitted = _emitted_commands()
    assert len(emitted) >= 3, (
        f"shipped craft code only yielded the command vocabulary {emitted}; the "
        "scan is too narrow to describe what the gates really run"
    )
    legal = effective_allowed_commands()
    unwhitelisted = {stem: where for stem, where in emitted.items() if stem not in legal}
    assert not unwhitelisted, (
        f"craft asks the sandbox to run {sorted(unwhitelisted)} at "
        f"{list(unwhitelisted.values())} which the whitelist {sorted(legal)} denies"
    )
    unrouted = {stem: where for stem, where in emitted.items() if stem not in PROFILE_BY_STEM}
    # gradle is the case #366 measured: run_build_gate emits it for every
    # build.gradle repository, the routing table did not carry it, and the gate
    # arrived in `error` state with a reason the runner contradicted.
    assert not unrouted, (
        f"{sorted(unrouted)} are emitted by shipped craft code at "
        f"{[w for where in unrouted.values() for w in where]} but route to no "
        "image, so a pinned plane errors out instead of building the repository"
    )


def test_a_gradle_repository_builds_in_the_gradle_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shipped caller, on the plane production pins, measured both ways.

    Before #366 this returned ``status=error`` with 「命令词干 'gradle' 没有容器
    镜像」; the profile that proves that reason false is GRADLE_PROFILE, which
    experiments/adapters.py had been passing to the same runner all along.
    """
    (tmp_path / "build.gradle").write_text("plugins { id 'java' }\n", encoding="utf-8")
    seen: list[tuple[list[str], SandboxProfile | None]] = []

    def fake_run_sandboxed(**kwargs: Any) -> SandboxResult:
        seen.append((list(kwargs["command"]), kwargs["profile"]))
        return SandboxResult(exit_code=0, stdout="", stderr="", mode="docker")

    monkeypatch.setattr("craft.executor.run_sandboxed", fake_run_sandboxed)
    monkeypatch.delenv(EXTRA_COMMANDS_ENV, raising=False)
    monkeypatch.setenv(SANDBOX_MODE_ENV, "docker")

    result = run_build_gate(tmp_path)
    assert result.status == "passed", f"run_build did not build the repo: {result.note}"
    assert seen, "the gradle gate never reached the sandbox — 'passed' proves nothing"
    assert seen[0][1] is GRADLE_PROFILE, (
        f"build.gradle must compile in the gradle image, got "
        f"{seen[0][1].name if seen[0][1] else 'no profile at all'}"
    )
    assert "没有容器镜像" not in result.note, result.note

    go_seen: list[SandboxProfile | None] = []

    def record_profile(**kwargs: Any) -> SandboxResult:
        go_seen.append(kwargs["profile"])
        return SandboxResult(exit_code=0, stdout="", stderr="", mode="docker")

    monkeypatch.setattr("craft.executor.run_sandboxed", record_profile)
    Executor(tmp_path).run(["go", "test", "./..."])
    assert go_seen == [GO_PROFILE], (
        f"go reached the sandbox as {go_seen[0]}; GO_PROFILE existed while craft "
        "refused the stem outright"
    )


def test_a_workspace_without_markers_is_still_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Anti-vacuity for the leg above: the stub must not be passing everything."""
    calls: list[list[str]] = []

    def fake_run_sandboxed(**kwargs: Any) -> SandboxResult:
        calls.append(list(kwargs["command"]))
        return SandboxResult(exit_code=0, stdout="", stderr="", mode="docker")

    monkeypatch.setattr("craft.executor.run_sandboxed", fake_run_sandboxed)
    monkeypatch.delenv(EXTRA_COMMANDS_ENV, raising=False)
    monkeypatch.setenv(SANDBOX_MODE_ENV, "docker")
    result = run_build_gate(tmp_path)
    assert result.status == "skipped", result.note
    assert calls == [], f"a marker-less repo ran a build anyway: {calls}"


# ── the operator-side extension must be judged and disclosed ───────


def test_an_operator_appended_stem_is_legal_and_named_as_unservable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``CRAFT_EXTRA_COMMANDS`` widens what a job may ask for, so the two lists
    that say what the plane *cannot* serve have to widen with it. Pre-#366 they
    read ``ALLOWED_COMMANDS`` only: an appended stem was legal to request and
    absent from the job-log note and from the refusal's own inventory."""
    monkeypatch.setenv(EXTRA_COMMANDS_ENV, "Rust, cargo-c")
    monkeypatch.setenv(SANDBOX_MODE_ENV, "docker")
    legal = effective_allowed_commands()
    assert {"rust", "cargo-c"} <= legal, f"the knob is not appended: {sorted(legal)}"
    blamed = stems_without_profile()
    assert {"rust", "cargo-c"} <= blamed, (
        f"appended stems absent from the gap set: {sorted(blamed)}"
    )
    _plane, note = craft_plane_decision()
    assert "'cargo-c'" in note and "'rust'" in note, (
        f"the job log still blames only the shipped whitelist: {note!r}"
    )
    with pytest.raises(PlaneToolchainMissingError) as exc:
        Executor(tmp_path).run(["rust", "build"])
    assert "rust" in str(exc.value) and "cargo-c" in str(exc.value), str(exc.value)


# ── the doc that lists the routes must list exactly them ───────────


_PAIR_RE = re.compile(r"([a-z]+(?:·[a-z]+)*)→([A-Z][A-Z0-9_]*_PROFILE)")
_GAP_RE = re.compile(r"无镜像的白名单词干只剩([^,。/]*)")


def test_the_threat_doc_carries_exactly_the_shipped_routes() -> None:
    roster = _roster()
    const_by_profile = {id(profile): constant for constant, profile in roster.items()}
    text = THREAT_DOC.read_text(encoding="utf-8")
    documented: set[tuple[str, str]] = {
        (stem, constant)
        for group, constant in _PAIR_RE.findall(text)
        for stem in group.split("·")
    }
    expected = {(stem, const_by_profile[id(profile)]) for stem, profile in PROFILE_BY_STEM.items()}
    assert documented == expected, (
        "docs/operations/THREAT_TESTING.md §1 and craft/executor.py's routing table "
        f"disagree — doc {sorted(documented)} vs code {sorted(expected)}. The table "
        "is the fact; the paragraph is the mitigation claim an operator reads "
        "instead of the source."
    )
    gaps = _GAP_RE.findall(text)
    assert gaps, f"{THREAT_DOC.name} no longer states which whitelisted stem has no image"
    claimed = {token.strip() for token in gaps[0].split("、") if token.strip()}
    assert claimed == stems_without_profile(), (
        f"the doc blames {sorted(claimed)} for having no image while the derived gap "
        "set is "
        f"{sorted(stems_without_profile())} — #366 removed gradle from that sentence "
        "because GRADLE_PROFILE always existed"
    )
