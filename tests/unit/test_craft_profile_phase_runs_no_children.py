r"""#541b — the adapter *profile* phase declares; it must not run anything.

`craft/adapters/protocol.py` splits an adapter into four lifecycle phases. Two of
them answer "what is this project, and what would it take to verify it"
(`detect` → `bool`, `prepare` → `RuntimeProfile`); two of them do the work
(`execute` → `ExecutionResult`, `collect_evidence` → `list[EvidenceFragment]`).
That split is the whole safety story of this lane: the profile phase runs **on
the verification host**, before anything is sandboxed, against a repository the
product does not trust.

`GradleAdapter.prepare` reached that host lane through a helper. Measured, before
this unit, in `craft/adapters/gradle_adapter.py`: `prepare()` →
`_detect_gradle_version()` → `subprocess.run([gradlew, "--version"])`. The
project's own
`gradlew` — a script shipped by the untrusted repo — executed on the machine
that is grading it, to ask one question that `gradle/wrapper/
gradle-wrapper.properties` already answers in text. `experiments/adapters.py`
refuses `sandbox_mode == "local"` for Gradle for exactly this reason ("no host
lane: untrusted Gradle test code"); the profile phase was on the wrong side of
that line while the run phase was guarded.

It also broke the suite differently per platform, which is how it shipped
(`tests/unit/test_gradle_adapter.py::test_gradle_adapter_execute_test` patches
`subprocess.run` and then asserts `mock_run.assert_called_once()`). The fixture
creates `gradlew`, not `gradlew.bat`, so on the Windows host the probe finds no
file and stays quiet (12 passed), while on the Linux CI plane the probe spawns
and the assertion reads `Expected 'run' to have been called once. Called 2
times.` Two planes, one suite, opposite verdicts — and the second call's output
never reaches `ExecutionResult` at all.

So this gate charges the *phase*, structurally:

* which methods are profile phases is derived from `AdapterProtocol`'s own
  abstract-method return annotations, not from a list of names written here;
* reachability is a same-class/same-module closure, because a spawn hidden one
  helper below `prepare` is the same host execution;
* a lifecycle method whose return type is neither half of the split is a
  finding, so a fifth phase cannot join the protocol unclassified.

The behavior legs then run the fixed product on **both** planes, by patching
`os.name`, which is the only reason this file is green on the machine where the
bug never showed. The boundary that remains, and is disclosed rather than
hidden: `collect_evidence` → `_collect_dependency_tree` still spawns
`gradlew dependencies` on the host. It is a `list[EvidenceFragment]` phase, so
this gate permits it; deleting it would silently drop a real evidence fragment
and belongs in its own decision about where the dependency tree comes from.
"""

from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from craft.adapters.gradle_adapter import GradleAdapter

REPO = Path(__file__).resolve().parents[2]
ADAPTERS_DIR = REPO / "craft" / "adapters"
PROTOCOL_PATH = ADAPTERS_DIR / "protocol.py"

#: The half of the protocol that plans. `detect` answers about the repository;
#: `prepare` answers about the toolchain. Neither is allowed to *do* anything.
PLAN_PHASE_RETURNS = frozenset({"bool", "RuntimeProfile"})

#: The half that runs, and therefore may spawn — inside the sandbox, or on the
#: host only where the lane explicitly accepts that (`execute` here).
RUN_PHASE_RETURNS = frozenset({"ExecutionResult", "list[EvidenceFragment]"})

SUBPROCESS_FUNCS = frozenset({"run", "Popen", "check_output", "check_call", "call"})
OS_SHELL_FUNCS = frozenset({"system", "popen", "spawnv", "spawnve", "execv", "execve"})
#: Names imported as bare `run`/`Popen` still reach the same child process.
BARE_SPAWN_MODULES = {"subprocess", "os"}


# --- the ruler ---------------------------------------------------------------


