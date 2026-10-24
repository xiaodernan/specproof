"""Tests for Adapter Protocol (Phase 4)."""

import tempfile
from pathlib import Path

import pytest

from craft.adapters import protocol as proto
from craft.adapters.protocol import (
    AdapterNotImplemented,
    AdapterProtocol,
    EvidenceFragment,
    ExecutionResult,
    RuntimeProfile,
    detect_adapter,
    get_adapter,
    list_adapters,
    register_adapter,
)


@pytest.fixture(autouse=True)
def _restore_adapter_registry():
    """Snapshot the global registry and restore it after EVERY test.

    Without this, the `dummy` / `test-custom` adapters registered below stay in
    `_ADAPTER_REGISTRY` forever: `list_adapters()` then reports adapters that no
    test asked for, and `detect_adapter()` — which walks the registry in
    insertion order — becomes sensitive to which test ran first.
    """
    saved = dict(proto._ADAPTER_REGISTRY)
    try:
        yield
    finally:
        proto._ADAPTER_REGISTRY.clear()
        proto._ADAPTER_REGISTRY.update(saved)


def test_adapter_not_implemented_exception() -> None:
    with pytest.raises(AdapterNotImplemented):
        raise AdapterNotImplemented("test")


def test_runtime_profile_creation() -> None:
    profile = RuntimeProfile(
        language="java",
        build_tool="gradle",
        language_version="21",
        build_tool_version="8.5",
    )
    assert profile.language == "java"
    assert profile.build_tool == "gradle"
    assert profile.extra == {}


def test_execution_result_success() -> None:
    result = ExecutionResult(
        exit_code=0,
        stdout="OK",
        stderr="",
        duration_ms=1000,
        tests_run=10,
        tests_passed=10,
    )
    assert result.success is True


def test_execution_result_failure() -> None:
    result = ExecutionResult(
        exit_code=1,
        stdout="",
        stderr="FAILED",
        duration_ms=500,
        tests_run=10,
        tests_failed=2,
    )
    assert result.success is False


def test_evidence_fragment_creation() -> None:
    fragment = EvidenceFragment(
        fragment_type="build",
        collector_version="test-1.0",
        payload={"key": "value"},
    )
    assert fragment.fragment_type == "build"
    assert fragment.payload["key"] == "value"


def test_adapter_protocol_abstract_methods() -> None:
    """AdapterProtocol 是抽象基类，不能直接实例化。"""
    with pytest.raises(TypeError):
        AdapterProtocol()


def test_adapter_registry() -> None:
    """测试适配器注册表。"""
    @register_adapter
    class DummyAdapter(AdapterProtocol):
        ADAPTER_ID = "dummy"
        LANGUAGE = "dummy"
        BUILD_TOOL = "dummy"

        @classmethod
        def detect(cls, project_root: Path) -> bool:
            return (project_root / "dummy.marker").exists()

        @classmethod
        def prepare(cls, project_root: Path) -> RuntimeProfile:
            return RuntimeProfile(language="dummy", build_tool="dummy", language_version="1")

        @classmethod
        def execute(cls, project_root: Path, profile: RuntimeProfile, **kwargs) -> ExecutionResult:
            return ExecutionResult(exit_code=0, stdout="", stderr="", duration_ms=0)

        @classmethod
        def collect_evidence(
            cls, project_root: Path, profile: RuntimeProfile, result: ExecutionResult
        ) -> list[EvidenceFragment]:
            return []

    # 验证注册
    adapter = get_adapter("dummy")
    assert adapter == DummyAdapter

    # 验证列表
    adapters = list_adapters()
    dummy_caps = next((a for a in adapters if a["adapter_id"] == "dummy"), None)
    assert dummy_caps is not None
    assert dummy_caps["language"] == "dummy"

    # 验证检测需要标志文件
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        assert detect_adapter(tmp_path) is None  # 没有标志文件
        (tmp_path / "dummy.marker").write_text("test", encoding="utf-8")
        assert detect_adapter(tmp_path) == DummyAdapter


def test_detect_adapter() -> None:
    """测试自动检测。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        # 创建一个只有测试适配器识别的标志文件
        (tmp_path / "custom.marker").write_text("test", encoding="utf-8")

        # 注册一个检测 custom.marker 的适配器
        @register_adapter
        class TestCustomAdapter(AdapterProtocol):
            ADAPTER_ID = "test-custom"
            LANGUAGE = "custom"
            BUILD_TOOL = "custom"

            @classmethod
            def detect(cls, project_root: Path) -> bool:
                return (project_root / "custom.marker").exists()

            @classmethod
            def prepare(cls, project_root: Path) -> RuntimeProfile:
                return RuntimeProfile(language="custom", build_tool="custom", language_version="1")

            @classmethod
            def execute(
                cls, project_root: Path, profile: RuntimeProfile, **kwargs
            ) -> ExecutionResult:
                return ExecutionResult(exit_code=0, stdout="", stderr="", duration_ms=0)

            @classmethod
            def collect_evidence(
                cls,
                project_root: Path,
                profile: RuntimeProfile,
                result: ExecutionResult,
            ) -> list[EvidenceFragment]:
                return []

        detected = detect_adapter(tmp_path)
        assert detected == TestCustomAdapter


def test_get_adapter_not_found() -> None:
    with pytest.raises(AdapterNotImplemented):
        get_adapter("nonexistent")


def test_execution_result_defaults() -> None:
    result = ExecutionResult(exit_code=0, stdout="", stderr="", duration_ms=0)
    assert result.tests_run == 0
    assert result.tests_passed == 0
    assert result.tests_failed == 0
    assert result.tests_skipped == 0
    assert result.parse_errors == []


def test_runtime_profile_extra() -> None:
    profile = RuntimeProfile(
        language="python",
        build_tool="pytest",
        language_version="3.12",
        extra={"venv_path": "/venv"},
    )
    assert profile.extra["venv_path"] == "/venv"


class _ProbeAdapter(AdapterProtocol):
    """A concrete adapter used only to prove the registry is restored."""

    ADAPTER_ID = "registry-pollution-probe"
    LANGUAGE = "probe"
    BUILD_TOOL = "probe"

    @classmethod
    def detect(cls, project_root: Path) -> bool:
        return False

    @classmethod
    def prepare(cls, project_root: Path) -> RuntimeProfile:
        return RuntimeProfile(language="probe", build_tool="probe", language_version="1")

    @classmethod
    def execute(cls, project_root: Path, profile: RuntimeProfile, **kwargs) -> ExecutionResult:
        return ExecutionResult(exit_code=0, stdout="", stderr="", duration_ms=0)

    @classmethod
    def collect_evidence(
        cls, project_root: Path, profile: RuntimeProfile, result: ExecutionResult
    ) -> list[EvidenceFragment]:
        return []


def test_registry_pollution_probe_a_registers() -> None:
    """注册探针适配器；清理由 autouse fixture 在本用例结束时负责。

    与下一条配对：pytest 按文件顺序执行（本仓库未装用例随机化插件），
    所以 probe_b 一定在 probe_a 之后跑。
    """
    register_adapter(_ProbeAdapter)
    assert get_adapter("registry-pollution-probe") is _ProbeAdapter


def test_registry_pollution_probe_b_asserts_gone() -> None:
    """上一条注册的探针必须已经不在了 —— 证明 autouse fixture 真的还原了注册表。"""
    with pytest.raises(AdapterNotImplemented):
        get_adapter("registry-pollution-probe")
    assert "registry-pollution-probe" not in proto._ADAPTER_REGISTRY


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
