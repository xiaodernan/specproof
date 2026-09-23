"""Unit tests for the language-aware environment preflight (roadmap Phase 1.4).

The regression that matters most: a Node or Python repository must never be
blocked because a JDK is absent. That single behaviour is why this module sat
unwired for so long, so it is locked down explicitly.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from agent import preflight as pf
from agent.nodes.preflight import ENV_DISABLE, ERROR_PREFIX, preflight_node

# ── detect_language ─────────────────────────────────────────────────────


def test_detect_java(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    assert pf.detect_language(str(tmp_path)) == pf.LANGUAGE_JAVA


def test_detect_node(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    assert pf.detect_language(str(tmp_path)) == pf.LANGUAGE_NODE


def test_detect_python(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]", encoding="utf-8")
    assert pf.detect_language(str(tmp_path)) == pf.LANGUAGE_PYTHON


def test_detect_go(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module x", encoding="utf-8")
    assert pf.detect_language(str(tmp_path)) == pf.LANGUAGE_GO


def test_detect_unknown_on_empty_dir(tmp_path: Path) -> None:
    assert pf.detect_language(str(tmp_path)) == pf.LANGUAGE_UNKNOWN


def test_detect_unknown_when_path_missing() -> None:
    assert pf.detect_language(None) == pf.LANGUAGE_UNKNOWN


def test_detect_honours_app_dir(tmp_path: Path) -> None:
    """A monorepo with the JVM project in a subdirectory is still Java."""
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "pom.xml").write_text("<project/>", encoding="utf-8")
    assert pf.detect_language(str(tmp_path), "backend") == pf.LANGUAGE_JAVA


def test_java_wins_over_node_in_same_root(tmp_path: Path) -> None:
    """Java repos often ship a package.json (frontend); Java must win."""
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    assert pf.detect_language(str(tmp_path)) == pf.LANGUAGE_JAVA


# ── language gating (the core regression) ───────────────────────────────


def test_node_repo_is_never_blocked_by_missing_jdk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No JDK installed + a Node repo ⇒ preflight must still pass."""
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")

    def _no_java(cmd: list[str], timeout: int = 0) -> tuple[int, str]:
        if "java" in cmd[0] or "javac" in cmd[0] or cmd[:1] == ["mvn"]:
            return pf.EXIT_NOT_FOUND, ""
        return 0, "v22.0.0"

    monkeypatch.setattr(pf, "_probe", _no_java)
    monkeypatch.delenv("JAVA_HOME", raising=False)

    result = pf.run_preflight(str(tmp_path))
    assert result.passed is True
    assert result.errors == []
    assert "java" in result.skipped
    assert "maven_wrapper" in result.skipped


def test_python_repo_is_never_blocked_by_missing_jdk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]", encoding="utf-8")

    monkeypatch.setattr(pf, "_probe", lambda cmd, timeout=0: (pf.EXIT_NOT_FOUND, ""))
    monkeypatch.setattr(pf, "_check_python", lambda r: pf._add(r, "python", "PASS", "ok"))
    monkeypatch.setattr(pf, "_check_pytest", lambda r: pf._add(r, "pytest", "PASS", "ok"))

    result = pf.run_preflight(str(tmp_path))
    assert result.passed is True
    assert result.errors == []
    assert "java" in result.skipped


def test_unknown_language_runs_only_universal_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An undetectable repository must not be blocked by anything."""
    monkeypatch.setattr(pf, "_probe", lambda cmd, timeout=0: (pf.EXIT_NOT_FOUND, ""))
    result = pf.run_preflight(str(tmp_path), language=pf.LANGUAGE_UNKNOWN)
    assert result.passed is True
    assert result.errors == []
    assert [c["check"] for c in result.checks] == ["disk_space"]


def test_java_repo_blocks_on_missing_jdk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    monkeypatch.setattr(pf, "_probe", lambda cmd, timeout=0: (pf.EXIT_NOT_FOUND, ""))
    monkeypatch.delenv("JAVA_HOME", raising=False)

    result = pf.run_preflight(str(tmp_path))
    assert result.passed is False
    assert any("Java not found" in e for e in result.errors)


def test_java_home_missing_is_a_warning_not_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A working `java` on PATH is enough; JAVA_HOME is advisory."""
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    (tmp_path / "mvnw").write_text("#!/bin/sh", encoding="utf-8")
    (tmp_path / ".mvn").mkdir()
    (tmp_path / ".mvn" / "wrapper").mkdir()
    (tmp_path / ".mvn" / "wrapper" / "maven-wrapper.properties").write_text(
        "distributionUrl=https://repo.maven.apache.org/x\ndistributionSha256Sum=abc",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        pf, "_probe", lambda cmd, timeout=0: (0, 'openjdk version "21.0.4"')
    )
    monkeypatch.delenv("JAVA_HOME", raising=False)

    result = pf.run_preflight(str(tmp_path))
    assert result.passed is True
    assert any("JAVA_HOME is not set" in w for w in result.warnings)
    assert not any("JAVA_HOME" in e for e in result.errors)


