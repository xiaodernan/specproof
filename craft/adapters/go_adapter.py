"""Go 适配器增强 (Phase 4)。

对现有 Go 适配器的增强：CGO 离线编译支持、模块缓存机制、更健壮的测试结果解析。
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from craft.adapters.protocol import (
    AdapterNotImplemented,
    AdapterProtocol,
    EvidenceFragment,
    ExecutionResult,
    RuntimeProfile,
    register_adapter,
)
from sandbox.runner import child_output_text


def _read_text_or_none(path: Path | str) -> str | None:
    """Read a file as UTF-8, or ``None`` when it cannot be read as text.

    Covers three different facts with one answer: the file is absent, the OS
    refuses to read it (permissions, a directory where a file was expected), or
    the bytes are not UTF-8. Callers that need to tell "absent" from "corrupt"
    must check existence themselves — ``prepare`` records both in
    ``extra["has_go_mod"]`` / ``extra["go_mod_readable"]``.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError):
        return None


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
        # 读取 go.mod 获取 Go 版本。**只读一次**：旧版读了两次，第二次没有 try
        # 保护，文件不可读时会让 prepare 直接抛而不是退回默认值。
        go_mod = project_root / "go.mod"
        go_mod_text = _read_text_or_none(go_mod)
        go_mod_content = go_mod_text or ""
        go_version = "1.23"  # 默认
        match = re.search(r"go\s+([\d.]+)", go_mod_content)
        if match:
            go_version = match.group(1)

        # 检查是否启用 CGO
        cgo_enabled = "//go:cgo_enable" in go_mod_content or "CGO" in go_mod_content.upper()

        # 沙箱镜像（可通过环境变量覆盖）
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
                # 「存在但读不出来」（权限、非 UTF-8、同名目录）与「声明里没有
                # 版本」在旧版里长得一模一样——都退回默认 1.23。把「读没读到」
                # 单独记一笔，免得 profile 替一个坏文件撒谎。
                "go_mod_readable": go_mod_text is not None,
            },
        )

    @classmethod
    def execute(
        cls,
        project_root: Path,
        profile: RuntimeProfile,
        goal: str = "test",
        **kwargs: Any,
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
            env = dict(os.environ)
            # 设置离线模式
            env["GOPROXY"] = "off"
            env["GONOSUMCHECK"] = "*"
            env["GOFLAGS"] = "-mod=mod"

            # 设置 GOCACHE
            if profile.dependency_cache_path:
                env["GOCACHE"] = str(profile.dependency_cache_path)

            completed = subprocess.run(
                cmd,
                cwd=project_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,  # 10 分钟超时
                env=env,
            )
        except subprocess.TimeoutExpired as e:
            return ExecutionResult(
                exit_code=-1,
                stdout=child_output_text(e.stdout),
                stderr=child_output_text(e.stderr),
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
        s_stdout = child_output_text(completed.stdout)
        s_stderr = child_output_text(completed.stderr)

        # 解析测试结果
        tests_run, tests_passed, tests_failed, tests_skipped = cls._parse_test_results(
            project_root, s_stdout, s_stderr
        )

        return ExecutionResult(
            exit_code=completed.returncode,
            stdout=s_stdout,
            stderr=s_stderr,
            duration_ms=duration_ms,
            tests_run=tests_run,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            tests_skipped=tests_skipped,
            raw_output=s_stdout + s_stderr,
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
                "content_text": _read_text_or_none(project_root / "go.mod"),
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
                "cgo_enabled": (profile.extra or {}).get("cgo_enabled", False),
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
                "cgo_enabled": (profile.extra or {}).get("cgo_enabled", False),
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
        #
        # No try/except here (#509): every call below is `re.findall` /
        # `re.search` with a literal pattern, which cannot raise for any input.
        # The blind catch that used to wrap this block was therefore dead code,
        # and its justification ("JSON parse failed -> fall through") described
        # a mechanism that did not exist — the fallback is driven by
        # `tests_run == 0`, not by an exception.
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
                passes = re.findall(r'--- PASS:\s+\S+', full_output)
                fails = re.findall(r'--- FAIL:\s+\S+', full_output)
                skips = re.findall(r'--- SKIP:\s+\S+', full_output)
                if passes or fails or skips:
                    tests_run = len(passes) + len(fails) + len(skips)
                    tests_passed = len(passes)
                    tests_failed = len(fails)
                    tests_skipped = len(skips)

        return tests_run, tests_passed, tests_failed, tests_skipped

    @classmethod
    def get_capabilities(cls) -> dict[str, Any]:
        base = super().get_capabilities() if hasattr(super(), 'get_capabilities') else {}
        return {
            **base,
            "cgo_enabled": False,  # 将在 prepare() 中动态确定
        }


__all__ = ["GoAdapter"]
