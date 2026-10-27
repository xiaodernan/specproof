"""#426 — a gate may not count a test file that nothing dispatches.

Measured on the shipped tree before the repair (``.scratch/dispatch_probe.py``,
artifacts ``.scratch/dispatch_probe.txt`` / ``.scratch/dispatch_probe_after.txt``).
``run_test_gate`` read its four buckets through hand-copied subscripts
(``by_kind["python"] / ["java"] / ["go"] / ["node"]``) out of the dict whose keys
come from ``_TEST_GLOBS_BY_KIND``, and three more subscripts named
``_BUILD_MARKERS["maven"] / ["gradle"]``. Both directions of drift were measured:

- one row removed from the vocabulary (``go``) → ``KeyError: 'go'`` escaped a
  function declared ``-> GateResult``. ``GatePipeline`` happened to catch it
  (``run_test=error``), so the leak only showed on the direct call path — the one
  craft's own tool surface uses. ``run_typecheck_gate`` raised ``KeyError:
  'gradle'`` the same way once a row left ``_BUILD_ROUTES``.
- one row added (``rust``: ``*_test.rs``) → nothing raised. A python+rust
  repository came back ``status=passed`` with the note 「检测到 2 个测试文件; python
  -m pytest -q: 通过」 while only pytest had been asked to run, and
  ``detect_test_suite`` returned both files. Through the shipped pipeline that
  came back ``overall=skipped`` with ``run_test=passed`` — the silent half of the
  pair, and the one nobody spots in a report.

``run_build_gate`` already refused the second shape (its ``raise AssertionError``
landed with #423), so the two gates disagreed about what an unrouted kind means.
The repair makes the test dispatch walk the detector's own buckets and refuse any
kind no branch answers, and moves Java's build-file/command knowledge into
``_BuildRoute.language`` + ``test_command`` so the 「均无法运行」 disclosure is read
from the route table at call time instead of naming maven and gradle twice.
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

from craft import gates
from craft.executor import ExecResult
from craft.gates import (
    _BUILD_ROUTES,
    _TEST_GLOBS_BY_KIND,
    GatePipeline,
    GateResult,
    detect_test_suite,
    run_build_gate,
    run_test_gate,
    run_typecheck_gate,
)
from craft.schemas import ChangeBundle
from tests.unit.craft_java_disclosure import (
    missing_markers_clause,
    unrunnable_commands_clause,
)

GATE_SOURCE = (Path(__file__).resolve().parents[2] / "craft" / "gates.py").read_text(
    encoding="utf-8"
)

PY_FILE = {"test_calc.py": "def test_x():\n    assert True\n"}
JAVA_FILE = {"src/test/java/demo/DemoTest.java": "class DemoTest {}\n"}
GO_FILE = {"pkg/sum_test.go": 'package pkg\n\nimport "testing"\n\nfunc TestSum(t *testing.T) {}\n'}
NODE_FILE = {"src/index.test.ts": "test('ok', () => {})\n"}
NODE_NO_SCRIPT = {
    "package.json": json.dumps({"name": "d", "scripts": {"lint": "eslint ."}}),
    **NODE_FILE,
}


def _write(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


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


def _replace_vocabulary(monkeypatch: pytest.MonkeyPatch, table: dict[str, tuple[str, ...]]) -> None:
    """Swap the kind→pattern table the way a source edit would: matchers too.

    ``_compile_matchers`` is the module's own derivation, so the leg borrows the
    producer instead of copying its comprehension.
    """
    monkeypatch.setattr(gates, "_TEST_GLOBS_BY_KIND", table)
    monkeypatch.setattr(gates, "_TEST_MATCHERS", gates._compile_matchers(table))


def _route(kind: str) -> gates._BuildRoute:
    return next(route for route in _BUILD_ROUTES if route.kind == kind)


def _dispatched_kinds() -> set[str]:
    return set(re.findall(r'kind == "([a-z]+)"', inspect.getsource(run_test_gate)))


# ── the rosters are gone; each dispatch chain answers its own table ──


def _literal_kind_subscripts(source: str, kinds: set[str]) -> list[str]:
    """Every ``NAME["kind"]`` in the source, for the kinds the tables name."""
    vocabulary = "|".join(sorted(kinds))
    pattern = re.compile(r"\b[_A-Za-z][_A-Za-z0-9]*\[\s*['\"](?:" + vocabulary + r")['\"]\s*\]")
    return pattern.findall(source)


def test_no_kind_is_read_out_of_a_table_by_a_hand_copied_subscript() -> None:
    assert GATE_SOURCE.count("by_kind[") == 0, "a bucket is still read by a literal kind name"
    # #480: the old belt counted the literal ``_BUILD_MARKERS["`` — a string the
    # module no longer holds, so the belt could only ever stay green. The
    # census is name-agnostic now: ANY table read by a literal kind name, with
    # the vocabulary taken from the two tables themselves.
    vocabulary = {route.kind for route in _BUILD_ROUTES} | set(_TEST_GLOBS_BY_KIND)
    assert _literal_kind_subscripts(GATE_SOURCE, vocabulary) == [], (
        "a table is read by a literal kind name: "
        f"{_literal_kind_subscripts(GATE_SOURCE, vocabulary)}"
    )
    # carriers: without these the two assertions above would pass on a file that
    # never reads those tables at all.
    assert "for kind, bucket in by_kind.items()" in GATE_SOURCE
    assert GATE_SOURCE.count("_java_serving()") >= 3, (
        "the Java disclosure is expected to be read from the route table at call time "
        f"(definition + 2 readers), found {GATE_SOURCE.count('_java_serving()')}"
    )


def test_the_literal_kind_census_can_still_see_the_shape_it_forbids() -> None:
    """Anti-vacuity: a census that cannot find a planted subscript proves nothing."""
    assert _literal_kind_subscripts('markers["maven"]', {"maven"}) == ['markers["maven"]']
    assert _literal_kind_subscripts("markers['java']", {"maven", "java"}) == ["markers['java']"]
    assert _literal_kind_subscripts('markers["maven"]', {"gradle"}) == []


def test_the_test_dispatch_answers_exactly_the_kinds_the_table_names() -> None:
    body = inspect.getsource(run_test_gate)
    assert _dispatched_kinds() == set(_TEST_GLOBS_BY_KIND), (
        f"the vocabulary names {sorted(_TEST_GLOBS_BY_KIND)} but the dispatch chain "
        f"answers {sorted(_dispatched_kinds())} — a counted kind with no branch is the "
        "fake-pass shape, and a branch with no kind is dead code"
    )
    assert re.search(r'\n        else:\n            raise AssertionError', body), (
        "the chain has to end by refusing an unanswered kind, not by falling through "
        "to whatever command list happens to exist"
    )


def test_the_build_dispatch_answers_exactly_the_kinds_the_route_table_names() -> None:
    body = inspect.getsource(run_build_gate)
    dispatched = set(re.findall(r'route\.kind == "([a-z]+)"', body))
    named = {route.kind for route in _BUILD_ROUTES}
    assert dispatched == named, f"{sorted(dispatched)} vs {sorted(named)}"
    assert re.search(r"\n        else:\n            raise AssertionError", body), (
        "run_build_gate's refusal is the twin the test gate now has to keep"
    )


# ── Java: one declaration, read at call time ───────────────────────


def test_the_java_view_is_the_language_column_in_dispatch_order() -> None:
    serving = gates._java_serving()
    routes = tuple(route for route in _BUILD_ROUTES if route.language == "java")
    assert routes, "no route declares itself Java"
    assert serving.routes == routes
    assert serving.markers == tuple(m for r in routes for m in r.markers)
    assert serving.stems == tuple(r.test_command[0] for r in routes if r.test_command)


def test_a_third_java_route_moves_the_honest_note_with_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Derivation, not equality: change the table and the sentence has to follow."""
    ws = _write(tmp_path, JAVA_FILE)
    monkeypatch.setattr(
        gates,
        "_BUILD_ROUTES",
        (*_BUILD_ROUTES, gates._BuildRoute("bazel", ("BUILD.bazel",), "java", ("bazel", "test"))),
    )
    result = run_test_gate(ws, executor=Recorder())
    assert "BUILD.bazel" in result.note, result.note
    assert missing_markers_clause() in result.note, result.note
    assert unrunnable_commands_clause() in result.note, result.note