def test_wrapperless_maven_repo_passes_when_mvn_on_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pom.xml without mvnw is valid when a system Maven is installed."""
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")

    def _probe(cmd: list[str], timeout: int = 0) -> tuple[int, str]:
        if "java" in cmd[0]:
            return 0, 'openjdk version "21.0.4"'
        return 0, "Apache Maven 3.9.6"

    monkeypatch.setattr(pf, "_probe", _probe)
    monkeypatch.delenv("JAVA_HOME", raising=False)

    result = pf.run_preflight(str(tmp_path))
    assert result.passed is True
    wrapper = next(c for c in result.checks if c["check"] == "maven_wrapper")
    assert wrapper["status"] == "PASS"
    assert "system mvn" in wrapper["detail"]


def test_wrapperless_maven_repo_fails_when_no_mvn_either(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    monkeypatch.setattr(pf, "_probe", lambda cmd, timeout=0: (pf.EXIT_NOT_FOUND, ""))
    monkeypatch.delenv("JAVA_HOME", raising=False)

    result = pf.run_preflight(str(tmp_path))
    assert result.passed is False
    assert any("Maven" in e for e in result.errors)


def test_old_jdk_is_blocking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    (tmp_path / "mvnw").write_text("#!/bin/sh", encoding="utf-8")
    monkeypatch.setattr(
        pf, "_probe", lambda cmd, timeout=0: (0, 'openjdk version "17.0.9"')
    )
    monkeypatch.delenv("JAVA_HOME", raising=False)

    result = pf.run_preflight(str(tmp_path))
    assert result.passed is False
    assert any("JDK 21 required" in e for e in result.errors)


# ── result shape ────────────────────────────────────────────────────────


def test_to_dict_is_json_ready() -> None:
    result = pf.PreflightResult(language=pf.LANGUAGE_NODE)
    payload = result.to_dict()
    assert set(payload) == {"passed", "language", "checks", "errors", "warnings", "skipped"}
    assert payload["language"] == pf.LANGUAGE_NODE


def test_report_includes_language_and_skipped() -> None:
    result = pf.PreflightResult(language=pf.LANGUAGE_NODE, skipped=["java"])
    text = pf.format_preflight_report(result)
    assert "language: node" in text
    assert "Not applicable (1): java" in text
    assert "Preflight: PASSED" in text


def test_report_marks_failure() -> None:
    result = pf.PreflightResult(errors=["Java not found."])
    result.passed = False
    assert "Preflight: FAILED — 1 error(s)" in pf.format_preflight_report(result)


def test_probe_variants_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """npm ships as npm.cmd; without variants it is invisible to subprocess."""
    monkeypatch.setattr(sys, "platform", "win32")
    assert pf._probe_variants(["npm", "--version"]) == [
        ["npm.cmd", "--version"],
        ["npm.exe", "--version"],
        ["npm.bat", "--version"],
        ["npm", "--version"],
    ]


def test_probe_returns_not_found_without_raising() -> None:
    code, _ = pf._probe(["specproof-definitely-not-a-binary-xyz", "--version"])
    assert code == pf.EXIT_NOT_FOUND


def test_probe_reports_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)

    monkeypatch.setattr(subprocess, "run", _boom)
    code, detail = pf._probe(["anything"])
    assert code == pf.EXIT_TIMEOUT
    assert "timed out" in detail


# ── pipeline node ───────────────────────────────────────────────────────


def test_node_skips_when_upstream_already_failed() -> None:
    state = {"repo_path": "", "errors": ["Repository path does not exist: x"]}
    out = preflight_node(state)  # type: ignore[arg-type]
    assert out["preflight"]["not_run"] == "upstream_errors"
    assert "errors" not in out


def test_node_respects_disable_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_DISABLE, "0")
    out = preflight_node({"repo_path": "", "errors": []})  # type: ignore[arg-type]
    assert out["preflight"]["not_run"] == f"disabled_by_{ENV_DISABLE}"


def test_node_emits_prefixed_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    monkeypatch.setattr(pf, "_probe", lambda cmd, timeout=0: (pf.EXIT_NOT_FOUND, ""))
    monkeypatch.delenv("JAVA_HOME", raising=False)
    monkeypatch.delenv(ENV_DISABLE, raising=False)

    out = preflight_node(  # type: ignore[arg-type]
        {"repo_path": str(tmp_path), "app_dir": "", "errors": []}
    )
    assert out["preflight"]["passed"] is False
    assert out["errors"]
    assert all(e.startswith(ERROR_PREFIX) for e in out["errors"])


def test_node_never_raises_when_probe_explodes(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("probe infrastructure is broken")

    # Patch where the node looks it up: it imported the symbol by name.
    monkeypatch.setattr("agent.nodes.preflight.run_preflight", _boom)
    monkeypatch.delenv(ENV_DISABLE, raising=False)

    out = preflight_node({"repo_path": "", "app_dir": "", "errors": []})  # type: ignore[arg-type]
    assert out["preflight"]["not_run"] == "probe_error"
    assert "errors" not in out
