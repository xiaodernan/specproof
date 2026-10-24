"""统一适配器协议 (Phase 4)。

定义所有语言/构建工具适配器必须实现的接口。
确保 fail-closed：不支持的语言抛 AdapterNotImplemented，绝不静默通过。
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class AdapterNotImplemented(Exception):  # noqa: N818 — domain term, public API
    """适配器不支持该语言/构建工具。"""
    pass


@dataclass
class RuntimeProfile:
    """运行时环境画像：语言版本、构建工具、依赖缓存等。"""
    language: str
    build_tool: str
    language_version: str
    build_tool_version: str | None = None
    dependency_cache_path: Path | None = None
    sandbox_image: str | None = None
    sandbox_digest: str | None = None
    extra: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.extra is None:
            self.extra = {}


@dataclass
class ExecutionResult:
    """单次执行的结果。"""
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    raw_output: str = ""
    parse_errors: list[str] | None = None

    def __post_init__(self) -> None:
        if self.parse_errors is None:
            self.parse_errors = []

    @property
    def success(self) -> bool:
        return self.exit_code == 0


@dataclass
class EvidenceFragment:
    """执行产生的证据片段（可序列化写入 MongoDB/MinIO）。"""
    fragment_type: str  # http | db | redis | mq | schema | perf | static | build | object
    collector_version: str
    payload: dict[str, Any]


class AdapterProtocol(abc.ABC):
    """适配器协议：所有语言适配器必须实现的接口。"""

    #: 适配器标识，如 "java-maven", "java-gradle", "python-pytest", "go-test", "node-npm"
    ADAPTER_ID: str

    #: 支持的语言
    LANGUAGE: str

    #: 支持的构建工具
    BUILD_TOOL: str

    @classmethod
    @abc.abstractmethod
    def detect(cls, project_root: Path) -> bool:
        """检测项目是否适用此适配器。

        Returns:
            True 如果项目包含该适配器识别的标志文件（如 pom.xml, build.gradle, pyproject.toml 等）
        """
        ...

    @classmethod
    @abc.abstractmethod
    def prepare(cls, project_root: Path) -> RuntimeProfile:
        """准备运行时环境。

        包括：检查沙箱镜像、下载依赖缓存、验证构建工具版本等。
        失败时抛异常，绝不返回部分结果。

        Returns:
            RuntimeProfile 包含语言版本、构建工具版本、依赖缓存路径、沙箱镜像等
        """
        ...

    @classmethod
    @abc.abstractmethod
    def execute(cls, project_root: Path, profile: RuntimeProfile, **kwargs: Any) -> ExecutionResult:
        """在准备好的环境中执行测试/构建。

        Args:
            project_root: 项目根目录
            profile: prepare() 返回的运行时画像
            **kwargs: 额外参数（如测试过滤、并行度等）

        Returns:
            ExecutionResult 包含退出码、stdout/stderr、测试统计、解析错误等
        """
        ...

    @classmethod
    @abc.abstractmethod
    def collect_evidence(
        cls, project_root: Path, profile: RuntimeProfile, result: ExecutionResult
    ) -> list[EvidenceFragment]:
        """从执行结果中收集证据片段。

        解析测试报告、构建日志、覆盖率报告等，生成标准化的 EvidenceFragment。
        解析失败时记录在 fragment 的 payload 中，绝不抛异常。

        Returns:
            EvidenceFragment 列表
        """
        ...

    @classmethod
    def get_supported_goals(cls) -> list[str]:
        """返回支持的执行目标，如 ["test", "build", "lint"]。"""
        return ["test"]

    @classmethod
    def get_capabilities(cls) -> dict[str, Any]:
        """返回适配器能力声明，用于兼容性矩阵。"""
        return {
            "adapter_id": cls.ADAPTER_ID,
            "language": cls.LANGUAGE,
            "build_tool": cls.BUILD_TOOL,
            "goals": cls.get_supported_goals(),
            "offline_capable": True,  # 是否支持完全离线执行
            "sandbox_required": True,  # 是否需要沙箱隔离
        }


# 适配器注册表
_ADAPTER_REGISTRY: dict[str, type[AdapterProtocol]] = {}


def register_adapter(adapter_cls: type[AdapterProtocol]) -> type[AdapterProtocol]:
    """注册适配器到全局注册表。"""
    _ADAPTER_REGISTRY[adapter_cls.ADAPTER_ID] = adapter_cls
    return adapter_cls


def get_adapter(adapter_id: str) -> type[AdapterProtocol]:
    """按 ID 获取适配器类。"""
    if adapter_id not in _ADAPTER_REGISTRY:
        raise AdapterNotImplemented(f"No adapter registered for {adapter_id}")
    return _ADAPTER_REGISTRY[adapter_id]


def detect_adapter(project_root: Path) -> type[AdapterProtocol] | None:
    """自动检测项目适用的适配器。

    按注册顺序检测，返回第一个 `detect()` 为 True 的适配器，或 None。

    `detect()` 抛出的异常**不再被吞掉**。此前这里是 `except Exception:
    continue`，于是「探测本身崩了」会被报成「没检测到适配器」——调用方无从
    分辨这两件事，而这正是本仓库最反对的静默失败形态（启动链路要 fail-loud）。
    改前实测：生产代码零调用方（只有测试引用），所以现在改没有爆炸半径；
    等 Phase 4 真的接上自动检测时，坏探子会当场炸出来而不是伪装成「不支持」。
    """
    for adapter_cls in _ADAPTER_REGISTRY.values():
        if adapter_cls.detect(project_root):
            return adapter_cls
    return None


def list_adapters() -> list[dict[str, Any]]:
    """列出所有已注册适配器的能力声明。"""
    return [cls.get_capabilities() for cls in _ADAPTER_REGISTRY.values()]


__all__ = [
    "AdapterNotImplemented",
    "RuntimeProfile",
    "ExecutionResult",
    "EvidenceFragment",
    "AdapterProtocol",
    "register_adapter",
    "get_adapter",
    "detect_adapter",
    "list_adapters",
]
