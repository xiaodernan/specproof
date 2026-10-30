"""#531: DEEP's test runs have one command-shape owner — the ExecutionAdapter.

Measured before writing: ``agent/nodes/run_deep_experiments.py`` spelled its
own Maven argv, ``mvn -o test -q -Dtest=... -f /work/pom.xml`` plus a Windows
``mvnw.cmd`` local fallback. #530 had just taught the differential that ``-q``
hides a passing surefire run's "Tests run:" summary — a passing run and a
selector that matched nothing look identical in the output — but DEEP kept
its own copy of the flag while recording only exit codes, so after #530 DEEP
was the one remaining run path that could go mute about what it executed.

Ends pinned here:
  1. The node spells no Maven command and calls no sandbox runner itself;
     the argv it executes IS ``JavaMavenAdapter.prepare``'s argv (batch mode,
     no ``-q``).
  2. The executed counts come back from the run and reach the artifact:
     ``state_delta.head_test_counts``, every stability run record, and the
     written deep-report.json.
  3. The cache disclosure still crosses the new adapter boundary (the note
     used to be read straight off the SandboxResult this module called).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import agent.nodes.run_deep_experiments as deep

DEEP_SOURCE = Path(deep.__file__).read_text(encoding="utf-8")
NOT_VERIFIED = "缓存完整性: 未校验 (NOT VERIFIED) — profile maven 挂了缓存卷 MAVEN_USER_HOME"
ONE_TEST_GREEN = "Tests run: 2, Failures: 0, Errors: 0, Skipped: 0\nBUILD SUCCESS\n"


def _make_repo(root: Path) -> Path:
    """A workspace the Java/Maven adapter detects (pom.xml + src/main/java)."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "pom.xml").write_text("<project/>", encoding="utf-8")
    (root / "src" / "main" / "java").mkdir(parents=True)
    return root


def _fake_sandbox_result(stdout: str, cache_note: str = "") -> Any:
    from sandbox.runner import SandboxResult

    return SandboxResult(
        exit_code=0, stdout=stdout, stderr="", mode="docker",
        cache_note=cache_note,
    )


class TestOneCommandShapeOwner:
    def test_the_node_spells_no_maven_command_of_its_own(self) -> None:
        """A second hand-written argv is how DEEP kept ``-q`` after #530."""
        strings = {
            node.value
            for node in ast.walk(ast.parse(DEEP_SOURCE))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert "mvn" not in strings
        assert "mvnw" not in strings and "mvnw.cmd" not in strings
        assert "-q" not in strings
        assert "run_sandboxed" not in DEEP_SOURCE, (
            "the node must reach the sandbox through the adapter, not directly"
        )

    def test_the_run_executes_the_adapters_prepared_command(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        import experiments.adapters as adapters
        from experiments.adapters import ExecutionRequest, JavaMavenAdapter

        app = _make_repo(tmp_path / "repo")
        commands: list[list[str]] = []

        def fake_run(command: list[str], **kwargs: Any) -> Any:
            commands.append(list(command))
            return _fake_sandbox_result(ONE_TEST_GREEN)

        monkeypatch.setattr(adapters, "run_sandboxed", fake_run)
        out = deep._run_test_via_sandbox(str(app), str(tmp_path / "T.java"))

        expected = JavaMavenAdapter().prepare(
            ExecutionRequest(
                workspace=str(app), goal="run_test", test_class="T", timeout=900,
            )
        ).command
        assert commands == [expected]
        assert "-B" in expected, "batch mode is what makes a passing run print its summary"
        assert "-q" not in expected
        assert out["test_counts"] == {
            "tests": 2, "failures": 0, "errors": 0, "skipped": 0,
        }


class TestTheArtifactCarriesWhatRan:
    def _drive(
        self, tmp_path: Path, monkeypatch, stdout: str, cache_note: str,
    ) -> dict[str, Any]:
        import experiments.adapters as adapters

        app = _make_repo(tmp_path / "repo")
        monkeypatch.setattr(
            adapters, "run_sandboxed",
            lambda *a, **k: _fake_sandbox_result(stdout, cache_note),
        )
        monkeypatch.setattr(deep, "_make_test_runner", lambda *a, **k: (lambda _c: (0, "", 0)))
        monkeypatch.setattr(
            "experiments.state_snapshot.capture_full_stack",
            lambda *a, **k: {"tables": {}, "queues": {}},
        )
        monkeypatch.setattr(
            "experiments.state_snapshot.diff_states", lambda b, a: {"changed": []}
        )
        monkeypatch.setenv("SPECPROOF_DEEP_REPEATS", "2")
        return deep.run_deep_experiments_node({
            "depth": "DEEP",
            "head_workspace": str(app),
            "app_dir": "",
            "generated_tests_path": str(app / "T.java"),
            "output_dir": str(tmp_path / "reports"),
            "job_id": "",
        })

    def test_head_count_and_every_repeat_count_land_in_the_report(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        out = self._drive(tmp_path, monkeypatch, ONE_TEST_GREEN, NOT_VERIFIED)
        results = out["deep_results"]
        assert results["state_delta"]["head_test_counts"] == {
            "tests": 2, "failures": 0, "errors": 0, "skipped": 0,
        }
        runs = results["verdict_stability"]["runs"]
        assert [r["test_counts"]["tests"] for r in runs] == [2, 2]

        payload = json.loads(
            (tmp_path / "reports" / "deep-report.json").read_text(encoding="utf-8")
        )
        assert payload["state_delta"]["head_test_counts"]["tests"] == 2
        assert [r["test_counts"]["tests"] for r in payload["verdict_stability"]["runs"]] == [2, 2]
        # The disclosure still crosses the adapter boundary (#137 -> #531).
        assert payload["cache_integrity"] == NOT_VERIFIED

    def test_a_run_without_a_surefire_summary_reports_zero_executed(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        """The blind run is now countable: no summary reads as 0, not as green.

        Maven prints no "Tests run:" line for a run whose selector matched
        nothing, so this is the shape the adapter's counts must expose. Since
        #532 the counts are consumed, not just recorded: a stability sequence
        made of these runs classifies ``not_verified`` — the exit_0 of a run
        that executed nothing is not a verdict.
        """
        out = self._drive(tmp_path, monkeypatch, stdout="", cache_note="")
        results = out["deep_results"]
        counts = results["state_delta"]["head_test_counts"]
        assert counts == {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
        stability = results["verdict_stability"]
        assert stability["classification"] == "not_verified"
        assert stability["verdicts"] == ["not_run", "not_run"]
        assert stability["runs_without_execution"] == 2
        assert "cache_integrity" not in results
