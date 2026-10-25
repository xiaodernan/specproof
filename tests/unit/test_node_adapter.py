"""Tests for Node.js Adapter (Phase 4)."""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from craft.adapters.node_adapter import NodeAdapter
from craft.adapters.protocol import (
    AdapterNotImplemented,
    ExecutionResult,
    RuntimeProfile,
)


def test_node_adapter_detect() -> None:
    """检测 Node.js 项目。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        # 无 package.json 返回 False
        assert NodeAdapter.detect(tmp_path) is False

        # 有 package.json 且有 test 脚本返回 True
        pkg = {"scripts": {"test": "echo 'hello'"}, "dependencies": {}}
        (tmp_path / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
        assert NodeAdapter.detect(tmp_path) is True

        # 有 package.json 但无 test 脚本
        pkg2 = {"dependencies": {}}
        (tmp_path / "package.json").write_text(json.dumps(pkg2), encoding="utf-8")
        assert NodeAdapter.detect(tmp_path) is True  # package.json 存在即检测 through


def test_node_adapter_prepare() -> None:
    """Prepare 返回 RuntimeProfile。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        pkg = {"scripts": {"test": "echo 'hello'"}, "dependencies": {}}
        (tmp_path / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
        profile = NodeAdapter.prepare(tmp_path)
        assert profile.language == "javascript"
        assert profile.build_tool == "npm"
        assert profile.language_version == "22"
        assert profile.dependency_cache_path is not None


def test_node_adapter_prepare_no_test_script() -> None:
    """Prepare 在无 test 脚本时也能工作。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        pkg = {"dependencies": {}}
        (tmp_path / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
        profile = NodeAdapter.prepare(tmp_path)
        assert profile.language == "javascript"


def test_node_adapter_execute_test() -> None:
    """Execute test goal - verify ExecutionResult structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        pkg = {"scripts": {"test": "echo 'test completed successfully'"}, "dependencies": {}}
        (tmp_path / "package.json").write_text(json.dumps(pkg), encoding="utf-8")

        profile = NodeAdapter.prepare(tmp_path)

        # Mock subprocess.run to simulate successful npm test execution
        mock_result = subprocess.CompletedProcess(
            args=["npm", "test"],
            returncode=0,
            stdout=b"Tests: 1 passed, 0 failed, 0 skipped\n",
            stderr=b"",
        )

        with patch("subprocess.run", return_value=mock_result):
            result = NodeAdapter.execute(tmp_path, profile, goal="test")

        assert isinstance(result, ExecutionResult)
        # 验证结果结构
        assert result.exit_code == 0  # 模拟成功
        assert result.tests_run == 1
        assert result.tests_passed == 1
        assert result.tests_failed == 0
        assert result.tests_skipped == 0


def test_node_adapter_execute_unsupported_goal() -> None:
    """Unsupported goal raises AdapterNotImplemented."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        pkg = {"scripts": {"test": "echo 'hello'"}, "dependencies": {}}
        (tmp_path / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
        profile = NodeAdapter.prepare(tmp_path)

        with pytest.raises(AdapterNotImplemented):
            NodeAdapter.execute(tmp_path, profile, goal="deploy")


def test_node_adapter_supported_goals() -> None:
    """Supported goals 包含 test、vitest、node-test。"""
    goals = NodeAdapter.get_supported_goals()
    assert "test" in goals
    assert "vitest" in goals
    assert "node-test" in goals


def test_node_adapter_capabilities() -> None:
    """Capabilities 返回正确的字段。"""
    caps = NodeAdapter.get_capabilities()
    assert caps["adapter_id"] == "node-npm"
    assert caps["language"] == "javascript"
    assert caps["build_tool"] == "npm"
    assert caps["offline_capable"] is True
    assert caps["sandbox_required"] is True


def test_node_adapter_execute_node_test() -> None:
    """Execute node-test goal."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        pkg = {"scripts": {"test": "echo 'hello'"}, "dependencies": {}}
        (tmp_path / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
        profile = NodeAdapter.prepare(tmp_path)

        # Mock subprocess.run to simulate successful node --test execution
        mock_result = subprocess.CompletedProcess(
            args=["node", "--test"],
            returncode=0,
            stdout=b"",
            stderr=b"",
        )

        with patch("subprocess.run", return_value=mock_result):
            result = NodeAdapter.execute(tmp_path, profile, goal="node-test")

        assert isinstance(result, ExecutionResult)