def _abstract_phases(protocol_path: Path = PROTOCOL_PATH) -> dict[str, str]:
    """``{method: "return annotation"}`` for `AdapterProtocol`'s abstract phases."""
    tree = ast.parse(protocol_path.read_text(encoding="utf-8"))
    protocol = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "AdapterProtocol"
        ),
        None,
    )
    assert protocol is not None, f"{protocol_path} declares no AdapterProtocol class"
    phases: dict[str, str] = {}
    for stmt in protocol.body:
        if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decorators = {ast.unparse(d) for d in stmt.decorator_list}
        if not any(d.endswith("abstractmethod") for d in decorators):
            continue
        assert stmt.returns is not None, (
            f"{protocol_path.name}::{stmt.name} is a lifecycle phase with no return "
            "annotation, so this gate cannot classify it"
        )
        phases[stmt.name] = ast.unparse(stmt.returns)
    return phases


def plan_phase_names(protocol_path: Path = PROTOCOL_PATH) -> set[str]:
    """The profile-phase names, derived — this file hard-codes no method name."""
    phases = _abstract_phases(protocol_path)
    return {name for name, ret in phases.items() if ret in PLAN_PHASE_RETURNS}


def run_phase_names(protocol_path: Path = PROTOCOL_PATH) -> set[str]:
    phases = _abstract_phases(protocol_path)
    return {name for name, ret in phases.items() if ret in RUN_PHASE_RETURNS}


def unclassified_phase_names(protocol_path: Path = PROTOCOL_PATH) -> dict[str, str]:
    """Phases that fall into neither half — a hole in this gate, so a finding."""
    return {
        name: ret
        for name, ret in _abstract_phases(protocol_path).items()
        if ret not in PLAN_PHASE_RETURNS and ret not in RUN_PHASE_RETURNS
    }


def _spawn_names_in(module: ast.Module) -> tuple[set[str], set[str]]:
    """(`subprocess`-style bare names, `os`-style bare names) pulled in by `from`."""
    bare_subprocess: set[str] = set()
    bare_os: set[str] = set()
    for node in ast.walk(module):
        if not isinstance(node, ast.ImportFrom) or node.module not in BARE_SPAWN_MODULES:
            continue
        for alias in node.names:
            local = alias.asname or alias.name
            if node.module == "subprocess" and alias.name in SUBPROCESS_FUNCS:
                bare_subprocess.add(local)
            if node.module == "os" and alias.name in OS_SHELL_FUNCS:
                bare_os.add(local)
    return bare_subprocess, bare_os


def _is_spawn(call: ast.Call, bare_subprocess: set[str], bare_os: set[str]) -> bool:
    func = call.func
    if isinstance(func, ast.Attribute):
        base = getattr(func.value, "id", "")
        return (base == "subprocess" and func.attr in SUBPROCESS_FUNCS) or (
            base == "os" and func.attr in OS_SHELL_FUNCS
        )
    if isinstance(func, ast.Name):
        return func.id in bare_subprocess | bare_os
    return False


def _internal_edges(call: ast.Call, methods: dict[str, ast.FunctionDef]) -> set[str]:
    """Calls that stay inside this class/module: `cls._x(...)` / `self._x(...)` / `_x(...)`."""
    func = call.func
    if isinstance(func, ast.Attribute):
        if getattr(func.value, "id", "") not in {"cls", "self"}:
            return set()
        return {func.attr} if func.attr in methods else set()
    if isinstance(func, ast.Name) and func.id in methods:
        return {func.id}
    return set()


def _spawn_label(call: ast.Call) -> str:
    """The spelling that reached the OS, so the report names the child, not just the caller."""
    func = call.func
    if isinstance(func, ast.Attribute):
        return f"{getattr(func.value, 'id', '?')}.{func.attr}"
    if isinstance(func, ast.Name):
        return func.id
    return "?"


