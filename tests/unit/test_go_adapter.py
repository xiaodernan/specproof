"""Tests for Go Adapter (Phase 4)."""

import tempfile
from pathlib import Path

import pytest

from craft.adapters.go_adapter import GoAdapter
from craft.adapters.protocol import (
    AdapterNotImplemented,
    ExecutionResult,
)


def test_go_adapter_detect() -> None:
    """检测 Go 项目。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        # 无 go.mod 返回 False
        assert GoAdapter.detect(tmp_path) is False

        # 有 go.mod 返回 True
        go_mod_content = "module example\ngo 1.21\n"
        (tmp_path / "go.mod").write_text(go_mod_content, encoding="utf-8")
        assert GoAdapter.detect(tmp_path) is True

        # 无效的 go.mod 返回 False
        (tmp_path / "go.mod").write_text("invalid", encoding="utf-8")
        assert GoAdapter.detect(tmp_path) is False


def test_go_adapter_prepare() -> None:
    """Prepare 返回 RuntimeProfile 并检测 CGO 状态。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        go_mod_content = "module example\ngo 1.21\n"
        (tmp_path / "go.mod").write_text(go_mod_content, encoding="utf-8")
        profile = GoAdapter.prepare(tmp_path)
        assert profile.language == "go"
        assert profile.build_tool == "go"
        assert profile.language_version == "1.21"

        # 有 CGO 相关内容
        go_mod2_content = "module example\ngo 1.21\n//go:cgo enable\n"
        (tmp_path / "go.mod").write_text(go_mod2_content, encoding="utf-8")
        profile2 = GoAdapter.prepare(tmp_path)
        # 这条断言是本测试存在的理由（docstring 说「检测 CGO 状态」）：
        # 之前只 prepare 不断言，等于什么都没验。
        assert profile2.extra["cgo_enabled"] is True


def test_go_adapter_execute_test() -> None:
    """Execute test goal。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        go_mod_content = "module example\ngo 1.21\n"
        (tmp_path / "go.mod").write_text(go_mod_content, encoding="utf-8")
        (tmp_path / "go.sum").write_text("", encoding="utf-8")
        # 创建一个简单的 main.go
        main_go = "package main\n\nfunc main() {}\n"
        (tmp_path / "main.go").write_text(main_go, encoding="utf-8")

        profile = GoAdapter.prepare(tmp_path)
        result = GoAdapter.execute(tmp_path, profile, goal="test")

        assert isinstance(result, ExecutionResult)


def test_go_adapter_execute_unsupported_goal() -> None:
    """Unsupported goal raises AdapterNotImplemented。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        go_mod_content = "module example\ngo 1.21\n"
        (tmp_path / "go.mod").write_text(go_mod_content, encoding="utf-8")
        profile = GoAdapter.prepare(tmp_path)

        with pytest.raises(AdapterNotImplemented):
            GoAdapter.execute(tmp_path, profile, goal="deploy")


def test_go_adapter_supported_goals() -> None:
    """Supported goals 包含 test、build、vet。"""
    goals = GoAdapter.get_supported_goals()
    assert "test" in goals
    assert "build" in goals
    assert "vet" in goals


def test_go_adapter_capabilities() -> None:
    """Capabilities 返回字段。"""
    caps = GoAdapter.get_capabilities()
    assert caps["adapter_id"] == "go-test"
    assert caps["language"] == "go"
    assert caps["build_tool"] == "go"


def test_go_adapter_parse_test_json() -> None:
    """解析 go test -json 输出。"""
    output = (
        '{"name":"example/test","status":"passed","elapsed":1.5}\n'
        '{"name":"example/test2","status":"failed","elapsed":2.0}\n'
        '{"name":"example/test3","status":"skipped","elapsed":0.5}'
    )
    tests_run, passed, failed, skipped = GoAdapter._parse_test_results(
        Path("."), output, ""
    )
    assert tests_run == 3
    assert passed == 1
    assert failed == 1
    assert skipped == 1


def test_go_adapter_execute_build() -> None:
    """Execute build goal。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        go_mod_content = "module example\ngo 1.21\n"
        (tmp_path / "go.mod").write_text(go_mod_content, encoding="utf-8")
        profile = GoAdapter.prepare(tmp_path)
        result = GoAdapter.execute(tmp_path, profile, goal="build")

        assert isinstance(result, ExecutionResult)


def test_go_adapter_execute_vet() -> None:
    """Execute vet goal。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        go_mod_content = "module example\ngo 1.21\n"
        (tmp_path / "go.mod").write_text(go_mod_content, encoding="utf-8")
        profile = GoAdapter.prepare(tmp_path)
        result = GoAdapter.execute(tmp_path, profile, goal="vet")

        assert isinstance(result, ExecutionResult)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
