"""#538: the deep experiments are Java-shaped — a non-Java tree is NOT a run.

Measured before writing: ``run_deep_experiments_node`` ran unconditionally.
On a Node tree (package.json with a test script) ``_run_test_via_sandbox``
picks the NodeAdapter and executes the repository's OWN ``npm test`` under
the generated JUnit test's name, ``parse_surefire_summary`` reads that output
as zero executed tests, ``read_main_java_files`` finds no ``src/main/java``
so ``mutation`` is ``[]``, and the node reports ``completed`` with a sidecar
report that reads like a measured campaign. An unclaimed tree is the same
shape one step earlier: the sandbox returns exit -1 and the run is still
written as a completed deep report.

The fix is an applicability gate, not a multi-language campaign: DEEP's
experiments (source mutation into ``src/main/java``, injected JUnit reruns,
state delta around them) only measure a Java runtime, so any other detected
runtime is recorded as NOT MEASURED — with the reason on the node result,
in the sidecar report, and in the archived HTML report.

Witness arms on an external plane (predicted before running, measured
after; the first draft guessed P1/P2 would also red test_3 — it cannot,
because test_3's tree is Java and the gate is not what runs it):
  C1 rename the language constant (control)             -> none
  P1 gate body disabled                                 -> 1, 2 + the
     observable not_applicable delta (bombs fire)
  P2 gate accepts the Node language                     -> 1 + the same
     observable delta; 2 stays not applicable
  P3 unclaimed branch reports ran=True                  -> 2
  P4 renderer drops the applicability line              -> 4, 6
  P5 renderer keeps the cache-absence line for ran=False -> 4
  P6 reason rendered unescaped                          -> 6
  P7 emitted counter literal renamed                    -> 0 here; the
     observable vocabulary + delta pins red, while the
     dashboard-reference gate stays green because the name still
     accounts as a family via CONCATENATED_FAMILIES
  P8 sidecar skipped on the refusal path                -> 0 here; the
     observable sidecar pin reds
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import agent.nodes.run_deep_experiments as deep
from evidence.report import render_verification_report

MATRIX: dict[str, Any] = {"rows": []}


def _render(**overrides: Any) -> str:
    kwargs: dict[str, Any] = {
        "repo": "demo/repo",
        "base_ref": "base-sha",
        "head_ref": "head-sha",
        "matrix": MATRIX,
        "findings": [],
        "generated_at": "2026-10-01 00:00:00 UTC",
    }
    kwargs.update(overrides)
    return render_verification_report(**kwargs)


def _node_state(app: Path, tmp_path: Path) -> dict[str, Any]:
    return {
        "depth": "DEEP",
        "head_workspace": str(app),
        "app_dir": "",
        "generated_tests_path": str(tmp_path / "SpecProofGeneratedTest.java"),
        "output_dir": str(tmp_path / "reports"),
        "job_id": "",
    }


def _bomb_every_runtime_seam(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any call past the gate proves the gate did not return."""

    def bomb(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(
            "nothing may run on a tree the deep experiments cannot measure"
        )

    monkeypatch.setattr(deep, "_run_test_via_sandbox", bomb)
    monkeypatch.setattr("experiments.mutation.run_mutation_campaign", bomb)
    monkeypatch.setattr(
        "experiments.state_snapshot.capture_full_stack", bomb
    )
    monkeypatch.setattr("experiments.state_snapshot.diff_states", bomb)
    monkeypatch.setattr("storage.mysql.MySQLStore", bomb)
    monkeypatch.setattr("storage.redis.RedisStore", bomb)
    monkeypatch.setattr("storage.rabbitmq.RabbitMQClient", bomb)
    monkeypatch.setattr(
        "agent.nodes.run_differential._capture_db_snapshot", bomb
    )


class TestTheGate:
    def test_1_a_node_tree_is_not_applicable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        app = tmp_path / "repo"
        app.mkdir()
        (app / "package.json").write_text(
            '{"scripts": {"test": "node --test"}}', encoding="utf-8"
        )
        _bomb_every_runtime_seam(monkeypatch)

        out = deep.run_deep_experiments_node(  # type: ignore[arg-type]
            _node_state(app, tmp_path)
        )
        applicability = out["deep_results"]["applicability"]

        assert applicability["ran"] is False
        assert applicability["language"] == "javascript/typescript"
        assert applicability["build_tool"] == "npm"
        assert "nothing was measured" in applicability["reason"]
        assert "not evidence" in applicability["reason"]
        assert out["deep_note"].startswith("DEEP not applicable")

    def test_2_an_unclaimed_tree_is_not_applicable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        app = tmp_path / "repo"
        app.mkdir()
        _bomb_every_runtime_seam(monkeypatch)

        out = deep.run_deep_experiments_node(  # type: ignore[arg-type]
            _node_state(app, tmp_path)
        )
        applicability = out["deep_results"]["applicability"]

        assert applicability["ran"] is False
        assert applicability["language"] == ""
        assert "no execution adapter matched" in applicability["reason"]
        assert "not evidence" in applicability["reason"]

    @pytest.mark.parametrize(
        ("marker", "content", "build_tool"),
        [
            ("pom.xml", "<project/>", "maven"),
            ("build.gradle", "plugins {}", "gradle"),
        ],
    )
    def test_3_a_java_tree_runs_and_records_what_was_measured(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        marker: str,
        content: str,
        build_tool: str,
    ) -> None:
        """Gradle also reports language "java" and is covered by the gate."""
        app = tmp_path / "repo"
        (app / "src" / "main" / "java").mkdir(parents=True)
        (app / marker).write_text(content, encoding="utf-8")

        monkeypatch.setattr(
            deep,
            "_run_test_via_sandbox",
            lambda a, t: {
                "exit_code": 0,
                "error": "",
                "mode": "docker",
                "cache_note": "",
                "test_counts": {"tests": 1},
            },
        )
        monkeypatch.setattr(
            "experiments.state_snapshot.capture_full_stack", lambda *a, **k: {}
        )
        monkeypatch.setattr(
            "experiments.state_snapshot.diff_states", lambda b, a: {}
        )
        monkeypatch.setattr("storage.mysql.MySQLStore", lambda: object())
        monkeypatch.setattr("storage.redis.RedisStore", lambda: object())
        monkeypatch.setattr("storage.rabbitmq.RabbitMQClient", lambda: object())
        monkeypatch.setattr(
            "agent.nodes.run_differential._capture_db_snapshot",
            lambda workspace: {"rows": 0},
        )
        monkeypatch.setenv("SPECPROOF_DEEP_REPEATS", "1")

        out = deep.run_deep_experiments_node(  # type: ignore[arg-type]
            _node_state(app, tmp_path)
        )

        assert out["deep_results"]["applicability"] == {
            "ran": True,
            "language": "java",
            "build_tool": build_tool,
        }
        assert out["deep_note"].startswith("DEEP experiments completed")


class TestTheReaderSeesWhy:
    def test_4_the_report_names_the_reason_and_makes_no_cache_claim(self) -> None:
        reason = (
            "detected runtime is python (pip); the deep experiments only "
            "mutate and rerun a Java tree, so nothing was measured — this is "
            "not evidence that the generated test has no weaknesses"
        )
        html = _render(
            deep={
                "applicability": {
                    "ran": False,
                    "language": "python",
                    "build_tool": "pip",
                    "reason": reason,
                },
                "deep_report_file": "deep-report-deadbeef.json",
            },
            deep_note="DEEP not applicable: detected runtime python; nothing was measured",
        )
        assert "Deep experiments: not applicable" in html
        assert "nothing was measured" in html
        assert "not disclosed by this run" not in html, (
            "no deep test run existed, so there is no cache it could have failed to disclose"
        )
        assert "deep-report-deadbeef.json" in html

    def test_5_a_measured_run_without_a_cache_note_still_says_absent(self) -> None:
        """The suppression above is keyed on ran=False, not on the new key."""
        html = _render(
            deep={
                "applicability": {
                    "ran": True,
                    "language": "java",
                    "build_tool": "maven",
                },
                "mutation": [],
            },
            deep_note="deep tier ran",
        )
        assert "not disclosed by this run" in html
        assert "Deep experiments: not applicable" not in html

    def test_6_the_reason_is_escaped(self) -> None:
        payload = '<script>alert("deep")</script>'
        html = _render(
            deep={"applicability": {"ran": False, "reason": payload}},
            deep_note="DEEP not applicable",
        )
        assert "<script>alert" not in html
        assert "&lt;script&gt;alert" in html