def profile_spawn_sites_in_module(
    path: Path, phases: set[str], base: Path
) -> list[str]:
    """Offences as `path:line  Class  entry -> ... -> spawn`, for one adapter module."""
    module = ast.parse(path.read_text(encoding="utf-8"))
    bare_subprocess, bare_os = _spawn_names_in(module)
    module_funcs = {
        stmt.name: stmt for stmt in module.body if isinstance(stmt, ast.FunctionDef)
    }
    offenders: list[str] = []
    for cls in [n for n in module.body if isinstance(n, ast.ClassDef)]:
        methods = {
            stmt.name: stmt
            for stmt in cls.body
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        # a method may reach a module-level helper; both are the same host lane
        walkable = {**methods, **module_funcs}
        spawns = {
            name: call
            for name, fn in walkable.items()
            for call in ast.walk(fn)
            if isinstance(call, ast.Call) and _is_spawn(call, bare_subprocess, bare_os)
        }
        for entry in sorted(phases & set(methods)):
            chain = _chain_to_spawn(entry, walkable, spawns)
            if chain is not None:
                call = spawns[chain[-1]]
                offenders.append(
                    f"{path.relative_to(base).as_posix()}:{call.lineno}  {cls.name}  "
                    + " -> ".join([*chain, _spawn_label(call)])
                )
    return offenders


def _chain_to_spawn(
    entry: str,
    methods: dict[str, ast.FunctionDef],
    spawns: dict[str, ast.Call],
) -> list[str] | None:
    """BFS over the same-class/same-module call graph; returns the path, not just a bool.

    The path is the point: an offence reported as `file:line` alone reads like a
    lint hit, while `prepare -> _detect_gradle_version -> run` names the
    host execution and who ordered it.
    """
    queue: list[list[str]] = [[entry]]
    seen = {entry}
    if entry in spawns:
        return [entry]
    while queue:
        path = queue.pop(0)
        for call in ast.walk(methods[path[-1]]):
            if not isinstance(call, ast.Call):
                continue
            for nxt in _internal_edges(call, methods):
                if nxt in spawns and nxt not in seen:
                    return path + [nxt]
                if nxt in seen:
                    continue
                seen.add(nxt)
                queue.append(path + [nxt])
    return None


def profile_phase_spawn_sites(
    adapters_dir: Path = ADAPTERS_DIR, protocol_path: Path = PROTOCOL_PATH
) -> list[str]:
    phases = plan_phase_names(protocol_path)
    base = adapters_dir.parents[1]
    found: list[str] = []
    for path in sorted(adapters_dir.glob("*.py")):
        if path.name in {"protocol.py", "__init__.py"}:
            continue
        found += profile_spawn_sites_in_module(path, phases, base)
    return sorted(found)


# --- the ruler is not vacuous ------------------------------------------------


def test_the_profile_phase_names_come_from_the_protocol_itself() -> None:
    """If this list changes shape, the census changes shape with it."""
    phases = _abstract_phases()
    assert plan_phase_names() == {"detect", "prepare"}, f"got {plan_phase_names()}"
    assert run_phase_names() == {"execute", "collect_evidence"}, f"got {run_phase_names()}"
    assert set(phases) == {"detect", "prepare", "execute", "collect_evidence"}, phases


def test_a_phase_that_cannot_be_classified_is_a_finding_not_a_pass() -> None:
    """A fifth lifecycle method with a new return type must not be silently free."""
    assert unclassified_phase_names() == {}, (
        f"AdapterProtocol phases this gate cannot classify: {unclassified_phase_names()}"
    )


def test_the_census_actually_reads_the_shipped_adapter_modules() -> None:
    """Population guard: the skipped names may not become a hiding place.

    `protocol.py` and `__init__.py` are excluded because they implement no
    adapter; that skip is only honest while the *rest* is non-empty and is the
    set the product registers.
    """
    scanned = sorted(
        p.name for p in ADAPTERS_DIR.glob("*.py") if p.name not in {"protocol.py", "__init__.py"}
    )
    assert scanned, f"no adapter modules found under {ADAPTERS_DIR}"
    assert scanned == [
        "go_adapter.py",
        "gradle_adapter.py",
        "node_adapter.py",
    ], f"the census population moved without this line being re-decided: {scanned}"


# --- the shipped tree --------------------------------------------------------


def test_no_profile_phase_reaches_a_child_process() -> None:
    offenders = profile_phase_spawn_sites()
    assert not offenders, (
        "a profile phase (`detect`/`prepare`) executes code on the verification host "
        "before anything is sandboxed; these are host runs of repository-supplied "
        "build scripts:\n  " + "\n  ".join(offenders)
    )


def test_the_transitive_shape_is_caught_and_named_by_its_entry_point(
    tmp_path: Path,
) -> None:
    """Reverse control: a spawn one helper below `prepare` must still be charged.

    Written as a copy under `tmp_path` — the shipped adapter files are never
    edited to prove a gate works. `prepare -> _uses_wrapper -> _run_it` is two
    hops deep, which a method-body-only scan would have missed, and the report
    must name the entry (`prepare`) or the reader cannot tell a profile breach
    from an `execute` call site.
    """
    tree = tmp_path / "craft" / "adapters"
    tree.mkdir(parents=True)
    (tmp_path / "craft" / "__init__.py").write_text("", encoding="utf-8")
    (tree / "fake_adapter.py").write_text(
        "import subprocess\n"
        "class FakeAdapter:\n"
        "    @classmethod\n"
        "    def prepare(cls, root):\n"
        "        return cls._uses_wrapper(root)\n"
        "    @classmethod\n"
        "    def _uses_wrapper(cls, root):\n"
        "        return cls._run_it(root)\n"
        "    @classmethod\n"
        "    def _run_it(cls, root):\n"
        "        return subprocess.run([str(root / 'gradlew'), '--version'], check=False)\n"
        "    @classmethod\n"
        "    def execute(cls, root, profile):\n"
        "        return subprocess.run([str(root / 'gradlew'), 'test'], check=False)\n",
        encoding="utf-8",
    )
    offenders = profile_phase_spawn_sites(tree, PROTOCOL_PATH)
    assert len(offenders) == 1, f"expected exactly the profile-phase spawn, got {offenders}"
    assert "FakeAdapter" in offenders[0] and "prepare -> _uses_wrapper -> _run_it" in offenders[0]


def test_a_spawn_that_belongs_to_the_run_phase_stays_uncharged(tmp_path: Path) -> None:
    """The census charges the phase, not the file: `execute` spawning is its job.

    Without this leg the gate would pass on a repo where someone deleted every
    adapter child process, and it would red on the `execute()`/
    `_collect_dependency_tree()` sites that this unit deliberately left alone.
    """
    tree = tmp_path / "craft" / "adapters"
    tree.mkdir(parents=True)
    (tree / "run_only.py").write_text(
        "import subprocess\n"
        "class RunOnly:\n"
        "    @classmethod\n"
        "    def prepare(cls, root):\n"
        "        return {'ok': True}\n"
        "    @classmethod\n"
        "    def execute(cls, root, profile):\n"
        "        return subprocess.run(['make', 'test'], check=False)\n"
        "    @classmethod\n"
        "    def collect_evidence(cls, root, profile, result):\n"
        "        import os\n"
        "        return os.system('gradle dependencies')\n",
        encoding="utf-8",
    )
    assert profile_phase_spawn_sites(tree, PROTOCOL_PATH) == []


def test_a_bare_imported_spawn_name_is_a_spawn_too(tmp_path: Path) -> None:
    """`from subprocess import run` reaches the same child; the name may not hide it."""
    tree = tmp_path / "craft" / "adapters"
    tree.mkdir(parents=True)
    (tree / "bare.py").write_text(
        "from subprocess import run\n"
        "class Bare:\n"
        "    @classmethod\n"
        "    def detect(cls, root):\n"
        "        return run(['true'], check=False).returncode == 0\n",
        encoding="utf-8",
    )
    offenders = profile_phase_spawn_sites(tree, PROTOCOL_PATH)
    assert len(offenders) == 1, f"`detect` shelled out and the census read it clean: {offenders}"
    assert "detect -> run" in offenders[0]


# --- both planes, on the product --------------------------------------------


class _Recorder:
    """Stands in for `subprocess.run` and keeps every argv the adapter tried to launch."""

    def __init__(self, stdout: str = "Gradle 8.5\n") -> None:
        self.stdout = stdout
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], *args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        self.calls.append([str(a) for a in argv])
        return subprocess.CompletedProcess(list(argv), 0, self.stdout, "")


