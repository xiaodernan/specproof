"""#423 — craft's gates must serve every language the rest of the tree already names.

Measured off the delivered tree before the fix (``.scratch/m370_probe.py`` ran the
shipped gates over six one-repository fixtures):

- ``agent/preflight.py`` names 4 languages from 16 markers, and
  ``experiments/adapters.py``'s ``COMPATIBILITY_MATRIX`` declares 5 rows
  「已支持」 — including JavaScript/TypeScript (``npm test``) and Go (``go test``).
- ``craft/gates.py`` tested 4 build markers (pom.xml / build.gradle /
  pyproject.toml / setup.py) against 6 test-file patterns over 2 languages. A Go
  repository (``go.mod`` + ``sum_test.go``) and a Node repository
  (``package.json`` with ``scripts.test`` + ``src/index.test.ts``) both came back
  ``run_build=skipped`` 「未检测到构建配置」 and ``run_test=skipped`` 「未检测到测试文件」 —
  inventories that leave out the marker the repository is standing on.
- A third reading came out of the same fixture set: a Gradle-only Java repository
  reached ``run_build=passed`` (``gradle -q compileJava``) yet its test gate
  answered 「检测到 1 个 Java 测试文件但仓库无 pom.xml, mvn test 无法运行」 — after #366
  routed ``gradle`` to ``GRADLE_PROFILE``, that reason names an image and a route
  the same tree has.
- The detector itself was measured too (``.scratch/m370_probe4.py`` over two real
  trees): the 15-pattern table asked ``apps/web`` for one ``Path.glob`` per
  pattern, walked 52 raw hits in 38.40 s and kept 47, while the single pruned
  walk returned those same 47 in 0.80 s — the walk cost was never bounded by the
  ignore list, only the result was. And the ignore list is a list of *names*:
  this tree's ``.venv312`` holds 183 test-named files (``test_*.py`` 177,
  ``*_test.py`` 6) and is not named ``venv``, so all 183 survived the old
  after-the-fact filter. A virtualenv is a directory that carries
  ``pyvenv.cfg``.

Every figure below is derived from the shipped tables and the shipped functions.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, NoReturn

import pytest

from agent.preflight import _LANGUAGE_MARKERS
from craft import gates
from craft.executor import ExecResult
from craft.gates import (
    _BUILD_MARKER_INVENTORY,
    _BUILD_ROUTES,
    _TEST_GLOBS,
    _TEST_GLOBS_BY_KIND,
    _TEST_INVENTORY,
    _detect_suite_by_kind,
    compose_verdict,
    detect_test_suite,
    run_build_gate,
    run_test_gate,
)
from sandbox.runner import (
    GO_PROFILE,
    GRADLE_PROFILE,
    NODE_PROFILE,
    SANDBOX_MODE_ENV,
    SandboxProfile,
    SandboxResult,
)
from tests.unit.craft_java_disclosure import (
    java_serving,
    missing_markers_clause,
    unrunnable_commands_clause,
)

REPO = Path(__file__).resolve().parents[2]
KINDS = ("python", "java", "go", "node")


def _write(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


GO_REPO = {
    "go.mod": "module example.com/demo\n\ngo 1.22\n",
    "pkg/sum.go": "package pkg\n",
    "pkg/sum_test.go": 'package pkg\n\nimport "testing"\n\nfunc TestSum(t *testing.T) {}\n',
}
NODE_REPO = {
    "package.json": json.dumps(
        {"name": "demo", "scripts": {"test": "node --test", "build": "tsc -p ."}}, indent=2
    ),
    "src/index.test.ts": "test('ok', () => {})\n",
}
NODE_NO_SCRIPTS = {
    "package.json": json.dumps({"name": "demo", "scripts": {"lint": "eslint ."}}, indent=2),
    "src/index.spec.js": "it('ok', () => {})\n",
}
NODE_BAD_MANIFEST = {"package.json": "{not json", "src/index.spec.ts": "x\n"}
JAVA_GRADLE = {
    "build.gradle": "plugins { id 'java' }\n",
    "src/test/java/demo/DaoIT.java": "class DaoIT {}\n",
}
JAVA_NO_BUILD_FILE = {"src/test/java/demo/DemoTest.java": "class DemoTest {}\n"}


class Recorder:
    """A stand-in ExecRunner that records argv and always succeeds."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, command: list[str], *, timeout: int | None = None) -> ExecResult:
        self.calls.append(list(command))
        return ExecResult(
            command=list(command),
            exit_code=0,
            stdout="",
            stderr="",
            output_tail="",
            truncated=False,
            error="",
            mode="docker",
        )


