"""Tests for Gradle Adapter (Phase 4)."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from craft.adapters.gradle_adapter import GradleAdapter
from craft.adapters.protocol import AdapterNotImplemented, RuntimeProfile, ExecutionResult


def test_gradle_adapter_detect() -> None:
    """Gradle adapter detects build.gradle files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        assert GradleAdapter.detect(tmp_path) is False

        (tmp_path / "build.gradle").write_text("plugins { id 'java' }", encoding="utf-8")
        assert GradleAdapter.detect(tmp_path) is True

        tmp_path2 = Path(tmpdir + "2")
        tmp_path2.mkdir()
        (tmp_path2 / "build.gradle.kts").write_text("plugins { kotlin(\"jvm\") }", encoding="utf-8")
        assert GradleAdapter.detect(tmp_path2) is True

        tmp_path3 = Path(tmpdir + "3")
        tmp_path3.mkdir()
        (tmp_path3 / "settings.gradle").write_text("rootProject.name = 'test'", encoding="utf-8")
        assert GradleAdapter.detect(tmp_path3) is True


def test_gradle_adapter_detect_no_marker() -> None:
    """Non-Gradle projects return False."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / "pom.xml").write_text("<project></project>", encoding="utf-8")
        assert GradleAdapter.detect(tmp_path) is False

        (tmp_path / "package.json").write_text("{}", encoding="utf-8")
        assert GradleAdapter.detect(tmp_path) is False


def test_gradle_adapter_prepare() -> None:
    """Prepare returns RuntimeProfile with detected versions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / "build.gradle").write_text(
            "plugins { id 'java' }\n"
            "sourceCompatibility = '17'\n",
            encoding="utf-8",
        )
        (tmp_path / "gradlew").write_text("#!/bin/sh\necho 'wrapper'", encoding="utf-8")
        (tmp_path / "gradlew").chmod(0o755)

        profile = GradleAdapter.prepare(tmp_path)
        assert profile.language == "java"
        assert profile.build_tool == "gradle"
        assert profile.extra["has_wrapper"] is True


def test_gradle_adapter_prepare_no_wrapper() -> None:
    """Prepare works without gradle wrapper."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / "build.gradle").write_text("plugins { id 'java' }", encoding="utf-8")

        profile = GradleAdapter.prepare(tmp_path)
        assert profile.extra["has_wrapper"] is False


def test_gradle_adapter_execute_unsupported_goal() -> None:
    """Unsupported goal raises AdapterNotImplemented."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / "build.gradle").write_text("plugins { id 'java' }", encoding="utf-8")
        profile = GradleAdapter.prepare(tmp_path)

        with pytest.raises(AdapterNotImplemented):
            GradleAdapter.execute(tmp_path, profile, goal="deploy")


def test_gradle_adapter_supported_goals() -> None:
    goals = GradleAdapter.get_supported_goals()
    assert "test" in goals
    assert "build" in goals
    assert "check" in goals


def test_gradle_adapter_capabilities() -> None:
    caps = GradleAdapter.get_capabilities()
    assert caps["adapter_id"] == "java-gradle"
    assert caps["language"] == "java"
    assert caps["build_tool"] == "gradle"
    assert caps["offline_capable"] is True
    assert caps["sandbox_required"] is True


@patch("craft.adapters.gradle_adapter.subprocess.run")
def test_gradle_adapter_execute_test(mock_run: Mock) -> None:
    """Execute test goal with mocked subprocess."""
    mock_run.return_value = Mock(
        returncode=0,
        stdout="BUILD SUCCESSFUL\n5 tests completed, 0 failed, 0 skipped",
        stderr="",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / "build.gradle").write_text("plugins { id 'java' }", encoding="utf-8")
        (tmp_path / "gradlew").write_text("#!/bin/sh", encoding="utf-8")
        (tmp_path / "gradlew").chmod(0o755)

        profile = GradleAdapter.prepare(tmp_path)
        result = GradleAdapter.execute(tmp_path, profile, goal="test")

        assert isinstance(result, ExecutionResult)
        assert result.exit_code == 0
        mock_run.assert_called_once()


@patch("craft.adapters.gradle_adapter.subprocess.run")
def test_gradle_adapter_execute_build(mock_run: Mock) -> None:
    """Execute build goal."""
    mock_run.return_value = Mock(
        returncode=0,
        stdout="BUILD SUCCESSFUL",
        stderr="",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / "build.gradle").write_text("plugins { id 'java' }", encoding="utf-8")
        (tmp_path / "gradlew").write_text("#!/bin/sh", encoding="utf-8")
        (tmp_path / "gradlew").chmod(0o755)

        profile = GradleAdapter.prepare(tmp_path)
        result = GradleAdapter.execute(tmp_path, profile, goal="build")

        assert result.exit_code == 0
        # Verify -x test was added
        call_args = mock_run.call_args[0][0]
        # -x test is passed as a single argument
        assert any("-x" in arg for arg in call_args)


def test_gradle_adapter_parse_junit_xml() -> None:
    """Parse JUnit XML test results."""
    import xml.etree.ElementTree as ET

    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.example.Test" tests="5" failures="1" errors="0" skipped="1" time="10.5">
    <testcase name="testPass" classname="com.example.Test" time="1.0"/>
    <testcase name="testFail" classname="com.example.Test" time="2.0">
        <failure message="Assertion failed">Expected true but was false</failure>
    </testcase>
    <testcase name="testSkip" classname="com.example.Test" time="0.0">
        <skipped/>
    </testcase>
</testsuite>"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        xml_file = tmp_path / "TEST-com.example.Test.xml"
        xml_file.write_text(xml_content, encoding="utf-8")

        run, passed, failed, skipped = GradleAdapter._parse_junit_xml([xml_file])
        assert run == 5
        assert failed == 1
        assert skipped == 1
        assert passed == 3  # 5 - 1 - 1


def test_gradle_adapter_parse_stdout() -> None:
    """Parse test results from stdout."""
    output = "BUILD SUCCESSFUL\n5 tests completed, 1 failed, 0 skipped"
    run, passed, failed, skipped = GradleAdapter._parse_stdout_results(output)
    assert run == 5
    assert failed == 1
    assert skipped == 0
    assert passed == 4


def test_gradle_adapter_registry() -> None:
    """GradleAdapter is registered in protocol registry."""
    from craft.adapters.protocol import get_adapter
    adapter = get_adapter("java-gradle")
    assert adapter == GradleAdapter


if __name__ == "__main__":
    pytest.main([__file__, "-v"])