def _wrapper_project(root: Path) -> Path:
    """A Gradle tree the adapter recognizes, with a wrapper script and no `distributionUrl`."""
    (root / "build.gradle").write_text("plugins { id 'java' }\n", encoding="utf-8")
    gradlew = root / ("gradlew.bat" if os.name == "nt" else "gradlew")
    gradlew.write_text(
        "@echo off\r\n" if gradlew.name.endswith(".bat") else "#!/bin/sh\n", encoding="utf-8"
    )
    return gradlew


@pytest.mark.parametrize(
    ("plane", "wrapper_name"), [("posix", "gradlew"), ("nt", "gradlew.bat")]
)
def test_the_profile_phase_launches_no_child_on_either_plane(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, plane: str, wrapper_name: str
) -> None:
    """The CI shape, runnable from a Windows host.

    Measured pre-fix, and wider than the CI red suggested: this leg was red on
    **both** planes, because the probe only needs a wrapper script to exist
    under the plane's own name. CI saw it first because
    `tests/unit/test_gradle_adapter.py`'s fixture creates `gradlew` and never
    `gradlew.bat`, so `assert_called_once` disagreed with the product on Linux
    and agreed with it on Windows — a platform-shaped fixture, not a
    platform-shaped bug.
    """
    monkeypatch.setattr(os, "name", plane)
    (tmp_path / wrapper_name).write_text("#!/bin/sh\n", encoding="utf-8")
    recorder = _Recorder()
    monkeypatch.setattr(subprocess, "run", recorder)

    profile = GradleAdapter.prepare(tmp_path)

    assert recorder.calls == [], (
        f"the profile phase ran {recorder.calls} on the {plane} plane: `prepare` executed "
        f"the repository's own wrapper script on the verification host"
    )
    assert profile.build_tool_version == "unknown", (
        f"no declaration says which Gradle this is, so the profile must not invent one "
        f"(a host probe's answer describes the host, not the sandbox): "
        f"{profile.build_tool_version!r}"
    )


