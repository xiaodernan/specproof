"""#139: the DEEP artifact must be job-scoped and self-attributing.

Measured before writing: every job's DEEP node wrote the SAME filename
("deep-report.json") into a SHARED reports directory (state["output_dir"]
defaults to "reports"), so a second concurrent DEEP run replaced the first
job's mutation / state-delta / cache evidence, and the surviving file said
nothing about which job it described. Naming now follows the convention the
certificate artifacts already use (first 8 characters of the job id), and the
artifact carries its own job id, filename and naming decision.

Arms and predicted reds (written before running any arm):
  K1 name back to the fixed "deep-report.json"  -> 1,2,5
  K2 drop the id-shape guard (raw id in a path) -> 4
  K3 drop results["job_id"]                      -> 1
  K4 drop results["deep_report_file"]            -> 5
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import agent.nodes.run_deep_experiments as deep

JOB_A = "1a2b3c4d-5e6f-4a5b-8c9d-0e1f2a3b4c5d"
JOB_B = "9f8e7d6c-5b4a-4321-9876-543210fedcba"
NOT_A = "缓存完整性: 未校验 (NOT VERIFIED) — run A"
NOT_B = "缓存完整性通过: 校验 7 个条目 (run B)"


def _drive(reports: Path, monkeypatch, job_id: str, note: str) -> dict[str, Any]:
    """Run the real DEEP node for one job into a shared reports directory."""

    def fake_run(_app: str, _tests: str) -> dict[str, Any]:
        return {
            "exit_code": 0, "error": "", "mode": "docker", "cache_note": note,
        }

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
    state = {
        "depth": "DEEP",
        "head_workspace": str(reports.parent),
        "app_dir": "",
        "generated_tests_path": str(reports.parent / "T.java"),
        "output_dir": str(reports),
        "job_id": job_id,
    }
    return deep.run_deep_experiments_node(state)


def _read(reports: Path, name: str) -> dict[str, Any]:
    return json.loads((reports / name).read_text(encoding="utf-8"))


class TestNoCollision:
    def test_two_concurrent_jobs_keep_their_own_artifacts(self, tmp_path, monkeypatch) -> None:
        """The regression: one shared filename meant the second job won."""
        reports = tmp_path / "reports"
        _drive(reports, monkeypatch, JOB_A, NOT_A)
        _drive(reports, monkeypatch, JOB_B, NOT_B)

        written = sorted(p.name for p in reports.glob("deep-report*.json"))
        assert written == [
            f"deep-report-{JOB_A[:8]}.json",
            f"deep-report-{JOB_B[:8]}.json",
        ]
        doc_a = _read(reports, f"deep-report-{JOB_A[:8]}.json")
        doc_b = _read(reports, f"deep-report-{JOB_B[:8]}.json")
        assert doc_a["job_id"] == JOB_A and doc_a["cache_integrity"] == NOT_A
        assert doc_b["job_id"] == JOB_B and doc_b["cache_integrity"] == NOT_B


class TestNaming:
    def test_artifact_name_is_derived_from_the_job_id(self, tmp_path, monkeypatch) -> None:
        reports = tmp_path / "reports"
        _drive(reports, monkeypatch, JOB_A, NOT_A)
        assert (reports / f"deep-report-{JOB_A[:8]}.json").is_file()
        assert not (reports / "deep-report.json").exists()

    def test_unscoped_run_keeps_the_plain_name(self, tmp_path, monkeypatch) -> None:
        reports = tmp_path / "reports"
        _drive(reports, monkeypatch, "", NOT_A)
        assert sorted(p.name for p in reports.glob("deep-report*.json")) == [
            "deep-report.json"
        ]

    def test_non_id_shaped_job_id_never_enters_a_filename(self, tmp_path, monkeypatch) -> None:
        """An arbitrary string must not become a path component."""
        reports = tmp_path / "reports"
        hostile = "../../escape"
        _drive(reports, monkeypatch, hostile, NOT_A)
        assert sorted(p.name for p in reports.glob("deep-report*")) == ["deep-report.json"]
        assert not (tmp_path / "escape.json").exists()
        assert (reports / "deep-report.json").is_file()

    def test_artifact_points_at_a_file_that_exists(self, tmp_path, monkeypatch) -> None:
        reports = tmp_path / "reports"
        _drive(reports, monkeypatch, JOB_B, NOT_B)
        doc = _read(reports, f"deep-report-{JOB_B[:8]}.json")
        assert doc["deep_report_file"] == f"deep-report-{JOB_B[:8]}.json"
        assert (reports / doc["deep_report_file"]).is_file()
        assert doc["deep_report_naming"] == "job-scoped"
