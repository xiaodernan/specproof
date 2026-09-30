"""#137: the DEEP tier's cache-integrity disclosure must reach its report.

Backlog #7's guard produced a `SandboxResult.cache_note` that no shipped
reader consumed. #136 made the note itself honest (a cache-mounting profile
run without cache_dir+cache_manifest says NOT VERIFIED instead of ""); this
file pins the next link — agent/nodes/run_deep_experiments.py must carry that
note into deep_results / deep-report.json, which is the artifact a reviewer
actually opens.

Mutation arms and their predicted reds (written before running):
  A1 drop the `if cache_integrity:` guard      -> test_no_disclosure_writes_no_key
  A2 drop the dedupe (`and note not in seen`)  -> test_agreeing_runs_collapse_to_one_statement
  A3 pass [head_run] only                      -> test_only_a_repeat_run_disclosing_still_lands
  A4 drop cache_note from _run_test_via_sandbox-> test_the_real_run_function_carries_the_note
  A5 rename the results key                    -> every node-level case here
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

NOT_VERIFIED = "缓存完整性: 未校验 (NOT VERIFIED) — profile maven 挂了缓存卷 MAVEN_USER_HOME"
VERIFIED = "缓存完整性通过: 校验 3 个条目"
POISONED = "缓存投毒检测到 1 个条目, 拒绝执行 (fail-closed)"


def _state(tmp_path: Path) -> dict[str, Any]:
    return {
        "depth": "DEEP",
        "head_workspace": str(tmp_path),
        "app_dir": "",
        "generated_tests_path": str(tmp_path / "T.java"),
        "output_dir": str(tmp_path / "reports"),
        "job_id": "",
    }


def _drive(tmp_path: Path, monkeypatch, notes: list[str]) -> dict[str, Any]:
    """Run the real DEEP node over a fake sandbox view: one note per run.

    The node calls _run_test_via_sandbox once for the head run and then once
    per stability repeat, so `notes` is consumed in that order.
    """
    import agent.nodes.run_deep_experiments as deep

    remaining = list(notes)

    def fake_run(_app: str, _tests: str) -> dict[str, Any]:
        note = remaining.pop(0) if remaining else notes[-1]
        return {"exit_code": 0, "error": "", "mode": "docker", "cache_note": note}

    monkeypatch.setattr(deep, "_run_test_via_sandbox", fake_run)
    monkeypatch.setattr(deep, "_make_test_runner", lambda *a, **k: (lambda _c: (0, "")))
    monkeypatch.setattr(
        "experiments.state_snapshot.capture_full_stack",
        lambda *a, **k: {"tables": {}, "queues": {}},
    )
    monkeypatch.setattr(
        "experiments.state_snapshot.diff_states", lambda b, a: {"changed": []}
    )
    monkeypatch.setenv("SPECPROOF_DEEP_REPEATS", "2")
    return deep.run_deep_experiments_node(_state(tmp_path))


class TestRunFunctionCarriesTheNote:
    def test_the_real_run_function_carries_the_note(self, tmp_path, monkeypatch) -> None:
        """_run_test_via_sandbox must forward cache_note, not just exit/mode."""
        import agent.nodes.run_deep_experiments as deep
        import sandbox.runner as runner

        class FakeResult:
            exit_code = 0
            error = ""
            mode = "docker"
            cache_note = NOT_VERIFIED

        monkeypatch.setattr(runner, "run_sandboxed", lambda *a, **k: FakeResult())
        out = deep._run_test_via_sandbox(str(tmp_path), str(tmp_path / "T.java"))
        assert out["cache_note"] == NOT_VERIFIED
        assert set(out) == {"exit_code", "error", "mode", "cache_note"}


class TestDisclosureMerge:
    def test_agreeing_runs_collapse_to_one_statement(self, tmp_path, monkeypatch) -> None:
        out = _drive(tmp_path, monkeypatch, [NOT_VERIFIED] * 3)
        statement = out["deep_results"]["cache_integrity"]
        assert statement == NOT_VERIFIED
        assert statement.count("NOT VERIFIED") == 1

    def test_disagreeing_runs_name_both_sides(self, tmp_path, monkeypatch) -> None:
        out = _drive(tmp_path, monkeypatch, [VERIFIED, POISONED])
        statement = out["deep_results"]["cache_integrity"]
        assert VERIFIED in statement and POISONED in statement
        assert statement.index(VERIFIED) < statement.index(POISONED)

    def test_only_a_repeat_run_disclosing_still_lands(self, tmp_path, monkeypatch) -> None:
        out = _drive(tmp_path, monkeypatch, ["", NOT_VERIFIED])
        assert out["deep_results"]["cache_integrity"] == NOT_VERIFIED

    def test_no_disclosure_writes_no_key(self, tmp_path, monkeypatch) -> None:
        """An absent disclosure must stay absent — "" reads as "checked, fine"."""
        out = _drive(tmp_path, monkeypatch, ["", "   "])
        assert "cache_integrity" not in out["deep_results"]

    def test_helper_dedupes_in_visit_order(self) -> None:
        from agent.nodes.run_deep_experiments import _cache_integrity_disclosure

        runs = [{"cache_note": " b "}, {}, {"cache_note": "a"}, {"cache_note": "b"}]
        assert _cache_integrity_disclosure(runs) == "b; a"
        assert _cache_integrity_disclosure([]) == ""


class TestArtifactIsTheReader:
    def test_deep_report_json_contains_the_disclosure(self, tmp_path, monkeypatch) -> None:
        report = tmp_path / "reports" / "deep-report.json"
        _drive(tmp_path, monkeypatch, [NOT_VERIFIED])
        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload["cache_integrity"] == NOT_VERIFIED