def test_the_wrapper_declaration_still_answers_without_a_child(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """What the profile *keeps*: the version is read from the checked-in text."""
    monkeypatch.setattr(os, "name", "posix")
    props = tmp_path / "gradle" / "wrapper" / "gradle-wrapper.properties"
    props.parent.mkdir(parents=True)
    props.write_text(
        "distributionUrl=https\\://services.gradle.org/distributions/gradle-8.5-bin.zip\n",
        encoding="utf-8",
    )
    recorder = _Recorder()
    monkeypatch.setattr(subprocess, "run", recorder)

    profile = GradleAdapter.prepare(tmp_path)

    assert profile.build_tool_version == "8.5"
    assert recorder.calls == [], f"reading a declaration must not run anything: {recorder.calls}"


def test_one_child_per_verified_run_counting_the_profile_phase(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`prepare()` + `execute()` = exactly one child, and it is the test run.

    This is the assertion CI was making indirectly through a mock's call count.
    Said here instead, on the posix plane, so it fails where the product is
    wrong rather than where a fixture happens to be shaped like one OS.
    """
    monkeypatch.setattr(os, "name", "posix")
    (tmp_path / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
    recorder = _Recorder(stdout="BUILD SUCCESSFUL\n5 tests completed, 0 failed, 0 skipped\n")
    monkeypatch.setattr(subprocess, "run", recorder)

    profile = GradleAdapter.prepare(tmp_path)
    GradleAdapter.execute(tmp_path, profile, goal="test")

    assert len(recorder.calls) == 1, (
        f"a verified run launched {len(recorder.calls)} children: {recorder.calls}"
    )
    assert all("--version" not in argv for argv in recorder.calls), (
        f"the run phase is the only child allowed, and it is not a version probe: {recorder.calls}"
    )
    assert "test" in recorder.calls[0], recorder.calls[0]


def test_the_profile_phase_stays_quiet_when_a_wrapper_is_executable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The pre-fix trigger, kept as a permanent witness.

    `_wrapper_project` puts a wrapper script on the posix plane, which is what
    made the deleted probe spawn. If the probe ever comes back under a
    different name, this leg — and the census above — both catch it, and neither
    depends on the host that runs the suite.
    """
    monkeypatch.setattr(os, "name", "posix")
    _wrapper_project(tmp_path)
    recorder = _Recorder()
    monkeypatch.setattr(subprocess, "run", recorder)

    assert GradleAdapter.detect(tmp_path) is True
    GradleAdapter.prepare(tmp_path)

    assert recorder.calls == [], f"`detect`/`prepare` launched: {recorder.calls}"