def test_a_java_route_that_declares_no_test_command_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control behind ``elif not present.test_command`` has to be reachable."""
    ws = _write(tmp_path, {"build.gradle": "plugins { id 'java' }\n", **JAVA_FILE})
    monkeypatch.setattr(
        gates,
        "_BUILD_ROUTES",
        tuple(
            gates._BuildRoute(route.kind, route.markers, route.language, ())
            if route.kind == "gradle"
            else route
            for route in _BUILD_ROUTES
        ),
    )
    with pytest.raises(AssertionError) as raised:
        run_test_gate(ws, executor=Recorder())
    assert "gradle" in str(raised.value), raised.value
    assert "test_command" in str(raised.value), raised.value


def test_the_maven_route_outranks_gradle_because_the_table_orders_it_first(tmp_path: Path) -> None:
    ws = _write(
        tmp_path,
        {"pom.xml": "<project/>\n", "build.gradle": "plugins { id 'java' }\n", **JAVA_FILE},
    )
    recorder = Recorder()
    result = run_test_gate(ws, executor=recorder)
    assert recorder.calls == [list(_route("maven").test_command)], (recorder.calls, result.note)


# ── the two measured fates, both directions ────────────────────────


def test_a_vocabulary_row_removed_still_answers_with_a_gate_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = {kind: patterns for kind, patterns in _TEST_GLOBS_BY_KIND.items() if kind != "go"}
    _replace_vocabulary(monkeypatch, table)
    result = run_test_gate(_write(tmp_path / "py", PY_FILE), executor=Recorder())
    assert isinstance(result, GateResult), type(result)
    assert result.status == "passed", result.note
    assert "go test" not in result.note, result.note
    bare_go = _write(tmp_path / "go", {"go.mod": "module example.com/demo\n", **GO_FILE})
    skipped = run_test_gate(bare_go, executor=Recorder())
    assert skipped.status == "skipped", skipped.note
    assert "未检测到测试文件" in skipped.note, skipped.note


def test_a_vocabulary_row_added_is_refused_instead_of_counted_and_passed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The silent half of the measured pair, on the direct call path."""
    _replace_vocabulary(monkeypatch, {**_TEST_GLOBS_BY_KIND, "rust": ("*_test.rs",)})
    ws = _write(tmp_path, {**PY_FILE, "src/lib_test.rs": "fn t() {}\n"})
    assert len(detect_test_suite(ws)) == 2, detect_test_suite(ws)
    with pytest.raises(AssertionError) as raised:
        run_test_gate(ws, executor=Recorder())
    message = str(raised.value)
    assert "'rust'" in message, message
    assert "run by nothing" in message, message


