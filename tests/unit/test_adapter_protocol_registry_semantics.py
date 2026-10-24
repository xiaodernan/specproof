"""`craft/adapters/protocol.py` 的注册表语义与能力声明（Phase 4 的公共地基）。

`test_adapter_protocol.py` 已覆盖：四个数据类的构造/默认值、`AdapterProtocol` 抽象不可实例化、
`register_adapter`/`get_adapter`/`detect_adapter` 的 happy path。**没覆盖**：
- `register_adapter` 的**返回值**（它可当装饰器用 ⇒ 必须返回被装饰的类本身）；
- 重复 `ADAPTER_ID` 注册时**静默覆盖**（后注册者赢，无告警）；
- `detect_adapter` 对 `detect()` 抛异常的适配器**静默跳过**（docstring 没写的 fail-soft）；
- `get_capabilities()` 的完整形状（六个键）与 `goals` 来自 `get_supported_goals()`；
- `get_supported_goals()` 的默认值；
- `ExecutionResult.success` **只看退出码**（哪怕 `tests_failed > 0`）。

另：`test_adapter_protocol.py` 往**全局** `_ADAPTER_REGISTRY` 注册了 `dummy` / `test-custom`
且从不清理 ⇒ 注册表被测试污染（跨用例顺序敏感）。本文件用 autouse fixture 快照/还原注册表，
**不再加重污染**（已有的污染原样保留、不清除）；既有污染本身记为下一号队列。

只加测试，`craft/adapters/protocol.py` 一字未动。
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from craft.adapters import protocol as proto
from craft.adapters.protocol import (
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
def _restore_registry():
    """Snapshot the global registry and put it back — never leave test adapters behind."""
    saved = dict(proto._ADAPTER_REGISTRY)
    try:
        yield
    finally:
        proto._ADAPTER_REGISTRY.clear()
        proto._ADAPTER_REGISTRY.update(saved)


def _adapter(
    adapter_id: str,
    *,
    detect: Callable[[Path], bool] | None = None,
    goals: list[str] | None = None,
) -> type[AdapterProtocol]:
    """Build + register a concrete adapter; returns the class."""

    @register_adapter
    class _Adapter(AdapterProtocol):
        ADAPTER_ID = adapter_id
        LANGUAGE = "test-lang"
        BUILD_TOOL = "test-tool"

        @classmethod
        def detect(cls, project_root: Path) -> bool:  # type: ignore[override]
            return bool(detect and detect(project_root))

        @classmethod
        def prepare(cls, project_root: Path) -> RuntimeProfile:
            return RuntimeProfile(
                language="test-lang",
                build_tool="test-tool",
                language_version="1",
            )

        @classmethod
        def execute(
            cls, project_root: Path, profile: RuntimeProfile, **kwargs: Any
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

        if goals is not None:

            @classmethod
            def get_supported_goals(cls) -> list[str]:
                return list(goals)

    return _Adapter


# ── register_adapter 的返回值（装饰器契约） ─────────────────────────────


def test_register_adapter_returns_the_decorated_class() -> None:
    """注册器可当装饰器用 ⇒ 必须原样返回被装饰的类，否则 `@register_adapter` 会把类变成 None。"""
    seen: dict[str, type[AdapterProtocol]] = {}

    @register_adapter
    class _Returned(AdapterProtocol):
        ADAPTER_ID = "returned-probe"
        LANGUAGE = "x"
        BUILD_TOOL = "x"

        @classmethod
        def detect(cls, project_root: Path) -> bool:
            return False

        @classmethod
        def prepare(cls, project_root: Path) -> RuntimeProfile:
            return RuntimeProfile(language="x", build_tool="x", language_version="1")

        @classmethod
        def execute(
            cls, project_root: Path, profile: RuntimeProfile, **kwargs: Any
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

    seen["cls"] = _Returned
    assert seen["cls"] is _Returned
    assert _Returned.__name__ == "_Returned"
    assert get_adapter("returned-probe") is _Returned


# ── 重复 ADAPTER_ID：静默覆盖（钉住现状） ────────────────────────────────


def test_duplicate_adapter_id_silently_overwrites() -> None:
    first = _adapter("dup-id")
    second = _adapter("dup-id")
    # 现状：后者静默覆盖，没有告警、没有抛错。
    assert get_adapter("dup-id") is second
    assert get_adapter("dup-id") is not first


# ── detect_adapter 的 fail-soft：异常被吞（钉住现状 + 记为边界） ──────────


def test_detect_adapter_swallows_a_crashing_detect() -> None:
    def _boom(_root: Path) -> bool:
        raise OSError("permission denied while probing")

    _adapter("crash-only", detect=_boom)
    with tempfile.TemporaryDirectory() as tmp:
        # 现状：detect() 抛异常 ⇒ 该适配器被静默跳过，整体返回 None
        # （调用方只会看到「没检测到适配器」，看不到「探测本身崩了」）。
        assert detect_adapter(Path(tmp)) is None


def test_detect_adapter_falls_through_to_a_working_adapter() -> None:
    def _boom(_root: Path) -> bool:
        raise RuntimeError("broken probe")

    _adapter("crash-first", detect=_boom)
    working = _adapter("crash-after", detect=lambda root: (root / "ok.marker").exists())

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "ok.marker").write_text("x", encoding="utf-8")
        assert detect_adapter(root) is working


# ── 能力声明的完整形状 ──────────────────────────────────────────────────


def test_get_capabilities_has_exactly_the_six_declared_keys() -> None:
    caps = _adapter("caps-probe").get_capabilities()
    assert set(caps) == {
        "adapter_id",
        "language",
        "build_tool",
        "goals",
        "offline_capable",
        "sandbox_required",
    }
    assert caps == {
        "adapter_id": "caps-probe",
        "language": "test-lang",
        "build_tool": "test-tool",
        "goals": ["test"],
        "offline_capable": True,
        "sandbox_required": True,
    }


def test_capabilities_goals_come_from_get_supported_goals() -> None:
    caps = _adapter("goals-probe", goals=["test", "build", "lint"]).get_capabilities()
    assert caps["goals"] == ["test", "build", "lint"]


def test_get_supported_goals_defaults_to_test_only() -> None:
    assert _adapter("default-goals").get_supported_goals() == ["test"]


# ── list_adapters 反映注册表 ────────────────────────────────────────────


def test_list_adapters_reflects_registration() -> None:
    _adapter("listed-probe")
    ids = [caps["adapter_id"] for caps in list_adapters()]
    assert "listed-probe" in ids


# ── success 只看退出码 ──────────────────────────────────────────────────


def test_success_depends_only_on_the_exit_code() -> None:
    # 退出码 0 即成功，哪怕统计里写着 tests_failed > 0
    green = ExecutionResult(
        exit_code=0, stdout="", stderr="", duration_ms=1, tests_failed=3
    )
    assert green.success is True
    # 退出码非 0 即失败，哪怕 tests_passed 很多
    red = ExecutionResult(
        exit_code=1, stdout="", stderr="", duration_ms=1, tests_passed=99
    )
    assert red.success is False