def _sandbox_capturing(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[list[str], SandboxProfile | None]]:
    """Route the shipped Executor to a stub that records (argv, profile)."""
    seen: list[tuple[list[str], SandboxProfile | None]] = []

    def fake_run_sandboxed(**kwargs: Any) -> SandboxResult:
        seen.append((list(kwargs["command"]), kwargs["profile"]))
        return SandboxResult(exit_code=0, stdout="", stderr="", mode="docker")

    monkeypatch.setattr("craft.executor.run_sandboxed", fake_run_sandboxed)
    monkeypatch.setenv(SANDBOX_MODE_ENV, "docker")
    return seen


# ── the tables are read as one fact, and they are not empty ─────────


def test_the_two_tables_name_every_language_the_gates_dispatch() -> None:
    assert tuple(_TEST_GLOBS_BY_KIND) == KINDS, (
        f"the detector groups suites by {tuple(_TEST_GLOBS_BY_KIND)}; the gates "
        f"dispatch one command per kind in {KINDS}"
    )
    assert len(_TEST_GLOBS) >= 15, (
        f"the table carried 15 patterns when #423 measured it, now {len(_TEST_GLOBS)} "
        "— a shrunken census would make the parity legs below pass on less coverage"
    )
    route_kinds = [route.kind for route in _BUILD_ROUTES]
    assert len(route_kinds) == len(set(route_kinds)), f"duplicate build route kinds: {route_kinds}"
    markers = [marker for route in _BUILD_ROUTES for marker in route.markers]
    assert len(markers) >= 7, (
        f"the build table carried 7 markers when #423 measured it, now {len(markers)} "
        "— the same floor applies to the markers as to the patterns"
    )
    assert len(markers) == len(set(markers)), f"a marker routes two kinds: {markers}"
    for kind in KINDS:
        assert _TEST_GLOBS_BY_KIND[kind], f"{kind} is a dispatch kind with no pattern"


def test_the_build_markers_live_in_one_table_and_the_census_can_see_it() -> None:
    """#480 — the deleted copy may not come back under another name.

    ``_BUILD_MARKERS`` was a second dict of the route table's markers. It had no
    production reader, and the only test that read it compared it with its own
    derivation — so three source edits to the table and one runtime swap of it
    all left that leg green (#480 measured it). The table is the route table
    alone now, and this census refuses ANY kind-keyed table of strings in
    ``craft.gates`` besides the test-pattern table. It names the one table it
    allows, which is what keeps it from passing vacuously: a census that found
    nothing would not equal that set.
    """
    vocabulary = {route.kind for route in _BUILD_ROUTES} | set(_TEST_GLOBS_BY_KIND)
    found = {
        name: value
        for name, value in vars(gates).items()
        if isinstance(value, dict)
        and value
        and set(value) <= vocabulary
        and all(
            isinstance(entry, str)
            or (isinstance(entry, (list, tuple)) and all(isinstance(x, str) for x in entry))
            for entry in value.values()
        )
    }
    assert set(found) == {"_TEST_GLOBS_BY_KIND"}, (
        f"craft.gates holds {sorted(found)}; the build markers live in _BUILD_ROUTES, "
        "and a second copy of them can only drift away from it"
    )


def test_craft_and_preflight_agree_on_the_build_marker_vocabulary() -> None:
    known = {marker for _language, markers in _LANGUAGE_MARKERS for marker in markers}
    tested = {marker for route in _BUILD_ROUTES for marker in route.markers}
    invented = tested - known
    assert not invented, (
        f"craft tests {sorted(invented)} as build configuration while "
        "agent/preflight.py's _LANGUAGE_MARKERS does not name them — one of the two "
        "vocabularies is invented, and preflight's is the one detect_language() uses"
    )
    for language, markers in _LANGUAGE_MARKERS:
        if language == "unknown":
            continue
        served = {
            route.kind
            for route in _BUILD_ROUTES
            if set(markers) & set(route.markers)
        }
        assert served, (
            f"preflight detects {language!r} from {markers} but no craft build route "
            "carries any of them — such a repository is skipped as 「未检测到构建配置」"
        )


# ── the skip note may not name a smaller vocabulary than the code ───


_INVENTORY_RE = re.compile(r"未检测到(?:测试文件|构建配置) \(([^)]*)\)")


