"""Unit tests — specproof baseline (diff-only reviewer comparison)."""

import subprocess
from pathlib import Path

from cli.specproof.commands.baseline import (
    capture_diff,
    deterministic_baseline,
    judge_case,
    render_report,
    summarize,
)


def test_deterministic_reader_detects_removed_preauthorize():
    diff = (
        "diff --git a/UserController.java b/UserController.java\n"
        "-    @PreAuthorize(\"isAuthenticated()\")\n"
        "     public void changeEmail() {}\n"
    )
    findings = deterministic_baseline(diff)
    assert len(findings) == 1
    assert findings[0]["contract_id"] == "AUTH-01"
    assert findings[0]["severity"] == "BLOCKER"


def test_reader_skips_modified_guard():
    # Condition inverted (removed + near-identical added) is a MODIFICATION:
    # a conservative static reader cannot call it a regression.
    diff = (
        "diff --git a/UserService.java b/UserService.java\n"
        "-        if (userRepository.existsByEmail(newEmail)) {\n"
        "+        if (!userRepository.existsByEmail(newEmail)) {\n"
    )
    assert deterministic_baseline(diff) == []


def test_reader_flags_deleted_uniqueness_guard():
    diff = (
        "diff --git a/UserService.java b/UserService.java\n"
        "-        if (userRepository.existsByEmail(newEmail)) {\n"
        "-            throw new RuntimeException(\"duplicate\");\n"
        "-        }\n"
    )
    findings = deterministic_baseline(diff)
    ids = {f["contract_id"] for f in findings}
    assert "UNIQUE-01" in ids


def test_reader_flags_added_publish_call():
    diff = (
        "diff --git a/UserService.java b/UserService.java\n"
        "+        rabbitTemplate.convertAndSend(\"x\", \"email.changed\", event);\n"
    )
    findings = deterministic_baseline(diff)
    assert any(f["contract_id"] == "EVENT_ONCE-01" for f in findings)


def test_reader_ignores_added_comments():
    diff = (
        "diff --git a/UserController.java b/UserController.java\n"
        "+/** documentation only */\n"
        "+        // another comment\n"
    )
    assert deterministic_baseline(diff) == []


def test_judge_positive_pass():
    gt = {
        "should_detect": True,
        "expected_contract": "AUTH-01",
        "expected_evidence_type": "differential_test",
    }
    row = judge_case(
        "case-x",
        gt,
        [{
            "contract_id": "AUTH-01",
            "severity": "BLOCKER",
            "evidence_type": "java_source_diff",
        }],
    )
    assert row["verdict"] == "PASS"
    assert row["detected"] is True


def test_judge_miss():
    gt = {
        "should_detect": True,
        "expected_contract": "AUTH-01",
        "expected_evidence_type": "differential_test",
    }
    row = judge_case("case-x", gt, [])
    assert row["verdict"] == "MISS"
    assert row["detected"] is False


def test_judge_negative_any_finding_is_false_positive():
    gt = {"should_detect": False, "expected_contract": None}
    row = judge_case(
        "case-x",
        gt,
        [{"contract_id": "EVENT_ONCE-01", "severity": "MAJOR"}],
    )
    assert row["verdict"] == "FALSE_POSITIVE"
    assert row["false_positive"] is True


def test_judge_partial_when_below_min_findings():
    gt = {
        "should_detect": True,
        "expected_contract": "AUTH-01",
        "expected_min_findings": 2,
    }
    row = judge_case(
        "case-x",
        gt,
        [{"contract_id": "AUTH-01", "severity": "BLOCKER"}],
    )
    assert row["verdict"] == "PARTIAL"
    assert row["detected"] is True


def test_summarize_aggregates():
    rows = [
        {"should_detect": True, "detected": True, "false_positive": False},
        {"should_detect": True, "detected": False, "false_positive": False},
        {"should_detect": False, "detected": False, "false_positive": False},
        {"should_detect": False, "detected": False, "false_positive": True},
    ]
    summary = summarize(rows)
    assert summary["detected"] == 1
    assert summary["recall"] == 50.0
    assert summary["precision"] == 50.0
    assert summary["false_positives"] == 1


def test_render_report_gate_math():
    rows: list[dict] = []
    baseline_summary = {"total_cases": 8, "recall": 62.5, "precision": 80.0}
    specproof = {
        "recall": 100.0,
        "precision": 100.0,
    }
    report = render_report(rows, baseline_summary, specproof, "deterministic")
    assert "+37.5pp" in report
    assert "**PASS**" in report
    failing = render_report(
        rows, {"total_cases": 8, "recall": 95.0, "precision": 90.0},
        specproof, "deterministic",
    )
    assert "**FAIL**" in failing


def test_render_report_without_specproof_results():
    rows: list[dict] = []
    report = render_report(
        rows, {"total_cases": 0, "recall": 0.0, "precision": 0.0},
        None, "deterministic",
    )
    assert "SpecProof 结果文件缺失" in report


def test_capture_diff_roundtrip(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-q"], cwd=repo, check=True, timeout=60,
    )
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"],
        cwd=repo, check=True, timeout=60,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"], cwd=repo, check=True, timeout=60,
    )
    (repo / "A.java").write_text("int a = 1;\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, timeout=60)
    subprocess.run(
        ["git", "commit", "-qm", "base"], cwd=repo, check=True, timeout=60,
    )
    subprocess.run(
        ["git", "checkout", "-qb", "head"], cwd=repo, check=True, timeout=60,
    )
    (repo / "A.java").write_text("int a = 2;\n", encoding="utf-8")
    subprocess.run(
        ["git", "commit", "-qam", "head"], cwd=repo, check=True, timeout=60,
    )
    diff = capture_diff(str(repo), "master", "head")
    assert "int a = 2" in diff
    assert "int a = 1" in diff
