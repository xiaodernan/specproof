"""Gradle + JUnit 5 适配器 (Phase 4)。

支持：Gradle 项目、JUnit 5 测试、离线模式、依赖缓存。
输出：统一的 RuntimeProfile、ExecutionResult、EvidenceFragment。
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from collections.abc import Callable
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


def _as_text(value: bytes | str | None) -> str:
    """把 subprocess 的输出（bytes | str | None）收敛成文本。

    `subprocess.run(text=True)` 正常给 str，但 `TimeoutExpired.stdout` 的类型是
    `bytes | str | None` —— 原样传进去会让声明为 `str` 的 `ExecutionResult.stdout`
    实际带上 bytes。这里统一收敛，超时路径与正常路径行为一致。
    """
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


#: 一条 stdout 启发式：正则 + 从 match 取出 (run, passed, failed, skipped) 的提取器。
_StdoutExtractor = Callable[[re.Match[str]], tuple[int, int, int, int]]


@register_adapter
class GradleAdapter(AdapterProtocol):
    """Gradle + JUnit 5 适配器。"""

    ADAPTER_ID = "java-gradle"
    LANGUAGE = "java"
    BUILD_TOOL = "gradle"

    # Gradle 标志文件
    MARKER_FILES = (
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        "settings.gradle.kts",
    )

    # 默认沙箱镜像
    DEFAULT_SANDBOX_IMAGE = "gradle:8.5-jdk21"
    DEFAULT_SANDBOX_DIGEST = "sha256:gradle8.5-jdk21-digest-placeholder"

    # 依赖缓存卷名
    GRADLE_CACHE_VOLUME = "specproof-gradle-cache-1000"

    @classmethod
    def detect(cls, project_root: Path) -> bool:
        """检测是否为 Gradle 项目。"""
        return any((project_root / marker).exists() for marker in cls.MARKER_FILES)

    @classmethod
    def prepare(cls, project_root: Path) -> RuntimeProfile:
        """准备 Gradle 运行时环境。"""
        # 检测 Gradle 版本
        gradle_version = cls._detect_gradle_version(project_root)
        # 检测 Java 版本
        java_version = cls._detect_java_version(project_root)
        # 检查 wrapper
        has_wrapper = (project_root / "gradlew").exists() or (project_root / "gradlew.bat").exists()

        # 沙箱镜像（可通过环境变量覆盖）
        import os
        sandbox_image = os.getenv("SPECPROOF_SANDBOX_GRADLE_IMAGE", cls.DEFAULT_SANDBOX_IMAGE)

        return RuntimeProfile(
            language=cls.LANGUAGE,
            build_tool=cls.BUILD_TOOL,
            language_version=java_version,
            build_tool_version=gradle_version,
            dependency_cache_path=Path("/gradle-cache") if has_wrapper else None,
            sandbox_image=sandbox_image,
            sandbox_digest=cls.DEFAULT_SANDBOX_DIGEST,
            extra={
                "has_wrapper": has_wrapper,
                "gradle_user_home": "/gradle-cache",
            },
        )

    @classmethod
    def execute(
        cls,
        project_root: Path,
        profile: RuntimeProfile,
        goal: str = "test",
        test_filter: str | None = None,
        parallel: int = 2,
        **kwargs: Any,
    ) -> ExecutionResult:
        """执行 Gradle 测试。"""
        if goal not in cls.get_supported_goals():
            raise AdapterNotImplemented(f"Goal '{goal}' not supported by {cls.ADAPTER_ID}")

        start = time.perf_counter()

        # 构建命令
        cmd = cls._build_command(project_root, profile, goal, test_filter, parallel)

        # 执行
        try:
            result = subprocess.run(
                cmd,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=600,  # 10 分钟超时
                env={
                    **dict(os.environ),
                    "GRADLE_USER_HOME": str(
                        (profile.extra or {}).get("gradle_user_home", "/gradle-cache")
                    ),
                },
            )
        except subprocess.TimeoutExpired as e:
            return ExecutionResult(
                exit_code=-1,
                stdout=_as_text(e.stdout),
                stderr=_as_text(e.stderr),
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
        """收集证据：JUnit XML 报告、构建日志、依赖树。"""
        fragments = []

        # 1. JUnit XML 测试报告
        junit_fragments = cls._collect_junit_reports(project_root, result)
        fragments.extend(junit_fragments)

        # 2. 构建日志片段
        build_fragment = EvidenceFragment(
            fragment_type="build",
            collector_version="gradle-adapter-1.0",
            payload={
                "adapter_id": cls.ADAPTER_ID,
                "exit_code": result.exit_code,
                "duration_ms": result.duration_ms,
                "tests_run": result.tests_run,
                "tests_passed": result.tests_passed,
                "tests_failed": result.tests_failed,
                "tests_skipped": result.tests_skipped,
                "parse_errors": result.parse_errors,
                "gradle_version": profile.build_tool_version,
                "java_version": profile.language_version,
            },
        )
        fragments.append(build_fragment)

        # 3. 依赖树（如果可用）
        dep_fragments = cls._collect_dependency_tree(project_root, profile)
        fragments.extend(dep_fragments)

        return fragments

    @classmethod
    def get_supported_goals(cls) -> list[str]:
        return ["test", "build", "check"]

    @classmethod
    def _detect_gradle_version(cls, project_root: Path) -> str:
        """检测 Gradle 版本。"""
        # 优先读取 wrapper
        wrapper_props = project_root / "gradle" / "wrapper" / "gradle-wrapper.properties"
        if wrapper_props.exists():
            content = wrapper_props.read_text(encoding="utf-8")
            match = re.search(r"gradle-([\d.]+)-", content)
            if match:
                return match.group(1)
        # 尝试运行 gradle --version
        try:
            gradlew = project_root / ("gradlew.bat" if os.name == "nt" else "gradlew")
            if gradlew.exists():
                result = subprocess.run(
                    [str(gradlew), "--version"],
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                match = re.search(r"Gradle ([\d.]+)", result.stdout)
                if match:
                    return match.group(1)
        except Exception:
            pass
        return "unknown"

    @classmethod
    def _detect_java_version(cls, project_root: Path) -> str:
        """检测 Java 版本。"""
        # 读取 build.gradle / build.gradle.kts
        for marker in ("build.gradle", "build.gradle.kts"):
            build_file = project_root / marker
            if build_file.exists():
                content = build_file.read_text(encoding="utf-8")
                # sourceCompatibility / targetCompatibility / java.toolchain
                match = re.search(r"sourceCompatibility\s*=\s*['\"]([\d.]+)['\"]", content)
                if match:
                    return match.group(1)
                match = re.search(
                    r"java\.toolchain\.languageVersion\s*=\s*JavaLanguageVersion\.of\((\d+)\)",
                    content,
                )
                if match:
                    return match.group(1)
        return "21"  # 默认

    @classmethod
    def _build_command(
        cls,
        project_root: Path,
        profile: RuntimeProfile,
        goal: str,
        test_filter: str | None,
        parallel: int,
    ) -> list[str]:
        """构建 Gradle 命令。"""
        gradlew = project_root / ("gradlew.bat" if os.name == "nt" else "gradlew")
        # 无 wrapper 时使用系统 gradle（不推荐）
        cmd = [str(gradlew)] if gradlew.exists() else ["gradle"]

        # 基础参数
        cmd.extend(["--no-daemon", "--no-build-cache"])

        # 离线模式：如果有依赖缓存
        if profile.dependency_cache_path:
            cmd.append("--offline")

        # 目标
        if goal == "test":
            cmd.append("test")
            if test_filter:
                cmd.append(f"--tests={test_filter}")
            # 并行执行
            if parallel > 1:
                cmd.append(f"-Dorg.gradle.workers.max={parallel}")
        elif goal == "build":
            cmd.append("build")
            cmd.append("-x test")  # build 不运行测试
        elif goal == "check":
            cmd.append("check")

        return cmd

    @classmethod
    def _parse_test_results(
        cls, project_root: Path, stdout: str, stderr: str
    ) -> tuple[int, int, int, int]:
        """解析测试结果：优先读取 JUnit XML，回退到 stdout 解析。"""
        # 查找 JUnit XML 报告
        xml_dirs = [
            project_root / "build" / "test-results" / "test",
            project_root / "build" / "reports" / "tests" / "test",
        ]
        for xml_dir in xml_dirs:
            if xml_dir.exists():
                xml_files = list(xml_dir.rglob("*.xml"))
                if xml_files:
                    return cls._parse_junit_xml(xml_files)

        # 回退：从 stdout 解析
        return cls._parse_stdout_results(stdout + stderr)

    @classmethod
    def _parse_junit_xml(cls, xml_files: list[Path]) -> tuple[int, int, int, int]:
        """解析 JUnit XML 报告。"""
        import xml.etree.ElementTree as ET

        tests_run = tests_passed = tests_failed = tests_skipped = 0
        for xml_file in xml_files:
            try:
                tree = ET.parse(xml_file)
                root = tree.getroot()
                for testsuite in root.iter("testsuite"):
                    tests_run += int(testsuite.get("tests", 0))
                    tests_failed += int(testsuite.get("failures", 0)) + int(
                        testsuite.get("errors", 0)
                    )
                    tests_skipped += int(testsuite.get("skipped", 0))
                tests_passed = tests_run - tests_failed - tests_skipped
            except Exception:
                continue
        return tests_run, tests_passed, tests_failed, tests_skipped

    @classmethod
    def _parse_stdout_results(cls, output: str) -> tuple[int, int, int, int]:
        """从 stdout 解析测试结果（启发式）。"""
        # Gradle 测试输出模式
        patterns: list[tuple[str, _StdoutExtractor]] = [
            (
                r"(\d+) tests completed, (\d+) failed, (\d+) skipped",
                lambda m: (
                    int(m.group(1)),
                    int(m.group(1)) - int(m.group(2)) - int(m.group(3)),
                    int(m.group(2)),
                    int(m.group(3)),
                ),
            ),
            (r"> Task :test\s+(\d+) tests completed", lambda m: (int(m.group(1)), 0, 0, 0)),
            (r"(\d+) tests completed", lambda m: (int(m.group(1)), 0, 0, 0)),
        ]

        for pattern, extractor in patterns:
            match = re.search(pattern, output)
            if match:
                return extractor(match)

        return 0, 0, 0, 0

    @classmethod
    def _collect_junit_reports(
        cls, project_root: Path, result: ExecutionResult
    ) -> list[EvidenceFragment]:
        """收集 JUnit XML 报告作为证据。"""
        fragments = []
        xml_dirs = [
            project_root / "build" / "test-results" / "test",
            project_root / "build" / "reports" / "tests" / "test",
        ]
        for xml_dir in xml_dirs:
            if xml_dir.exists():
                for xml_file in xml_dir.rglob("*.xml"):
                    try:
                        content = xml_file.read_text(encoding="utf-8")
                        fragments.append(EvidenceFragment(
                            fragment_type="build",
                            collector_version="gradle-adapter-1.0",
                            payload={
                                "type": "junit_xml",
                                "file": str(xml_file.relative_to(project_root)),
                                "content": content[:50000],  # 限制大小
                            },
                        ))
                    except Exception:
                        continue
        return fragments

    @classmethod
    def _collect_dependency_tree(
        cls, project_root: Path, profile: RuntimeProfile
    ) -> list[EvidenceFragment]:
        """收集依赖树。"""
        fragments = []
        try:
            gradlew = project_root / ("gradlew.bat" if os.name == "nt" else "gradlew")
            if gradlew.exists():
                result = subprocess.run(
                    [str(gradlew), "dependencies", "--configuration", "runtimeClasspath"],
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env={
                    **dict(os.environ),
                    "GRADLE_USER_HOME": str(
                        (profile.extra or {}).get("gradle_user_home", "/gradle-cache")
                    ),
                },
                )
                if result.returncode == 0:
                    fragments.append(EvidenceFragment(
                        fragment_type="build",
                        collector_version="gradle-adapter-1.0",
                        payload={
                            "type": "dependency_tree",
                            "content": result.stdout[:50000],
                        },
                    ))
        except Exception:
            pass
        return fragments


__all__ = ["GradleAdapter"]
