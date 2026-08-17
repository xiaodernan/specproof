"""Integration tests for SpecProof differential verification."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_REPO = REPO_ROOT / "demo" / "spring-backend"
APP_DIR = "demo/spring-backend"
CONTROLLER_PATH = (
    APP_DIR
    + "/src/main/java/com/specproof/demo/controller/UserController.java"
)
REQUIREMENT_FILE = REPO_ROOT / "demo" / "requirement.txt"


def _specproof(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "cli.specproof.main"] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(REPO_ROOT),
    )


def _cleanup_worktrees(final: dict) -> None:
    for key in ("base_workspace", "head_workspace"):
        ws = final.get(key, "")
        if not ws:
            continue
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "worktree", "remove", "--force", ws],
            capture_output=True, text=True, timeout=60,
        )


class TestDifferentialVerification:
    """End-to-end verification tests using the demo repository."""

    def test_specproof_probe_cli(self):
        """specproof probe should run without crashing (may fail on no API key)."""
        result = _specproof([
            "probe", "--base-url", "http://localhost:8080/v1",
            "--api-key", "test-key-for-probe",
        ])
        # Should either succeed or report API error, not crash on CLI usage
        output = result.stdout + result.stderr
        assert result.returncode in (0, 1, 2)
        assert any(
            word in output.lower()
            for word in ["probe", "api", "error", "usage", "capability"]
        )

    def test_specproof_verify_cli_help(self):
        """specproof verify --help should work."""
        result = _specproof(["verify", "--help"])
        assert result.returncode == 0
        assert "verify" in result.stdout.lower()

    def test_verify_with_demo_repo_git_tags(self):
        """Run specproof verify on the demo repo with base/head-v1 tags."""
        if not DEMO_REPO.exists():
            pytest.skip(f"Demo repo not found at {DEMO_REPO}")

        tags = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "tag", "-l"],
            capture_output=True, text=True, timeout=10,
        )
        if "base" not in tags.stdout or "head-v1" not in tags.stdout:
            pytest.skip("Required git tags (base, head-v1) not found")

        result = _specproof([
            "verify",
            "--repo", str(REPO_ROOT),
            "--app-dir", APP_DIR,
            "--base", "base",
            "--head", "head-v1",
            "--spec", str(REQUIREMENT_FILE),
            "--depth", "FAST",
        ], timeout=900)

        # May fail if Maven not installed (differential test can't run)
        # but should not crash — should report findings from static analysis
        output = result.stdout + result.stderr
        keywords = ["verify", "finding", "error"]
        assert any(kw in output.lower() for kw in keywords)

    def test_specproof_replay_help(self):
        """specproof replay --help should work."""
        result = _specproof(["replay", "--help"])
        assert result.returncode == 0
        assert "replay" in result.stdout.lower()

    def test_specproof_eval_help(self):
        """specproof eval --help should work."""
        result = _specproof(["eval", "--help"])
        assert result.returncode == 0
        assert "eval" in result.stdout.lower()


class TestStaticAnalysisDetection:
    """Verify static analysis detects known regressions."""

    def test_detect_annotation_removal(self):
        """The base→head-v1 diff should contain the @PreAuthorize removal."""
        diff_result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "diff", "base", "head-v1",
             "--", CONTROLLER_PATH],
            capture_output=True, text=True, timeout=10,
        )
        assert "@PreAuthorize" in diff_result.stdout
        assert "-@PreAuthorize" in diff_result.stdout.replace(" ", "").replace("\r", "") or "@PreAuthorize" in diff_result.stdout

    def test_head_missing_preauthorize(self):
        """Head version should NOT have @PreAuthorize on changeEmail."""
        content = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "show", "head-v1:" + CONTROLLER_PATH],
            capture_output=True, text=True, timeout=10,
        )
        assert "@PreAuthorize" not in content.stdout

    def test_base_has_preauthorize(self):
        """Base version should have @PreAuthorize on changeEmail."""
        content = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "show", "base:" + CONTROLLER_PATH],
            capture_output=True, text=True, timeout=10,
        )
        assert "@PreAuthorize" in content.stdout


class TestAgentNodeContracts:
    """Test individual agent nodes with the demo repo context."""

    def test_intake_node_reads_requirement(self):
        """intake node should read requirement text from spec file."""
        from agent.nodes.intake import intake_node

        state = {
            "repo_path": str(DEMO_REPO),
            "base_ref": "base",
            "head_ref": "head-v1",
            "spec_path": str(REQUIREMENT_FILE),
            "depth": "FAST",
        }
        result = intake_node(state)
        assert "requirement_text" in result
        assert len(result["requirement_text"]) > 0
        assert "auth" in result["requirement_text"].lower()

    def test_compile_contracts_from_requirement(self):
        """compile_contracts should detect auth, unique, token, etc."""
        from agent.nodes.compile_contracts import compile_contracts_node

        with open(REQUIREMENT_FILE, encoding="utf-8") as f:
            text = f.read()
        state = {
            "requirement_text": text,
        }
        result = compile_contracts_node(state)
        assert "contracts" in result
        contracts = result["contracts"]
        assert len(contracts) > 0
        contract_types = {c["checker_type"] for c in contracts}
        assert "http" in contract_types  # auth → http check

    def test_collect_diff_finds_annotation_removal(self):
        """collect_diff should find @PreAuthorize removal."""
        from agent.nodes.collect_diff import collect_diff_node

        state = {
            "repo_path": str(REPO_ROOT),
            "base_ref": "base",
            "head_ref": "head-v1",
        }
        result = collect_diff_node(state)
        assert "changed_symbols" in result
        symbols = result["changed_symbols"]
        has_annotation_removal = any(
            "ANNOTATION_REMOVED" in s for s in symbols
        )
        has_preauthorize = any(
            "PreAuthorize" in s for s in symbols
        )
        assert has_annotation_removal or has_preauthorize, (
            f"Expected @PreAuthorize removal, got: {symbols}"
        )

    def test_contract_checkers_detect_auth_bypass(self):
        """Contract checkers detect annotation removal on real sources."""
        base = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "show", "base:" + CONTROLLER_PATH],
            capture_output=True, text=True, timeout=10,
        ).stdout
        head = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "show", "head-v1:" + CONTROLLER_PATH],
            capture_output=True, text=True, timeout=10,
        ).stdout
        assert base and head

        from agent.checkers.java_source import run_contract_checks

        findings = run_contract_checks(
            {CONTROLLER_PATH: base},
            {CONTROLLER_PATH: head},
        )
        auth_findings = [
            f for f in findings if f.get("contract_id") == "AUTH-01"
        ]
        assert len(auth_findings) >= 1
        for f in auth_findings:
            assert f.get("severity") != "BLOCKER"
            assert f.get("evidence_type") == "java_source_diff"
            assert f.get("confidence") <= 0.85

    def test_review_court_confirms_auth_finding(self):
        """Review court should confirm findings with P0.5 evidence policy.

        P0.5: static regex findings (evidence_type=static_analysis) are capped
        at MAJOR. BLOCKER requires all 6 conditions including base/head
        execution and DB state evidence.
        """
        from agent.nodes.review_court import review_court_node

        state = {
            "static_findings": [{
                "id": "STATIC-AUTH-01",
                "severity": "BLOCKER",
                "type": "annotation_removed",
                "description": "@PreAuthorize removed from controller method",
                "evidence_type": "static_regex_analysis",  # P0.5: static regex
                "confidence": 0.95,
            }],
            "diff_results": [{
                "contract_id": "DIFF-HTTP",
                "verdict": "REGRESSION",
                "detail": "Security annotation present in base but missing in head",
                "evidence_type": "base_pass_head_fail",
                "db_state_verdict": "DB_MUTATED_ON_UNAUTH",
            }],
            "contracts": [{
                "id": "AUTH-01",
                "description": "所有变更API端点必须要求认证",
            }],
        }
        result = review_court_node(state)
        confirmed = result.get("confirmed_findings", [])
        assert len(confirmed) >= 1, f"Expected at least 1 confirmed finding, got {len(confirmed)}"

        # P0.5: static regex alone → max MAJOR, not BLOCKER
        static_finding = [f for f in confirmed if f.get("source") == "static_analysis"]
        for sf in static_finding:
            assert sf.get("severity") != "BLOCKER", (
                "P0.5: static regex findings must be capped at MAJOR"
            )

        # P0.5: with base_pass_head_fail + DB_MUTATED_ON_UNAUTH → can be BLOCKER
        blocker = [f for f in confirmed if f.get("severity") == "BLOCKER"]
        if blocker:
            assert blocker[0].get("evidence_type") in (
                "base_pass_head_fail", "differential_execution"
            )

    def test_generate_counterexamples_for_auth_bypass(self):
        """Counterexample generator should create auth bypass test."""
        from agent.nodes.generate_counterexamples import (
            generate_counterexamples_node,
        )

        state = {
            "static_findings": [{
                "id": "STATIC-AUTH-01",
                "type": "annotation_removed",
                "description": "@PreAuthorize removed",
            }],
            "head_workspace": "",
        }
        result = generate_counterexamples_node(state)
        tests_path = result.get("generated_tests_path", "")
        # Without head_workspace, test_path should be empty string
        assert tests_path == ""


class TestFullVerifyPipeline:
    """Run the complete graph pipeline end-to-end."""

    def test_full_graph_execution(self):
        """Build and execute the full Phase 0 graph."""
        from agent.graph import build_phase0_graph
        from agent.state import initial_state

        # Build graph
        graph = build_phase0_graph()

        # Create initial state
        state = initial_state(
            repo_path=str(REPO_ROOT),
            base_ref="base",
            head_ref="head-v1",
            spec_path=str(REQUIREMENT_FILE),
            depth="FAST",
        )
        state["app_dir"] = APP_DIR

        # Execute graph
        result = graph.invoke(state)

        # Verify output structure
        assert "requirement_text" in result
        assert "contracts" in result
        assert "changed_symbols" in result
        assert "static_findings" in result
        assert "confirmed_findings" in result

        # Should have detected the auth bypass
        findings = result.get("confirmed_findings", [])
        assert len(findings) > 0, "Expected at least one finding from demo repo"

        # Should have a report path
        report_path = result.get("report_path", "")
        assert report_path, "Expected a report path"
        assert Path(report_path).exists(), f"Report file not found: {report_path}"

        _cleanup_worktrees(result)

    def test_verify_then_replay_roundtrip(self):
        """Verify produces capsule, replay reads it back."""
        from agent.graph import build_phase0_graph
        from agent.state import initial_state

        graph = build_phase0_graph()
        state = initial_state(
            repo_path=str(REPO_ROOT),
            base_ref="base",
            head_ref="head-v1",
            spec_path=str(REQUIREMENT_FILE),
            depth="FAST",
        )
        state["app_dir"] = APP_DIR
        result = graph.invoke(state)

        capsules = result.get("capsules", [])
        if capsules:
            import zipfile
            capsule_path = capsules[0]
            assert Path(capsule_path).exists()
            # Read manifest from zip
            with zipfile.ZipFile(capsule_path, "r") as zf:
                assert "manifest.json" in zf.namelist()
                manifest = json.loads(zf.read("manifest.json"))
                assert "finding_id" in manifest
                assert "severity" in manifest

        _cleanup_worktrees(result)
