"""Backlog #7 攻击测试 1: 恶意构建脚本 (离线; 假 runner / 本地模式 tmp 目录).

Threat: a malicious PR's build command tries to rewrite files outside the
workspace, delete critical files, or overwrite mvnw — sabotaging the
verification pipeline or planting backdoors for later steps.

Defense layers under test (each asserted at its honest boundary):

1. Executor command whitelist (craft.executor): non-whitelisted script
   stems (sh/bash/cmd/mvnw/...) are denied BEFORE anything reaches the
   sandbox — the fake runner below fails the test if any command arrives.
2. Docker sandbox argv (sandbox.runner): the workspace is mounted
   read-only with ONLY target/ writable, and every escalation/exfil
   channel (root, caps, network) is closed — so a build-time write to
   mvnw or to any path outside /work is denied by the mount layer itself.
3. Honest degradation (sandbox.runner): mode=docker never falls back to
   unsandboxed execution; mode=auto falls back to local only with
   mode=local_fallback recorded AND the docker failure reason preserved.

Pinned gap (annotated): in explicit local mode (development-only;
production pins SPECPROOF_SANDBOX=docker — asserted against
compose.production.yml) a whitelisted interpreter CAN smuggle file
tampering. The real tmp-dir runs below pin that behaviour so nobody
mistakes local mode for a sandbox.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

import sandbox.runner as runner
from craft.executor import CommandNotAllowedError, Executor
from sandbox.runner import SandboxResult, run_sandboxed

_TAMPER_SCRIPT = (
    "import pathlib, sys; "
    "pathlib.Path(sys.argv[1]).write_text('owned-by-build', encoding='utf-8')"
)
_DELETE_SCRIPT = "import pathlib, sys; pathlib.Path(sys.argv[1]).unlink()"


class _FakeCompleted:
    returncode = 0
    stdout = "ok"
    stderr = ""


def _refuse_executor_sandbox(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Fake sandbox for the executor: fails the test if a command reaches it."""
    calls: list[list[str]] = []

    def fake_run_sandboxed(
        command: list[str],
        workspace: str,
        timeout: int,
        mode: str | None = None,
        local_command: list[str] | None = None,
    ) -> SandboxResult:
        calls.append(command)
        raise AssertionError("命令不应到达沙箱: 白名单必须先行拦截")

    monkeypatch.setattr("craft.executor.run_sandboxed", fake_run_sandboxed)
    return calls


