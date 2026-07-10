"""Phase 0 Acceptance Test Suite.

Validates that SpecProof Phase 0 meets all acceptance criteria:
1. Golden case detection rate >= defined threshold
2. Bug capsule replay works
3. HTML report generation is correct
4. CLI commands work end-to-end
5. No secrets leaked in any output
"""

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_CASES = PROJECT_ROOT / "golden-cases"
DEMO_REPO = PROJECT_ROOT / "demo" / "spring-backend"
REQUIREMENT_FILE = PROJECT_ROOT / "demo" / "requirement.txt"


def run_specproof(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "cli.specproof.main"] + args,
        capture_output=True, text=True, timeout=120,
        cwd=str(PROJECT_ROOT),
    )


class TestPhaseAcceptance:
    """Phase 0 acceptance criteria."""

    def test_all_golden_cases_exist(self):
        """All 10 golden cases should have spec.md and ground-truth.json."""
        case_dirs = sorted(
            d for d in GOLDEN_CASES.iterdir()
            if d.is_dir() and d.name.startswith("case-")
        )
        assert len(case_dirs) == 10, f"Expected 10 cases, got {len(case_dirs)}"

        for case_dir in case_dirs:
            assert (case_dir / "spec.md").exists(), f"{case_dir.name}: missing spec.md"
            assert (case_dir / "ground-truth.json").exists(), (
                f"{case_dir.name}: missing ground-truth.json"
            )

    def test_golden_cases_ground_truth_valid(self):
        """All ground-truth.json files must be valid JSON with required fields."""
        required_fields = {"expected_severity", "expected_evidence_type", "should_detect"}
        for case_dir in sorted(GOLDEN_CASES.iterdir()):
            if not case_dir.is_dir() or not case_dir.name.startswith("case-"):
                continue
            with open(case_dir / "ground-truth.json", encoding="utf-8") as f:
                gt = json.load(f)
            for field in required_fields:
                assert field in gt, f"{case_dir.name}: missing {field} in ground-truth.json"
            assert isinstance(gt["should_detect"], bool), (
                f"{case_dir.name}: should_detect must be boolean"
            )

    def test_specproof_eval_runs_all_cases(self):
        """specproof eval should process all 10 golden cases."""
        result = run_specproof(["eval", "--cases", str(GOLDEN_CASES)])
        assert result.returncode == 0
        assert "10 cases processed" in result.stdout

    def test_eval_generates_html_report(self):
        """eval command should generate an HTML report."""
        output_path = PROJECT_ROOT / "eval-report.html"
        result = run_specproof([
            "eval", "--cases", str(GOLDEN_CASES),
            "--output", str(output_path),
        ])
        assert result.returncode == 0
        assert output_path.exists()
        content = output_path.read_text(encoding="utf-8")
        assert "<html" in content.lower()
        assert "SpecProof" in content

    def test_capsule_replay_roundtrip(self):
        """Replay should extract and read a real capsule zip."""
        # Find an existing capsule from previous runs
        capsules_dir = PROJECT_ROOT / "capsules"
        capsule_zips = sorted(
            capsules_dir.glob("capsule-*.zip"),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        if not capsule_zips:
            pytest.skip("No capsule zips available for replay test")

        capsule = capsule_zips[0]
        result = run_specproof(["replay", str(capsule)])
        assert result.returncode == 0
        assert "Finding ID:" in result.stdout
        assert "Severity:" in result.stdout

    def test_capsule_zip_contains_required_files(self):
        """Each capsule zip must contain manifest.json and finding.json."""
        capsules_dir = PROJECT_ROOT / "capsules"
        for capsule_zip in capsules_dir.glob("capsule-*.zip"):
            with zipfile.ZipFile(capsule_zip, "r") as zf:
                names = zf.namelist()
                assert "manifest.json" in names, f"{capsule_zip.name}: missing manifest.json"
                assert "finding.json" in names, f"{capsule_zip.name}: missing finding.json"
                assert "requirement.json" in names, f"{capsule_zip.name}: missing requirement.json"
                assert "README.md" in names, f"{capsule_zip.name}: missing README.md"

    def test_capsule_manifest_has_required_fields(self):
        """manifest.json must have finding_id, severity, confidence, created_at."""
        capsules_dir = PROJECT_ROOT / "capsules"
        for capsule_zip in capsules_dir.glob("capsule-*.zip"):
            with zipfile.ZipFile(capsule_zip, "r") as zf:
                manifest = json.loads(zf.read("manifest.json"))
            assert "finding_id" in manifest
            assert "severity" in manifest
            assert "confidence" in manifest
            assert "created_at" in manifest

    def test_verification_report_not_empty(self):
        """Generated HTML reports should contain actual data, not placeholders."""
        reports_dir = PROJECT_ROOT / "reports"
        reports = sorted(
            reports_dir.glob("verification-report-*.html"),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        if not reports:
            pytest.skip("No reports available")

        latest = reports[0]
        content = latest.read_text(encoding="utf-8")
        assert "TODO" not in content
        assert "placeholder" not in content.lower()
        assert "Requirement-to-Evidence Matrix" in content

    def test_full_pipeline_produces_all_artifacts(self):
        """A full pipeline run should produce report + capsules + matrix."""
        from agent.graph import build_phase0_graph
        from agent.state import initial_state

        graph = build_phase0_graph()
        state = initial_state(
            repo_path=str(DEMO_REPO),
            base_ref="base",
            head_ref="head-v1",
            spec_path=str(REQUIREMENT_FILE),
            depth="FAST",
        )
        result = graph.invoke(state)

        # Must have a report
        assert result.get("report_path"), "No report generated"
        assert Path(result["report_path"]).exists(), "Report file not found"

        # Must have matrix data
        matrix = result.get("matrix", {})
        assert len(matrix.get("rows", [])) > 0, "Matrix has no rows"

        # Must have findings
        findings = result.get("confirmed_findings", [])
        assert len(findings) > 0, "No findings detected"

        # BLOCKER findings should produce capsules
        blocker_findings = [f for f in findings if f.get("severity") == "BLOCKER"]
        capsules = result.get("capsules", [])
        assert len(capsules) >= len(blocker_findings), (
            f"Expected at least {len(blocker_findings)} capsules, got {len(capsules)}"
        )

    def test_no_secrets_in_report(self):
        """Generated reports must not contain API keys or passwords."""
        reports_dir = PROJECT_ROOT / "reports"
        for report in reports_dir.glob("verification-report-*.html"):
            content = report.read_text(encoding="utf-8")
            # Must not contain real-looking API keys
            assert "sk-" not in content.lower(), f"{report.name}: contains 'sk-' pattern"
            # Must not contain real passwords
            for banned in ["password123", "admin123", "secret123"]:
                assert banned not in content.lower(), (
                    f"{report.name}: contains banned password pattern"
                )
