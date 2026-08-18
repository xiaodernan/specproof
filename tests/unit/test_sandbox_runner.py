"""P6 unit tests — sandbox runner non-root hardening (§12 compliance).

The runner builds its docker run invocation from a fixed template; these
tests mock subprocess and assert the exact hardening flags land in the
constructed command: non-root user, pids limit, Maven user home on the
seeded cache volume, and the read-only workspace mount.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

import sandbox.runner as runner


class _FakeCompleted:
    returncode = 0
    stdout = "fake stdout"
    stderr = ""


def _capture_docker_run(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> _FakeCompleted:
        calls.append(cmd)
        return _FakeCompleted()

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    # Skip the image-inspect probe and the target-dir pre-create so the
    # captured call is the docker run itself.
    monkeypatch.setattr(runner, "_image_ready", lambda _image: True)
    monkeypatch.setattr(runner, "_ensure_writable_target", lambda _ws: "")
    return calls


def _run_docker(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[runner.SandboxResult, list[str]]:
    calls = _capture_docker_run(monkeypatch)
    result = runner.run_sandboxed(
        ["mvn", "-o", "test-compile"],
        "C:/ws/specproof-base-1",
        mode="docker",
    )
    assert len(calls) == 1
    return result, calls[0]


def test_docker_run_as_non_root_user(monkeypatch: pytest.MonkeyPatch) -> None:
    _result, cmd = _run_docker(monkeypatch)
    i = cmd.index("--user")
    assert cmd[i + 1] == "1000:1000"


def test_docker_run_sets_default_pids_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    _result, cmd = _run_docker(monkeypatch)
    i = cmd.index("--pids-limit")
    assert cmd[i + 1] == "256"


def test_pids_limit_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECPROOF_SANDBOX_PIDS", "512")
    _result, cmd = _run_docker(monkeypatch)
    i = cmd.index("--pids-limit")
    assert cmd[i + 1] == "512"


def test_maven_user_home_points_at_cache_volume(monkeypatch: pytest.MonkeyPatch) -> None:
    _result, cmd = _run_docker(monkeypatch)
    assert "MAVEN_USER_HOME=/home/maven/.m2" in cmd
    assert "MAVEN_OPTS=-Duser.home=/home/maven" in cmd


def test_cache_volume_defaults_to_non_root_volume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The non-root layout is the default; the legacy root-layout volume
    # (long-running full evaluations) is only reachable via explicit env.
    monkeypatch.delenv("SPECPROOF_SANDBOX_M2_VOLUME", raising=False)
    _result, cmd = _run_docker(monkeypatch)
    assert "specproof-maven-cache-1000:/home/maven/.m2" in cmd
    assert "specproof-maven-cache:/home/maven/.m2" not in cmd


def test_cache_volume_env_override_to_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECPROOF_SANDBOX_M2_VOLUME", "specproof-maven-cache")
    _result, cmd = _run_docker(monkeypatch)
    assert "specproof-maven-cache:/home/maven/.m2" in cmd
    assert "specproof-maven-cache-1000:/home/maven/.m2" not in cmd


def test_workspace_read_only_with_writable_target_submount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _result, cmd = _run_docker(monkeypatch)
    assert "C:/ws/specproof-base-1:/work:ro" in cmd
    assert "C:/ws/specproof-base-1/target:/work/target" in cmd


def test_docker_run_keeps_network_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    _result, cmd = _run_docker(monkeypatch)
    assert "--network" in cmd and "none" in cmd
    assert "--cap-drop" in cmd and "ALL" in cmd
    assert "--security-opt" in cmd and "no-new-privileges" in cmd


def test_no_docker_socket_in_sandbox_command(monkeypatch: pytest.MonkeyPatch) -> None:
    _result, cmd = _run_docker(monkeypatch)
    assert not any("docker.sock" in arg for arg in cmd)


def test_missing_workspace_reports_sandbox_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _capture_docker_run(monkeypatch)
    monkeypatch.setattr(
        runner,
        "_ensure_writable_target",
        lambda _ws: "cannot create workspace target dir: boom",
    )
    result = runner.run_sandboxed(
        ["mvn", "-o", "test-compile"], "C:/ws/missing", mode="docker"
    )
    assert calls == [], "no docker run must be attempted"
    assert result.exit_code == -1
    assert result.mode == "docker"
    assert "cannot create workspace target dir" in result.error


def test_docker_mode_result_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    result, _cmd = _run_docker(monkeypatch)
    assert result.mode == "docker"
    assert result.exit_code == 0
    assert result.stdout == "fake stdout"


def _load_production_compose() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[2] / "compose.production.yml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_production_worker_has_no_docker_socket_mount() -> None:
    compose = _load_production_compose()
    worker = compose["services"]["worker"]
    mounts = [v for v in worker.get("volumes", []) if isinstance(v, str)]
    assert not any("docker.sock" in v for v in mounts), \
        "worker must not mount the host docker socket (§12)"


def test_production_worker_targets_sandbox_daemon_over_tcp() -> None:
    compose = _load_production_compose()
    worker = compose["services"]["worker"]
    assert worker["environment"]["DOCKER_HOST"] == "tcp://sandbox:2375"
    assert worker["environment"]["SPECPROOF_SANDBOX_M2_VOLUME"] == "specproof-maven-cache-1000"


def test_production_has_sandbox_daemon_service() -> None:
    compose = _load_production_compose()
    sandbox = compose["services"]["sandbox"]
    assert sandbox["image"].startswith("docker:"), "sandbox must run a docker image"
    assert sandbox["environment"]["DOCKER_TLS_CERTDIR"] == ""
    mounts = [v for v in sandbox.get("volumes", []) if isinstance(v, str)]
    assert any(
        "specproof-maven-cache-1000:" in v and "specproof-maven-cache:" not in v
        for v in mounts
    ), "sandbox must bridge the -1000 cache volume into the dind volume store"
    assert "specproof-maven-cache-1000" in compose.get("volumes", {})
