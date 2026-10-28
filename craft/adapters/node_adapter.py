"""Node.js 适配器 (Phase 4)。

支持：Node.js 项目在 Docker 沙箱中执行测试。
目标：npm test、vitest、node:test。
输出：统一的 RuntimeProfile、ExecutionResult、EvidenceFragment。
"""

from __future__ import annotations

import json
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
from sandbox.runner import child_output_text


def _read_text_or_none(path: Path | str) -> str | None:
    """Read a file as UTF-8, or ``None`` when it cannot be read as text.

    Covers absent, unreadable (permissions, a directory where a file was
    expected) and not-UTF-8 with one answer. Evidence collection wants exactly
    that: a `package.json` that cannot be decoded is "no content to show", not a
    reason to abort the whole evidence bundle.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError):
        return None


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
        """检测是否为 Node.js 项目。

        有 `package.json` 即算 Node.js 项目，**不要求** `scripts.test`：具体跑什么由
        goal 决定（`vitest` / `node-test` 都不需要 npm script）。这里只验证
        `package.json` 是能解析的 JSON —— 一个坏掉的 package.json 不该被认成
        Node 项目然后让下游在 `npm` 上失败。
        """
        pkg_file = project_root / "package.json"
        if not pkg_file.exists():
            return False
        try:
            json.loads(pkg_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return False
        return True

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
        except Exception:  # noqa: BLE001 — a malformed engines field leaves the default node version
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
        **kwargs: Any,
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
            env = dict(os.environ)
            # 设置 npm cache 目录
            if profile.dependency_cache_path:
                env["npm_config_cache"] = str(profile.dependency_cache_path)
            # 禁用新的 package-lock.json 行为以兼容老项目（可选）
            env["npm_config_lockfile"] = "false"

            # text=False on purpose: an unpinned text=True read decodes with the
            # host's preferred codec (cp936 on this machine), and a child that
            # emits UTF-8 then reads back as nothing at all. The bytes are
            # decoded below as UTF-8 with replacement instead — the same rule
            # `sandbox.runner.child_output_text` states for both planes.
            completed = subprocess.run(
                cmd,
                cwd=project_root,
                capture_output=True,
                timeout=300,  # 5 分钟超时
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
        # 优先读取 JUnit XML 报告
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
        """收集证据：JUnit XML 报告、package.json、node 版本信息。"""
        fragments = []

        # 1. JUnit XML 测试报告
        junit_fragments = cls._collect_junit_reports(project_root, result)
        fragments.extend(junit_fragments)

        # 2. package.json 信息
        pkg_path = project_root / "package.json"
        pkg_fragment = EvidenceFragment(
            fragment_type="build",
            collector_version="node-adapter-1.0",
            payload={
                "type": "package_json",
                "content": pkg_path,
                "content_text": _read_text_or_none(pkg_path),
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
                for root, _dirs, files in os.walk(xml_dir):
                    for f in files:
                        if f.endswith(".xml") or f.endswith(".junit"):
                            xml_path = os.path.join(root, f)
                            result = cls._parse_junit_xml_file(xml_path)
                            # `None` = no report parsed; (0, 0, 0, 0) = a
                            # report parsed and it says zero tests. Only the
                            # first may fall through (#510).
                            if result is not None:
                                return result

        # 回退：从 stdout/stderr 解析 npm/vitest 输出
        return cls._parse_stdout_results(stdout + stderr)

    @classmethod
    def _parse_junit_xml_file(cls, xml_path: str) -> tuple[int, int, int, int] | None:
        """解析单个 JUnit XML 文件；读不动时返回 None（不是全 0）。"""
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
        except Exception:  # noqa: BLE001 — an unreadable report yields no counts; the verdict stays exit_code
            pass
        return None

    @classmethod
    def _parse_stdout_results(cls, output: str) -> tuple[int, int, int, int]:
        """从 stdout/stderr 解析测试结果（启发式）。"""
        # npm test 输出模式： "test runner done" 或 "Test Suites: ..." 等
        # vitest 输出模式： "vitest run" 结果

        # 简单的正则匹配
        patterns: list[tuple[str, Callable[[re.Match[str]], tuple[int, int, int, int]]]] = [
            # npm test 模式： "Tests: (\d+) passed, (\d+) failed, (\d+) skipped"
            # run = passed + failed + skipped。旧版这里把 run 报成 passed，
            # 于是任何有失败或跳过的运行都会少算 tests_run（vitest 那条一直是对的）。
            (r"Tests:\s+(\d+)\s+passed,\s+(\d+)\s+failed,\s+(\d+)\s+skipped", lambda m: (
                int(m.group(1)) + int(m.group(2)) + int(m.group(3)),
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
    def _collect_junit_reports(
        cls, project_root: Path, result: ExecutionResult
    ) -> list[EvidenceFragment]:
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
                for root, _dirs, files in os.walk(xml_dir):
                    for f in files:
                        if not f.endswith(".xml"):
                            continue
                        xml_path = os.path.join(root, f)
                        content = _read_text_or_none(xml_path)
                        if content is None:
                            continue
                        fragments.append(EvidenceFragment(
                            fragment_type="build",
                            collector_version="node-adapter-1.0",
                            payload={
                                "type": "junit_xml",
                                "file": xml_path,
                                "content": content[:50000],
                            },
                        ))
        return fragments


__all__ = ["NodeAdapter"]
