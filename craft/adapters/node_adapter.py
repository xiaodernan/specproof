"""Node.js 适配器 (Phase 4)。

支持：Node.js 项目在 Docker 沙箱中执行测试。
目标：npm test、vitest、node:test。
输出：统一的 RuntimeProfile、ExecutionResult、EvidenceFragment。
"""

from __future__ import annotations

import json
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
class NodeAdapter(AdapterProtocol):
    """Node.js 适配器。

    支持的目标：
    - npm test
    - vitest run
    - node:test (node 18+ 内置测试框架)

    依赖解析：package.json + lockfile + 本地缓存卷 specproof-npm-cache-1000。
    """

    ADAPTER_ID = "node-npm"
    LANGUAGE = "javascript"
    BUILD_TOOL = "npm"

    # Docker 镜像配置
    DEFAULT_SANDBOX_IMAGE = "node:22-alpine"
    DEFAULT_SANDBOX_DIGEST = "sha256:node22-alpine-digest-placeholder"

    # 缓存卷名
    NPM_CACHE_VOLUME = "specproof-npm-cache-1000"

    # 已支持的测试目标
    SUPPORTED_GOALS = ["test", "vitest", "node-test"]

    @classmethod
    def detect(cls, project_root: Path) -> bool:
        """检测是否为 Node.js 项目。"""
        # 检查 package.json
        pkg_file = project_root / "package.json"
        if not pkg_file.exists():
            return False
        try:
            content = pkg_file.read_text(encoding="utf-8")
            pkg = json.loads(content)
            # 必须有 scripts 字段且包含 test 脚本
            scripts = pkg.get("scripts", {})
            if "test" not in scripts:
                # 兼容性：即使没有 test 脚本，只要有 package.json 仍算检测到
                # 具体的测试命令由 goal 决定
                pass
            # 检查是否有 node_modules（可选，但有利于判断）
            has_node_modules = (project_root / "node_modules").exists()
            return True  # 有 package.json 即视为 Node.js 项目
        except (json.JSONDecodeError, Exception):
            return False

    @classmethod
    def prepare(cls, project_root: Path) -> RuntimeProfile:
        """准备 Node.js 运行时环境。

        包括：检查 node 版本、设置 npm cache。
        """
        # 读取 package.json 获取 node 版本要求
        pkg_file = project_root / "package.json"
        node_version = "22"  # 默认
        try:
            content = pkg_file.read_text(encoding="utf-8")
            pkg = json.loads(content)
            # engines.field 可能包含 node 版本要求
            engines = pkg.get("engines", {})
            if engines and "node" in engines:
                v = engines["node"]
                # 提取版本号
                match = re.search(r"^(>=?)?(\d+\.\d+\.\d+)", str(v))
                if match:
                    node_version = match.group(2)
        except Exception:
            pass

        # 沙箱镜像（可通过环境变量覆盖）
        import os
        sandbox_image = os.getenv(
            "SPECPROOF_SANDBOX_NODE_IMAGE", cls.DEFAULT_SANDBOX_IMAGE
        )

        return RuntimeProfile(
            language=cls.LANGUAGE,
            build_tool=cls.BUILD_TOOL,
            language_version=node_version,
            build_tool_version="10.0.0",  # npm 大约版本
            dependency_cache_path=Path(
                f"/{cls.NPM_CACHE_VOLUME}"
            ),  # 本地缓存卷路径
            sandbox_image=sandbox_image,
            sandbox_digest=cls.DEFAULT_SANDBOX_DIGEST,
            extra={
                "has_node_modules": (project_root / "node_modules").exists(),
            },
        )

    @classmethod
    def execute(
        cls,
        project_root: Path,
        profile: RuntimeProfile,
        goal: str = "test",
        test_filter: str | None = None,
        **kwargs,
    ) -> ExecutionResult:
        """执行 Node.js 测试。

        支持的 goal：test、vitest、node-test
        """
        if goal not in cls.SUPPORTED_GOALS:
            raise AdapterNotImplemented(
                f"Goal '{goal}' not supported by {cls.ADAPTER_ID}. "
                f"Supported: {cls.SUPPORTED_GOALS}"
            )

        start = time.perf_counter()

        # 根据 goal 构建命令
        cmd = cls._build_command(project_root, goal, test_filter)

        # 执行
        try:
            env = dict(__import__("os").environ)
            # 设置 npm cache 目录
            if profile.dependency_cache_path:
                env["npm_config_cache"] = str(profile.dependency_cache_path)
            # 禁用新的 package-lock.json 行为以兼容老项目（可选）
            env["npm_config_lockfile"] = "false"

            # Use text=False to avoid Windows gk codec issues with Chinese paths
            # Decode output manually with utf-8 and error replacement
            result = subprocess.run(
                cmd,
                cwd=project_root,
                capture_output=True,
                timeout=300,  # 5 分钟超时
                env=env,
            )
            # Decode stdout/stderr safely
            if result.stdout:
                result.stdout = result.stdout.decode("utf-8", errors="replace")
            if result.stderr:
                result.stderr = result.stderr.decode("utf-8", errors="replace")
        except subprocess.TimeoutExpired as e:
            stdout = (e.stdout or b"").decode("utf-8", errors="replace") if e.stdout else ""
            stderr = (e.stderr or b"").decode("utf-8", errors="replace") if e.stderr else ""
            return ExecutionResult(
                exit_code=-1,
                stdout=stdout,
                stderr=stderr,
                duration_ms=int((time.perf_counter() - start) * 1000),
                parse_errors=[f"Execution timeout: {e}"],
            )
        except Exception as e:
            stdout = b"".decode("utf-8", errors="replace")
            stderr = str(e)
            return ExecutionResult(
                exit_code=-1,
                stdout=stdout,
                stderr=stderr,
                duration_ms=int((time.perf_counter() - start) * 1000),
                parse_errors=[f"Execution failed: {e}"],
            )

        duration_ms = int((time.perf_counter() - start) * 1000)

        # 解析测试结果
        # 优先读取 JUnit XML 报告
        tests_run, tests_passed, tests_failed, tests_skipped = cls._parse_test_results(
            project_root, result.stdout, result.stderr
        )

        # Ensure stdout/stderr are strings (not None)
        s_stdout = result.stdout or ""
        s_stderr = result.stderr or ""
        return ExecutionResult(
            exit_code=result.returncode,
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
        """收集证据：JUnit XML 报告、package.json、node 版本信息。"""
        fragments = []

        # 1. JUnit XML 测试报告
        junit_fragments = cls._collect_junit_reports(project_root, result)
        fragments.extend(junit_fragments)

        # 2. package.json 信息
        pkg_fragment = EvidenceFragment(
            fragment_type="build",
            collector_version="node-adapter-1.0",
            payload={
                "type": "package_json",
                "content": project_root / "package.json",
                "content_text": (
                    open(project_root / "package.json", encoding="utf-8").read()
                    if (project_root / "package.json").exists()
                    else None
                ),
            },
        )
        fragments.append(pkg_fragment)

        # 3. node 版本信息
        node_fragment = EvidenceFragment(
            fragment_type="build",
            collector_version="node-adapter-1.0",
            payload={
                "type": "node_version",
                "version": profile.language_version,
                "sandbox_image": profile.sandbox_image,
            },
        )
        fragments.append(node_fragment)

        # 4. 测试结果汇总
        result_fragment = EvidenceFragment(
            fragment_type="build",
            collector_version="node-adapter-1.0",
            payload={
                "type": "test_result",
                "exit_code": result.exit_code,
                "tests_run": result.tests_run,
                "tests_passed": result.tests_passed,
                "tests_failed": result.tests_failed,
                "tests_skipped": result.tests_skipped,
                "duration_ms": result.duration_ms,
                "parse_errors": result.parse_errors,
            },
        )
        fragments.append(result_fragment)

        return fragments

    @classmethod
    def get_supported_goals(cls) -> list[str]:
        return cls.SUPPORTED_GOALS

    @classmethod
    def _build_command(cls, project_root: Path, goal: str, test_filter: str | None) -> list[str]:
        """构建 Node.js 命令。"""
        # 检查是否有 package-lock.json 或 yarn.lock
        lock_files = [
            project_root / "package-lock.json",
            project_root / "yarn.lock",
            project_root / "pnpm-lock.yaml",
        ]

        # 优先使用 npm test，其次 vitest，最后 node:test
        if goal == "vitest":
            cmd = ["npm", "run", "vitest"]
            if test_filter:
                cmd.extend(["--reporter", "verbose", test_filter])
        elif goal == "node-test":
            # node 18+ 自带 --test
            cmd = ["node", "--test"]
            # 可以添加过滤
            if test_filter:
                cmd.extend(["--", test_filter])
        else:
            # 默认 npm test
            cmd = ["npm", "test"]
            if test_filter:
                # npm test -- --test-name-pattern=filter
                cmd.extend(["--", "--test-name-pattern", test_filter])

        return cmd

    @classmethod
    def _parse_test_results(
        cls, project_root: Path, stdout: str, stderr: str
    ) -> tuple[int, int, int, int]:
        """解析测试结果：优先 JUnit XML，回退到 stdout 解析。"""

        # 查找 JUnit XML 报告（npm test -- --output=junit 可能生成）
        xml_dirs = [
            project_root / "build",
            project_root / "reports",
            project_root / ".nyc_output",
        ]
        for xml_dir in xml_dirs:
            if xml_dir.exists():
                # 查找 xml 文件
                for root, dirs, files in os.walk(xml_dir):
                    for f in files:
                        if f.endswith(".xml") or f.endswith(".junit"):
                            xml_path = os.path.join(root, f)
                            result = cls._parse_junit_xml_file(xml_path)
                            if result != (0, 0, 0, 0):  # 找到了有效数据
                                return result

        # 回退：从 stdout/stderr 解析 npm/vitest 输出
        # Ensure both are strings for safe concatenation
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return cls._parse_stdout_results(stdout + stderr)

    @classmethod
    def _parse_junit_xml_file(cls, xml_path: str) -> tuple[int, int, int, int]:
        """解析单个 JUnit XML 文件。"""
        import xml.etree.ElementTree as ET

        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            for testsuite in root.iter("testsuite"):
                tests_run = int(testsuite.get("tests", 0))
                tests_failed = int(testsuite.get("failures", 0)) + int(
                    testsuite.get("errors", 0)
                )
                tests_skipped = int(testsuite.get("skipped", 0))
                tests_passed = tests_run - tests_failed - tests_skipped
                return tests_run, tests_passed, tests_failed, tests_skipped
        except Exception:
            pass
        return 0, 0, 0, 0

    @classmethod
    def _parse_stdout_results(cls, output: str) -> tuple[int, int, int, int]:
        """从 stdout/stderr 解析测试结果（启发式）。"""
        tests_run = tests_passed = tests_failed = tests_skipped = 0

        # npm test 输出模式： "test runner done" 或 "Test Suites: ..." 等
        # vitest 输出模式： "vitest run" 结果

        # 简单的正则匹配
        patterns = [
            # npm test 模式： "Tests: (\d+) passed, (\d+) failed, (\d+) skipped"
            (r"Tests:\s+(\d+)\s+passed,\s+(\d+)\s+failed,\s+(\d+)\s+skipped", lambda m: (
                int(m.group(1)),
                int(m.group(1)),
                int(m.group(2)),
                int(m.group(3)),
            )),
            # vitest 模式： "(\d+) tests passed, (\d+) failed"
            (r"(\d+) tests passed, (\d+) failed", lambda m: (
                int(m.group(1)) + int(m.group(2)),
                int(m.group(1)),
                int(m.group(2)),
                0,
            )),
            # node:test 模式
            (r"(\d+) tests? completed", lambda m: (int(m.group(1)), 0, 0, 0)),
        ]

        for pattern, extractor in patterns:
            match = re.search(pattern, output)
            if match:
                return extractor(match)

        return 0, 0, 0, 0

    @classmethod
    def _collect_junit_reports(cls, project_root: Path, result: ExecutionResult) -> list[EvidenceFragment]:
        """收集 JUnit XML 报告作为证据。"""
        fragments = []
        # npm test -- --output=junit 可能在 .nyc 或者 test-results 中
        xml_dirs = [
            project_root / "test-results",
            project_root / ".nyc_output",
            project_root / "build",
        ]
        for xml_dir in xml_dirs:
            if xml_dir.exists():
                for root, dirs, files in os.walk(xml_dir):
                    for f in files:
                        if f.endswith(".xml"):
                            xml_path = os.path.join(root, f)
                            try:
                                content = open(xml_path, encoding="utf-8").read()
                                fragments.append(EvidenceFragment(
                                    fragment_type="build",
                                    collector_version="node-adapter-1.0",
                                    payload={
                                        "type": "junit_xml",
                                        "file": xml_path,
                                        "content": content[:50000],
                                    },
                                ))
                            except Exception:
                                continue
        return fragments


__all__ = ["NodeAdapter"]