def _capture_runner_subprocess(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> _FakeCompleted:
        calls.append(cmd)
        return _FakeCompleted()

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setattr(runner, "_image_ready", lambda _image: True)
    monkeypatch.setattr(runner, "_ensure_writable_target", lambda _ws: "")
    return calls


# ══════════════════════════════════════════════════════════════════
# 层 1: 白名单 — 篡改脚本命令在执行前被拒 (假 runner 证明零到达)
# ══════════════════════════════════════════════════════════════════

class TestWhitelistDeniesTamperingScripts:
    @pytest.mark.parametrize(
        "stem",
        ["sh", "bash", "cmd", "powershell", "mvnw", "evil-build"],
    )
    def test_tampering_script_stem_denied_before_sandbox(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        stem: str,
    ) -> None:
        """A build command smuggled through a non-whitelisted shell/script
        stem (rm -rf / cp / overwrite mvnw ...) must never reach the
        sandbox: default-deny at the whitelist is the first gate."""
        calls = _refuse_executor_sandbox(monkeypatch)
        executor = Executor(tmp_path)
        with pytest.raises(CommandNotAllowedError, match="不在白名单"):
            executor.run([stem, "-c", "overwrite mvnw via " + stem])
        assert calls == []


# ══════════════════════════════════════════════════════════════════
# 层 2: Docker argv — 工作区只读, 仅 target 可写; 无提权/外传通道
# ══════════════════════════════════════════════════════════════════

class TestDockerArgvDeniesWorkspaceTampering:
    def test_workspace_mounted_readonly_except_target(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Every host path under the workspace must be mounted read-only,
        EXCEPT the target/ sub-mount. A build-time attempt to overwrite
        mvnw or write outside /work is denied by this mount layout."""
        calls = _capture_runner_subprocess(monkeypatch)
        workspace = tmp_path / "ws"
        result = run_sandboxed(["mvn", "-o", "test-compile"], str(workspace), mode="docker")
        assert result.mode == "docker"
        assert len(calls) == 1
        cmd = calls[0]
        assert f"{workspace}:/work:ro" in cmd, "workspace root must be read-only"
        assert f"{workspace}/target:/work/target" in cmd, (
            "target/ must be the only writable sub-mount"
        )
        assert not any(f"{workspace}/mvnw" in arg for arg in cmd), (
            "mvnw must never be separately (rw-)mounted"
        )
        mounts = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-v"]
        allowed = {f"{workspace}:/work:ro", f"{workspace}/target:/work/target"}
        for spec in mounts:
            if spec in allowed:
                continue
            assert not spec.startswith(str(workspace)), (
                f"no other writable host path under the workspace: {spec}"
            )

    def test_no_privilege_escalation_or_exfil_channels(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A tampering build that survives the read-only mount still cannot
        escalate (root/caps blocked) or exfiltrate (network none, no socket)."""
        calls = _capture_runner_subprocess(monkeypatch)
        run_sandboxed(["mvn", "-o", "test-compile"], str(tmp_path / "ws"), mode="docker")
        assert len(calls) == 1
        cmd = calls[0]
        assert cmd[cmd.index("--user") + 1] == "1000:1000"
        assert "--network" in cmd and "none" in cmd
        assert "--cap-drop" in cmd and "ALL" in cmd
        assert "--security-opt" in cmd and "no-new-privileges" in cmd
        assert not any("docker.sock" in arg for arg in cmd)


# ══════════════════════════════════════════════════════════════════
# 层 3: 诚实降级 — docker 模式绝不落回无沙箱执行; auto 落回必须留痕
# ══════════════════════════════════════════════════════════════════

class TestDockerModeNeverRunsUnsandboxed:
    def test_docker_mode_with_dead_daemon_hard_errors_no_local_exec(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: Any) -> _FakeCompleted:
            calls.append(cmd)
            raise OSError("docker daemon down")

        monkeypatch.setattr(runner.subprocess, "run", fake_run)
        monkeypatch.setattr(runner, "_image_ready", lambda _image: False)
        result = run_sandboxed(
            ["mvn", "-o", "test-compile"],
            str(tmp_path / "ws"),
            mode="docker",
            local_command=["marker-command", "--never-executed"],
        )
        assert result.exit_code == -1
        assert result.mode == "docker"
        assert "docker daemon down" in result.error
        assert not any("marker-command" in arg for arg in calls)

    def test_auto_mode_without_docker_records_local_fallback(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls = _capture_runner_subprocess(monkeypatch)
        monkeypatch.setattr(runner, "_docker_available", lambda: False)
        result = run_sandboxed(
            ["mvn", "-o", "test-compile"],
            str(tmp_path / "ws"),
            mode="auto",
            local_command=["fake-mvn", "-o", "test-compile"],
        )
        assert result.mode == "local_fallback"
        assert result.exit_code == 0
        assert any(cmd[0] == "fake-mvn" for cmd in calls)

    def test_auto_mode_docker_error_reason_preserved_in_fallback(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When docker exists but the sandbox run fails, the fallback must
        record BOTH the degradation (mode=local_fallback) AND the reason —
        a silent degradation would hide a broken sandbox from the audit."""
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: Any) -> _FakeCompleted:
            calls.append(cmd)
            if len(calls) == 1:
                raise OSError("docker run exploded")
            return _FakeCompleted()

        monkeypatch.setattr(runner.subprocess, "run", fake_run)
        monkeypatch.setattr(runner, "_docker_available", lambda: True)
        monkeypatch.setattr(runner, "_image_ready", lambda _image: True)
        monkeypatch.setattr(runner, "_ensure_writable_target", lambda _ws: "")
        result = run_sandboxed(
            ["mvn", "-o", "test-compile"],
            str(tmp_path / "ws"),
            mode="auto",
            local_command=["fake-mvn", "-o", "test-compile"],
        )
        assert result.mode == "local_fallback"
        assert result.exit_code == 0
        assert "local_fallback" in result.error
        assert "docker run exploded" in result.error


# ══════════════════════════════════════════════════════════════════
# 层 4: 钉住的缺口 — 显式 local 模式对篡改无隔离 (真实 tmp 运行)
# ══════════════════════════════════════════════════════════════════

class TestLocalModeTamperingGapPinned:
    """LOCAL-MODE TAMPERING GAP (annotated, design 退化策略):

    explicit local mode (and the auto fallback) executes the command on
    the host with NO isolation — a whitelisted interpreter therefore CAN
    overwrite mvnw, write outside the workspace and delete critical files.
    These tests pin TODAY's behaviour with real tmp-dir runs. The
    mitigating facts (also pinned): production sets SPECPROOF_SANDBOX=
    docker (TestProductionPinsDockerMode) and every local run reports its
    mode honestly. A future hardening (e.g. refusing local mode for
    untrusted content) must flip these tests to assert rejection.
    """

    def _setup_workspace(self, tmp_path: Path) -> tuple[Path, Path]:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        mvnw_text = '#!/bin/sh' + chr(10) + 'mvn "$@"' + chr(10)
        (workspace / "mvnw").write_text(mvnw_text, encoding="utf-8")
        (workspace / "critical.txt").write_text("do-not-touch", encoding="utf-8")
        outside = tmp_path / "outside"
        outside.mkdir()
        return workspace, outside

    def test_local_mode_can_overwrite_mvnw(self, tmp_path: Path) -> None:
        workspace, _outside = self._setup_workspace(tmp_path)
        mvnw = workspace / "mvnw"
        result = Executor(workspace, mode="local").run(
            ["python", "-c", _TAMPER_SCRIPT, str(mvnw)]
        )
        assert result.exit_code == 0
        assert result.mode == "local"
        assert mvnw.read_text(encoding="utf-8") == "owned-by-build"

    def test_local_mode_can_write_outside_workspace(self, tmp_path: Path) -> None:
        workspace, outside = self._setup_workspace(tmp_path)
        target = outside / "owned.txt"
        result = Executor(workspace, mode="local").run(
            ["python", "-c", _TAMPER_SCRIPT, str(target)]
        )
        assert result.exit_code == 0
        assert result.mode == "local"
        assert target.read_text(encoding="utf-8") == "owned-by-build"

    def test_local_mode_can_delete_critical_file(self, tmp_path: Path) -> None:
        workspace, _outside = self._setup_workspace(tmp_path)
        critical = workspace / "critical.txt"
        result = Executor(workspace, mode="local").run(
            ["python", "-c", _DELETE_SCRIPT, str(critical)]
        )
        assert result.exit_code == 0
        assert result.mode == "local"
        assert not critical.exists()


# ══════════════════════════════════════════════════════════════════
# 生产配置: 沙箱模式必须钉死在 docker, local 只能显式用于开发
# ══════════════════════════════════════════════════════════════════

class TestProductionPinsDockerMode:
    def test_production_worker_pins_docker_sandbox_mode(self) -> None:
        compose_path = Path(__file__).resolve().parents[2] / "compose.production.yml"
        with open(compose_path, encoding="utf-8") as f:
            compose = yaml.safe_load(f)
        worker = compose["services"]["worker"]
        assert worker["environment"]["SPECPROOF_SANDBOX"] == "docker", (
            "production must never degrade to unsandboxed local execution"
        )