def test_the_skip_notes_list_exactly_what_the_code_tests(tmp_path: Path) -> None:
    bare = _write(tmp_path / "bare", {"README.md": "nothing here\n"})
    seen = []
    for gate in (run_test_gate, run_build_gate):
        result = gate(bare, executor=Recorder())
        assert result.status == "skipped", result.note
        seen.append(result.note)
    notes = "\n".join(seen)
    tokens = {
        token.strip()
        for inventory in _INVENTORY_RE.findall(notes)
        for token in inventory.split(" / ")
    }
    assert tokens, f"neither skip note carries an inventory: {seen}"
    expected = set(_TEST_GLOBS) | set(_BUILD_MARKER_INVENTORY.split(" / "))
    assert tokens == expected, (
        f"the two notes together claim craft reads {sorted(tokens)} while the tables "
        f"say {sorted(expected)} — the note is what an operator reads instead of "
        "the source, so it must be generated from the tables and not retyped"
    )
    assert "src/test 等" not in notes, (
        "the pre-#423 wording ended the inventory in 「等」, which is how 「未检测到」 "
        "came to be written about a marker the sentence never named"
    )


def test_the_inventory_is_derived_from_the_tables_not_a_second_copy(tmp_path: Path) -> None:
    """A hand-copied note cannot move with the table — the derived one already did."""
    bare = _write(tmp_path / "bare", {"README.md": "x\n"})
    build = run_build_gate(bare, executor=Recorder())
    assert build.status == "skipped", build.note
    assert _BUILD_MARKER_INVENTORY in build.note, (
        f"the note does not carry the table verbatim (table={_BUILD_MARKER_INVENTORY}): "
        f"{build.note}"
    )
    assert "go.mod" in build.note, (
        f"go.mod is in craft's own build table but the sentence an operator reads "
        f"does not name it: {build.note}"
    )
    test = run_test_gate(bare, executor=Recorder())
    assert _TEST_INVENTORY in test.note, f"the test note dropped the pattern table: {test.note}"
    # …and the other direction: preflight reads pytest.ini as a Python marker,
    # craft never does, so craft's sentence must not claim it either.
    assert "pytest.ini" not in test.note, (
        "the skip note names a marker craft does not test — the inventory drifted back "
        "to a hand-written list (preflight's, which is wider)"
    )


# ── behaviour, on the plane production pins ────────────────────────


def test_a_go_repository_builds_and_tests_in_the_go_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = _write(tmp_path, GO_REPO)
    seen = _sandbox_capturing(monkeypatch)
    build = run_build_gate(ws)
    assert build.status == "passed", build.note
    assert seen[-1] == (["go", "build", "./..."], GO_PROFILE), seen[-1]
    test = run_test_gate(ws)
    assert test.status == "passed", test.note
    assert seen[-1] == (["go", "test", "./..."], GO_PROFILE), seen[-1]
    for note in (build.note, test.note):
        assert "未检测到" not in note, note


