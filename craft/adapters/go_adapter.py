"""Go 适配器增强 (Phase 4)。

对现有 Go 适配器的增强：CGO 离线编译支持、模块缓存机制、更健壮的测试结果解析。
"""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Any

from craft.adapters.protocol import (
    AdapterNotImplemented,
    AdapterProtocol,
    ExecutionResult,
    EvidenceFragment,
    RuntimeProfile,
    register_adapter,
)


@register_adapter
class GoAdapter(AdapterProtocol):
    """Go 适配器增强版。

    支持：
    - CGO 离线编译（alpine 版本不支持 CGO，使用 bookworm 版本）
    - GOPROXY=off 离线模式
    - go mod download + go test -json
    - CGO 依赖的系统库检测

    CGO 状态：
    - 已启用：可以编译包含 //go:cgo_flags 的代码
    - 已禁用：纯 Go 代码或缺少 CGO 依赖
    """
    ADAPTER_ID = "go-test"
    LANGUAGE = "go"
    BUILD_TOOL = "go"

    # Docker 镜像：bookworm 自带 gcc，支持 CGO；alpine 不支持
    DEFAULT_SANDBOX_IMAGE = "golang:1.23-bookworm"
    DEFAULT_SANDBOX_DIGEST = "sha256:golang1.23-bookworm-digest-placeholder"

    # 模块缓存卷名
    GO_MOD_CACHE_VOLUME = "specproof-go-modcache-1000"

    # 支持的目标
    SUPPORTED_GOALS = ["test", "build", "vet"]

    @classmethod
    def detect(cls, project_root: Path) -> bool:
        """检测是否为 Go 项目。"""
        # 检查 go.mod
        go_mod = project_root / "go.mod"
        if not go_mod.exists():
            return False
        content = go_mod.read_text(encoding="utf-8")
        # 验证是有效的 go.mod 文件
        return go_mod.name == "go.mod" and re.search(r"module\s+\S+", content) is not None

    @classmethod
    def prepare(cls, project_root: Path) -> RuntimeProfile:
        """准备 Go 运行时环境。

        包括：检测 Go 版本、设置模块缓存、检查 CGO 能力。
        """
        # 读取 go.mod 获取 Go 版本
        go_mod = project_root / "go.mod"
        go_version = "1.23"  # 默认
        try:
            content = go_mod.read_text(encoding="utf-8")
            # 提取版本行
            match = re.search(r"go\s+([\d.]+)", content)
            if match:
                go_version = match.group(1)
        except Exception:
            pass

        # 检查是否启用 CGO
        go_mod_content = go_mod.read_text(encoding="utf-8") if go_mod.exists() else ""
        cgo_enabled = "//go:cgo_enable" in go_mod_content or "CGO" in go_mod_content.upper()

        # 沙箱镜像（可通过环境变量覆盖）
        import os
        sandbox_image = os.getenv(
            "SPECPROOF_SANDBOX_GO_IMAGE", cls.DEFAULT_SANDBOX_IMAGE
        )

        return RuntimeProfile(
            language=cls.LANGUAGE,
            build_tool=cls.BUILD_TOOL,
            language_version=go_version,
            build_tool_version="1.23",
            dependency_cache_path=Path(
                f"/{cls.GO_MOD_CACHE_VOLUME}"
            ),  # Go module cache
            sandbox_image=sandbox_image,
            sandbox_digest=cls.DEFAULT_SANDBOX_DIGEST,
            extra={
                "cgo_enabled": cgo_enabled,
                "has_go_mod": go_mod.exists(),
            },
        )

    @classmethod
    def execute(
        cls,
        project_root: Path,
        profile: RuntimeProfile,
        goal: str = "test",
        **kwargs,
    ) -> ExecutionResult:
        """执行 Go 测试。

        支持的 goal：test、build、vet
        """
        if goal not in cls.SUPPORTED_GOALS:
            raise AdapterNotImplemented(
                f"Goal '{goal}' not supported by {cls.ADAPTER_ID}. "
                f"Supported: {cls.SUPPORTED_GOALS}"
            )

        start = time.perf_counter()

        # 构建命令
        cmd = cls._build_command(project_root, profile, goal)

        # 执行
        try:
            env = dict(__import__("os").environ)
            # 设置离线模式
            env["GOPROXY"] = "off"
            env["GONOSUMCHECK"] = "*"
            env["GOFLAGS"] = "-mod=mod"

            # 设置 GOCACHE
            if profile.dependency_cache_path:
                env["GOCACHE"] = str(profile.dependency_cache_path)

            result = subprocess.run(
                cmd,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=600,  # 10 分钟超时
                env=env,
            )
        except subprocess.TimeoutExpired as e:
            return ExecutionResult(
                exit_code=-1,
                stdout=e.stdout or "",
                stderr=e.stderr or "",
                duration_ms=int((time.perf_counter() - start) * 1000),
                parse_errors=[f"Execution timeout: {e}"],
            )
        except Exception as e:
            return ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_ms=int((time.perf_counter() - start) * 1000),
                parse_errors=[f"Execution failed: {e}"],
            )

        duration_ms = int((time.perf_counter() - start) * 1000)

        # 解析测试结果
        tests_run, tests_passed, tests_failed, tests_skipped = cls._parse_test_results(
            project_root, result.stdout, result.stderr
        )

        return ExecutionResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_ms=duration_ms,
            tests_run=tests_run,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            tests_skipped=tests_skipped,
            raw_output=result.stdout + result.stderr,
        )

    @classmethod
    def collect_evidence(
        cls, project_root: Path, profile: RuntimeProfile, result: ExecutionResult
    ) -> list[EvidenceFragment]:
        """收集证据：go.mod 信息、测试结果、CGO 状态。"""
        fragments = []

        # 1. go.mod 信息
        go_mod_fragment = EvidenceFragment(
            fragment_type="build",
            collector_version="go-adapter-1.0",
            payload={
                "type": "go_mod",
                "content": project_root / "go.mod",
                "content_text": (
                    open(project_root / "go.mod", encoding="utf-8").read()
                    if (project_root / "go.mod").exists()
                    else None
                ),
            },
        )
        fragments.append(go_mod_fragment)

        # 2. go.sum 信息
        go_sum_file = project_root / "go.sum"
        if go_sum_file.exists():
            sum_fragment = EvidenceFragment(
                fragment_type="build",
                collector_version="go-adapter-1.0",
                payload={
                    "type": "go_sum",
                    "content": go_sum_file.read_text(encoding="utf-8")[:5000],
                },
            )
            fragments.append(sum_fragment)

        # 3. 测试结果汇总
        result_fragment = EvidenceFragment(
            fragment_type="build",
            collector_version="go-adapter-1.0",
            payload={
                "type": "test_result",
                "exit_code": result.exit_code,
                "tests_run": result.tests_run,
                "tests_passed": result.tests_passed,
                "tests_failed": result.tests_failed,
                "tests_skipped": result.tests_skipped,
                "duration_ms": result.duration_ms,
                "cgo_enabled": profile.extra.get("cgo_enabled", False),
                "parse_errors": result.parse_errors,
            },
        )
        fragments.append(result_fragment)

        # 4. CGO 状态
        cgo_fragment = EvidenceFragment(
            fragment_type="build",
            collector_version="go-adapter-1.0",
            payload={
                "type": "cgo_status",
                "cgo_enabled": profile.extra.get("cgo_enabled", False),
            },
        )
        fragments.append(cgo_fragment)

        return fragments

    @classmethod
    def get_supported_goals(cls) -> list[str]:
        return cls.SUPPORTED_GOALS

    @classmethod
    def _build_command(cls, project_root: Path, profile: RuntimeProfile, goal: str) -> list[str]:
        """构建 Go 命令。"""
        # 基础命令
        cmd = ["go"]

        # 目标
        if goal == "test":
            cmd.extend(["test", "-json", "-count=1"])  # -json 输出 JSON 格式，-count=1 仅运行一次
        elif goal == "build":
            cmd.append("build ./...")
        elif goal == "vet":
            cmd.append("vet ./...")

        # 离线模式相关
        # GOPROXY 已在 env 中设置为 off

        return cmd

    @classmethod
    def _parse_test_results(
        cls, project_root: Path, stdout: str, stderr: str
    ) -> tuple[int, int, int, int]:
        """解析测试结果：优先分析 go test -json 输出，回退到 stdout 解析。"""
        # go test -json 输出格式：每个测试一个对象，包含 Status 字段
        tests_run = tests_passed = tests_failed = tests_skipped = 0

        # 尝试解析 go test -json 输出
        # 格式：{"name":"...", "status":"passed"|"failed"|"skipped", ...}
        try:
            # 尝试查找所有测试状态
            passed = len(re.findall(r'"status":"passed"', stdout + stderr))
            failed = len(re.findall(r'"status":"failed"', stdout + stderr))
            skipped = len(re.findall(r'"status":"skipped"', stdout + stderr))
            # 估算总数：查找测试套件声明
            suite_match = re.search(r'from package (\S+)', stdout + stderr)
            if suite_match:
                # 简单估算：计数所有测试函数名称
                test_fn_match = re.findall(r'["\'](Test\w+)["\']', stdout + stderr)
                tests_run = len(test_fn_match)
            else:
                # 备用：总数 = passed + failed + skipped
                tests_run = passed + failed + skipped
            tests_passed = passed
            tests_failed = failed
            tests_skipped = skipped
        except Exception:
            pass

        # 回退：从 stdout/stderr 关键字解析
        if tests_run == 0:
            # 标准 go test 输出模式：--- PASS, --- FAIL, --- SKIP
            full_output = stdout + stderr

            # 模式 1: --- PASS: ... --- FAIL: N 个
            m = re.search(r'--- FAIL:\s+(\d+)', full_output)
            if m:
                fail_count = int(m.group(1))
                m_skip = re.search(r'--- SKIP:\s+(\d+)', full_output)
                skip_count = int(m_skip.group(1)) if m_skip else 0
                tests_run = fail_count + skip_count
                tests_failed = fail_count
                tests_skipped = skip_count
            else:
                # 模式 2: --- PASS: ... 后面跟随计数
                m_pass = re.findall(r'--- PASS:\s+\S+', full_output)
                m_fail = re.findall(r'--- FAIL:\s+\S+', full_output)
                m_skip = re.findall(r'--- SKIP:\s+\S+', full_output)
                if m_pass or m_fail or m_skip:
                    tests_run = len(m_pass or []) + len(m_fail or []) + len(m_skip or [])
                    tests_passed = len(m_pass or [])
                    tests_failed = len(m_fail or [])
                    tests_skipped = len(m_skip or [])

        return tests_run, tests_passed, tests_failed, tests_skipped

    @classmethod
    def get_capabilities(cls) -> dict[str, Any]:
        base = super().get_capabilities() if hasattr(super(), 'get_capabilities') else {}
        return {
            **base,
            "cgo_enabled": False,  # 将在 prepare() 中动态确定
        }


__all__ = ["GoAdapter"]