def test_the_unrouted_kind_is_never_certified_through_the_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What the report an operator reads says when a kind is counted by nobody."""
    _replace_vocabulary(monkeypatch, {**_TEST_GLOBS_BY_KIND, "rust": ("*_test.rs",)})
    ws = _write(tmp_path, {**PY_FILE, "src/lib_test.rs": "fn t() {}\n"})
    report = GatePipeline(workspace=ws, executor=Recorder()).run(
        ChangeBundle(task_id="unrouted", changed_files=["test_calc.py"])
    )
    entry = next(item for item in report.entries if item.gate == "run_test")
    assert entry.status == "error", (entry.status, entry.note)
    assert "AssertionError" in entry.note, entry.note
    assert "不伪造结果" in entry.note, entry.note
    assert report.overall == "error", report.summary_line


def test_the_typecheck_gate_survives_a_dropped_build_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        gates, "_BUILD_ROUTES", tuple(r for r in _BUILD_ROUTES if r.kind != "gradle")
    )
    ws = _write(tmp_path, {"pom.xml": "<project/>\n"})
    result = run_typecheck_gate(["README.md"], ws, executor=Recorder())
    assert isinstance(result, GateResult), type(result)
    assert result.status == "skipped", result.note
    assert "Java 项目无独立 typecheck 命令" in result.note, result.note


def test_the_build_gate_refuses_a_route_no_branch_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The twin keeps its failure mode, so the two gates cannot drift apart."""
    monkeypatch.setattr(
        gates,
        "_BUILD_ROUTES",
        (*_BUILD_ROUTES, gates._BuildRoute("rust", ("Cargo.toml",), "rust")),
    )
    ws = _write(tmp_path, {"Cargo.toml": "[package]\n"})
    with pytest.raises(AssertionError) as raised:
        run_build_gate(ws, executor=Recorder())
    assert "rust" in str(raised.value), raised.value


