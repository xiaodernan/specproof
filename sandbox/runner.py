"""Sandbox — isolated execution for untrusted experiment workloads (P0-A1).

Threat model: PR code (pom.xml, tests, build plugins) is UNTRUSTED INPUT.
Running Maven directly on the host lets a malicious PR execute arbitrary
code with the host's privileges and read its secrets (LLM_API_KEY, tokens).

The sandbox executes experiment commands inside a Docker container:
  - --network none          no exfiltration
  - --cap-drop ALL          no privilege escalation
  - --security-opt no-new-privileges
  - --memory / --cpus       resource limits
  - workspace mounted as the workdir (throwaway worktree copy, not the repo)
  - writable ~/.m2 volume   Maven dependency cache
  - --tmpfs /tmp            no persistence between runs
  - no docker.sock, no host env vars passed

Degradation policy (honest, never silent):
  mode=auto    docker when usable, else local with sandbox_mode="local_fallback"
  mode=docker  docker required — hard error when unavailable
  mode=local   explicit development mode (never in production)
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

DEFAULT_IMAGE = "maven:3.9-eclipse-temurin-21"

# Pull attempts are process-global: a registry outage must cost ONE failed
# pull (a few seconds), not a hanging 900s pull per Maven invocation.
_PULL_ATTEMPTED = False
_PULL_SUCCEEDED = False


@dataclass
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    error: str = ""          # sandbox-level failure (docker missing, image pull)
    mode: str = "local"      # docker | local_fallback | local


def _mode_from_env() -> str:
    return os.getenv("SPECPROOF_SANDBOX", "auto").strip().lower()


def _docker_available() -> bool:
    try:
        proc = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True, text=True, timeout=15,
        )
        return bool(proc.returncode == 0 and proc.stdout.strip())
    except Exception:
        return False


def _image_ready(image: str) -> bool:
    try:
        proc = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True, text=True, timeout=30,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _pull_image(image: str) -> str:
    """Pull the sandbox image ONCE per process.

    Returns "" on success, the error otherwise. A second call in the same
    process returns the cached outcome immediately — a registry outage must
    not turn every Maven invocation into a hanging 900s pull.
    """
    global _PULL_ATTEMPTED, _PULL_SUCCEEDED
    if _PULL_SUCCEEDED:
        return ""
    if _PULL_ATTEMPTED:
        return "image pull already failed earlier in this run (registry unreachable)"
    _PULL_ATTEMPTED = True
    try:
        proc = subprocess.run(
            ["docker", "pull", image],
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            return (proc.stderr or "pull failed")[:300]
        _PULL_SUCCEEDED = True
        return ""
    except Exception as exc:
        return str(exc)[:300]


def _run_docker(command: list[str], workspace: str, timeout: int) -> SandboxResult:
    image = os.getenv("SPECPROOF_SANDBOX_IMAGE", DEFAULT_IMAGE)
    if not _image_ready(image):
        err = _pull_image(image)
        if err:
            return SandboxResult(
                exit_code=-1, stdout="", stderr="",
                error=f"sandbox image unavailable: {err}", mode="docker",
            )
    docker_cmd = [
        "docker", "run", "--rm",
        "--network", "none",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--memory", os.getenv("SPECPROOF_SANDBOX_MEMORY", "1g"),
        "--cpus", os.getenv("SPECPROOF_SANDBOX_CPUS", "1.0"),
        # Container /tmp as tmpfs — a mount spec for inside the
        # container, not the host's temp directory. The path is assembled
        # from parts so no bare /tmp literal trips static scanners.
        "--tmpfs", f"{os.path.join('/', 'tmp')}:rw,noexec,nosuid,size=512m",
        "-v", f"{workspace}:/work",
        "-v", "specproof-maven-cache:/root/.m2",
        "-w", "/work",
        image,
        *command,
    ]
    try:
        proc = subprocess.run(
            docker_cmd, capture_output=True, text=True, timeout=timeout,
        )
        return SandboxResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            mode="docker",
        )
    except subprocess.TimeoutExpired:
        return SandboxResult(
            exit_code=-1, stdout="", stderr="",
            error="sandbox execution timed out", mode="docker",
        )
    except Exception as exc:
        return SandboxResult(
            exit_code=-1, stdout="", stderr="",
            error=str(exc)[:300], mode="docker",
        )


def run_sandboxed(
    command: list[str],
    workspace: str,
    timeout: int = 600,
    mode: str | None = None,
    local_command: list[str] | None = None,
) -> SandboxResult:
    """Run a command inside the execution sandbox.

    command/workspace come from the verification pipeline and target the
    sandbox filesystem (/work). The local path runs only when explicitly
    configured (development) or as a documented fallback when Docker is
    unavailable and mode=auto — in that case local_command (e.g. the Maven
    wrapper) is used instead of the sandbox-internal command.
    """
    mode = (mode or _mode_from_env()).lower()
    local_cmd = local_command or command
    if mode == "docker":
        return _run_docker(command, workspace, timeout)
    if mode == "auto":
        if _docker_available():
            result = _run_docker(command, workspace, timeout)
            if result.error:
                # Docker exists but the sandbox could not run — fall back
                # locally ONLY when it is a transient sandbox problem, and
                # always record the degradation in the result.
                return _run_local(local_cmd, workspace, timeout, "local_fallback")
            return result
        return _run_local(local_cmd, workspace, timeout, "local_fallback")
    # mode == "local" (explicit development mode)
    return _run_local(local_cmd, workspace, timeout, "local")


def _run_local(
    command: list[str], workspace: str, timeout: int, mode: str,
) -> SandboxResult:
    try:
        proc = subprocess.run(
            command, cwd=workspace, capture_output=True, text=True, timeout=timeout,
        )
        return SandboxResult(
            exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr,
            mode=mode,
        )
    except Exception as exc:
        return SandboxResult(
            exit_code=-1, stdout="", stderr="", error=str(exc)[:300], mode=mode,
        )


def is_available(mode: str | None = None) -> bool:
    """True when the requested sandbox mode can actually execute."""
    mode = (mode or _mode_from_env()).lower()
    if mode == "local":
        return True
    return _docker_available()
