"""The archived HTML report must record the environment the verdict came from.

A report that says FAILED without saying whether the *machine* or the *code*
failed is unreadable months later. These tests lock the honesty rules:
only probed facts are rendered, and a skipped preflight is stated as skipped
rather than silently omitted (which would read as "environment was fine").
"""
from __future__ import annotations

from typing import Any

from evidence.report import render_verification_report

STAMP = "2026-01-01 00:00:00 UTC"


def _render(preflight: Any, errors: list[str] | None = None) -> str:
    return render_verification_report(
        repo="/repo",
        base_ref="base",
        head_ref="head",
        matrix={"rows": []},
        findings=[],
        errors=errors or [],
        generated_at=STAMP,
        preflight=preflight,
    )


def test_renders_probed_checks_with_status() -> None:
    html = _render(
        {
            "passed": False,
            "language": "java",
            "checks": [
                {"check": "disk_space", "status": "PASS", "detail": "38.8 GB"},
                {"check": "java", "status": "FAIL", "detail": "Not found"},
            ],
            "errors": ["Preflight: Java not found."],
            "warnings": [],
            "skipped": ["node"],
        }
    )
    assert "Environment Preflight" in html
    assert "Detected project type: <strong>java</strong>" in html
    assert "not satisfied" in html
    assert "disk_space" in html
    assert "Not found" in html


def test_lists_blocking_reasons_and_skipped_checks() -> None:
    html = _render(
        {
            "passed": False,
            "language": "node",
            "checks": [{"check": "node", "status": "FAIL", "detail": "Not found"}],
            "errors": ["Preflight: Node.js not found."],
            "warnings": ["Node.js 18+ recommended."],
            "skipped": ["java", "maven_wrapper"],
        }
    )
    assert "Blocking (1)" in html
    assert "Node.js not found." in html
    assert "Warnings (1)" in html
    # "not run on purpose" must be visible, never omitted.
    assert "deliberately not run" in html
    assert "java" in html and "maven_wrapper" in html


def test_healthy_environment_is_reported_as_satisfied() -> None:
    html = _render(
        {
            "passed": True,
            "language": "python",
            "checks": [{"check": "python", "status": "PASS", "detail": "Python 3.12.14"}],
            "errors": [],
            "warnings": [],
            "skipped": [],
        }
    )
    assert "satisfied" in html
    assert "not satisfied" not in html


def test_empty_preflight_renders_nothing() -> None:
    """No preflight data ⇒ no section, rather than an empty scaffold."""
    assert "Environment Preflight" not in _render({})
    assert "Environment Preflight" not in _render(None)


def test_skipped_preflight_says_why() -> None:
    html = _render({"not_run": "upstream_errors"})
    assert "Environment Preflight" in html
    assert "before the environment was probed" in html


def test_probe_error_is_stated_not_hidden() -> None:
    html = _render({"not_run": "probe_error"})
    assert "probe itself failed" in html


def test_disabled_preflight_is_stated() -> None:
    html = _render({"not_run": "disabled_by_SPECPROOF_PREFLIGHT"})
    assert "disabled by configuration" in html


def test_preflight_values_are_escaped() -> None:
    html = _render(
        {
            "language": "<script>alert(1)</script>",
            "checks": [{"check": "x", "status": "PASS", "detail": "<b>bold</b>"}],
            "errors": [],
            "warnings": [],
            "skipped": [],
        }
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "<b>bold</b>" not in html


def test_render_stays_deterministic_with_preflight() -> None:
    payload = {
        "passed": True,
        "language": "go",
        "checks": [{"check": "go", "status": "PASS", "detail": "go1.22"}],
        "errors": [],
        "warnings": [],
        "skipped": [],
    }
    assert _render(payload) == _render(payload)


def test_existing_callers_without_preflight_still_work() -> None:
    """Backwards compatibility: the parameter is optional."""
    html = render_verification_report(
        repo="/r", base_ref="b", head_ref="h",
        matrix={"rows": []}, findings=[], generated_at=STAMP,
    )
    assert "SpecProof Verification Report" in html
    assert "Environment Preflight" not in html