# ── the shipped plane: nothing is unrouted today ───────────────────

REPOS_BY_KIND: dict[str, dict[str, str]] = {
    "python": {**PY_FILE},
    "java": {"pom.xml": "<project/>\n", **JAVA_FILE},
    "go": {"go.mod": "module example.com/demo\n", **GO_FILE},
    "node": {
        "package.json": json.dumps({"name": "d", "scripts": {"test": "node --test"}}),
        **NODE_FILE,
    },
}


def test_every_kind_the_table_names_returns_a_gate_result_today(tmp_path: Path) -> None:
    assert set(REPOS_BY_KIND) == set(_TEST_GLOBS_BY_KIND), (
        "this roster is the shipped-shape witness for each dispatch kind; a new row in "
        "the vocabulary has to arrive with a fixture here"
    )
    for kind, files in sorted(REPOS_BY_KIND.items()):
        recorder = Recorder()
        result = run_test_gate(_write(tmp_path / kind, files), executor=recorder)
        assert result.status == "passed", (kind, result.note)
        assert recorder.calls, (kind, result.note)
        assert "未检测到" not in result.note, (kind, result.note)
        assert "该部分不执行" not in result.note, (kind, result.note)


def test_a_mixed_repository_reports_one_count_and_one_command_per_kind(tmp_path: Path) -> None:
    files: dict[str, str] = {}
    for repo in REPOS_BY_KIND.values():
        files.update(repo)
    ws = _write(tmp_path, files)
    recorder = Recorder()
    result = run_test_gate(ws, executor=recorder)
    counted = int(re.search(r"检测到 (\d+) 个测试文件", result.note).group(1))
    assert counted == len(detect_test_suite(ws)), (counted, result.note)
    assert len(recorder.calls) == len(_TEST_GLOBS_BY_KIND), recorder.calls
    assert result.status == "passed", result.note


def test_no_shipped_repository_shape_raises_out_of_a_gate(tmp_path: Path) -> None:
    """The ``-> GateResult`` contract, over every fixture shape the tree ships."""
    shapes = {
        **REPOS_BY_KIND,
        "bare": {"README.md": "nothing here\n"},
        "java-no-build-file": JAVA_FILE,
        "node-no-test-script": NODE_NO_SCRIPT,
        "node-broken-manifest": {"package.json": "{not json", **NODE_FILE},
    }
    for name, files in sorted(shapes.items()):
        ws = _write(tmp_path / name, files)
        for gate, args in (
            (run_test_gate, (ws,)),
            (run_build_gate, (ws,)),
            (run_typecheck_gate, (["README.md"], ws)),
        ):
            result = gate(*args, executor=Recorder())
            assert isinstance(result, GateResult), (name, gate.__name__, type(result))
            assert result.status in ("passed", "failed", "skipped", "error"), result.status


def test_only_a_kind_with_a_branch_or_a_disclosure_reaches_the_count(tmp_path: Path) -> None:
    """Every non-empty bucket on the shipped plane is answered by a dispatch branch."""
    ws = _write(tmp_path, {**PY_FILE, **JAVA_FILE, **GO_FILE, **NODE_FILE})
    counted = {kind for kind, bucket in gates._detect_suite_by_kind(ws).items() if bucket}
    assert counted <= _dispatched_kinds(), (
        f"{sorted(counted - _dispatched_kinds())} is counted into "
        "「检测到 N 个测试文件」 but no branch of run_test_gate answers it"
    )
    assert counted == set(_TEST_GLOBS_BY_KIND), (counted, _TEST_GLOBS_BY_KIND)