def test_a_node_repository_runs_the_scripts_its_manifest_declares(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = _write(tmp_path, NODE_REPO)
    seen = _sandbox_capturing(monkeypatch)
    build = run_build_gate(ws)
    assert build.status == "passed", build.note
    assert seen[-1] == (["npm", "run", "build"], NODE_PROFILE), seen[-1]
    test = run_test_gate(ws)
    assert test.status == "passed", test.note
    assert seen[-1] == (["npm", "test", "--silent"], NODE_PROFILE), seen[-1]


def test_a_gradle_repositorys_java_tests_are_not_blamed_on_a_missing_pom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#366's other half: the route exists, so the reason that denies it is false."""
    ws = _write(tmp_path, JAVA_GRADLE)
    seen = _sandbox_capturing(monkeypatch)
    result = run_test_gate(ws)
    assert result.status == "passed", result.note
    assert seen[-1] == (["gradle", "-q", "test"], GRADLE_PROFILE), seen[-1]
    # The note must not blame a build file the route table HAS. The derived
    # clause is one shape of that blame and a hand-written subset is another,
    # so the markers are checked one by one.
    for marker in java_serving().markers:
        assert f"无 {marker}" not in result.note, (
            f"the note blames {marker!r} although the route table carries it: {result.note}"
        )
    assert "没有容器镜像" not in result.note, result.note

    orphan = run_test_gate(_write(tmp_path / "orphan", JAVA_NO_BUILD_FILE), executor=Recorder())
    assert orphan.status == "skipped", orphan.note
    assert missing_markers_clause() in orphan.note, orphan.note
    assert unrunnable_commands_clause() in orphan.note, orphan.note


def test_a_manifest_without_the_script_is_skipped_for_the_reason_it_names(
    tmp_path: Path,
) -> None:
    """Detected files, undeliverable command — a different fate from 「未检测到」."""
    quiet = run_test_gate(_write(tmp_path, NODE_NO_SCRIPTS), executor=Recorder())
    assert quiet.status == "skipped", quiet.note
    assert "检测到 1 个" in quiet.note, quiet.note
    assert "scripts.test" in quiet.note, quiet.note
    assert "未检测到测试文件" not in quiet.note, quiet.note

    broken = run_test_gate(_write(tmp_path / "bad", NODE_BAD_MANIFEST), executor=Recorder())
    assert broken.status == "skipped", broken.note
    assert "读不出" in broken.note, (
        f"a manifest that cannot be parsed must not be reported as one that declares "
        f"nothing: {broken.note}"
    )
    build = run_build_gate(_write(tmp_path / "bad2", NODE_BAD_MANIFEST), executor=Recorder())
    assert build.status == "skipped", build.note


def test_a_workspace_with_nothing_to_run_is_never_certified(tmp_path: Path) -> None:
    """Anti-vacuity: the stub above must not be passing every repository."""
    bare = _write(tmp_path, {"README.md": "x\n"})
    entries = [
        run_test_gate(bare, executor=Recorder()),
        run_build_gate(bare, executor=Recorder()),
    ]
    assert [entry.status for entry in entries] == ["skipped", "skipped"]
    overall, note = compose_verdict(entries)
    assert overall == "skipped", note
    assert "不认证为通过" in note, note


# ── the detector's ignore list has to bound the walk, not the result ─


def _reference_detector(workspace: Path) -> dict[str, list[str]]:
    """What craft did before #423: one glob per pattern, filtered afterwards."""
    from craft.gates import _SKIPPED_DIR_PARTS

    found: dict[str, list[str]] = {kind: [] for kind in _TEST_GLOBS_BY_KIND}
    for kind, patterns in _TEST_GLOBS_BY_KIND.items():
        for pattern in patterns:
            for target in workspace.glob(f"**/{pattern}"):
                if not target.is_file():
                    continue
                if any(part in _SKIPPED_DIR_PARTS for part in target.parts):
                    continue
                rel = target.relative_to(workspace).as_posix()
                if rel not in found[kind]:
                    found[kind].append(rel)
    return found


def test_the_pruned_walk_returns_what_the_globbing_detector_returned(tmp_path: Path) -> None:
    fixture = {
        "test_calc.py": "x",
        "tests/test_deeper.py": "x",
        "a/b/c/test_deep.py": "x",
        "legacy_old_test.py": "x",
        "src/test/java/demo/AccountControllerTest.java": "x",
        "src/test/java/demo/nested/DaoIT.java": "x",
        "src/test/java/RepoTests.java": "x",
        "src/main/java/demo/Plain.java": "x",
        "pkg/sum_test.go": "x",
        "pkg/sum.go": "x",
        "src/index.test.ts": "x",
        "src/inner/deep.spec.tsx": "x",
        "node_modules/dep/vendor.test.js": "x",
        "venv/test_ghost.py": "x",
        "__pycache__/test_cached.py": "x",
        "target/generated/TestGen.java": "x",
    }
    ws = _write(tmp_path, fixture)
    # walk order and glob order are different orders over the same census, so the
    # claim is the multiset per kind, not a sequence.
    assert {k: sorted(v) for k, v in _detect_suite_by_kind(ws).items()} == {
        k: sorted(v) for k, v in _reference_detector(ws).items()
    }, "the pruned walk and the per-pattern glob disagree on what a suite is"
    assert len(detect_test_suite(ws)) == 10, detect_test_suite(ws)


def test_the_detector_never_walks_a_directory_it_will_ignore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """pyvenv.cfg is what makes a virtualenv; its name does not.

    ``.venv312`` on this tree holds 183 test-named files and matches none of the
    names in the skip list, so the old filter counted every one of them.
    """
    ws = _write(
        tmp_path,
        {
            "tests/test_real.py": "x",
            ".venv312/pyvenv.cfg": "home = x\n",
            ".venv312/Lib/site-packages/test_numpy.py": "x",
            ".venv312/Lib/site-packages/numpy_tests/test_linalg.py": "x",
            "builds/venv_like/pyvenv.cfg": "home = x\n",
            "builds/venv_like/test_inside.py": "x",
        },
    )
    glob_calls: list[str] = []

    def no_glob(self: Path, pattern: str) -> NoReturn:
        glob_calls.append(pattern)
        raise AssertionError(f"the detector globbed {pattern!r} — the walk is unpruned again")

    monkeypatch.setattr(Path, "glob", no_glob)
    kinds = _detect_suite_by_kind(ws)
    assert glob_calls == [], f"the detector still asks Path.glob: {glob_calls}"
    assert kinds["python"] == ["tests/test_real.py"], kinds["python"]
    assert sum(len(v) for v in kinds.values()) == 1, kinds


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
