"""Sandbox — isolated execution for untrusted experiment workloads (P0-A1).

Threat model: PR code (pom.xml, tests, build plugins) is UNTRUSTED INPUT.
Running Maven directly on the host lets a malicious PR execute arbitrary
code with the host's privileges and read its secrets (LLM_API_KEY, tokens).

The sandbox executes experiment commands inside a Docker container:
  - --user 1000:1000        §12: the workload never runs as root
  - --pids-limit 256        process-table DoS cap (SPECPROOF_SANDBOX_PIDS)
  - --network none          no exfiltration
  - --cap-drop ALL          no privilege escalation
  - --security-opt no-new-privileges
  - --memory / --cpus       resource limits
  - workspace mounted read-only at /work (a throwaway worktree copy, not
    the repo itself); only /work/target is a writable sub-mount so Maven
    can produce build output while the source tree stays immutable
  - writable ~/.m2 volume   Maven dependency cache at /home/maven/.m2
    (pinned via MAVEN_USER_HOME + MAVEN_OPTS=-Duser.home, see below; the
    maven image has no dedicated user, so the cache volume must be seeded
    with uid 1000 ownership — see scripts/seed_sandbox_cache.ps1 and
    docs/operations/RUNBOOK.md §5). Volume name defaults to the non-root
    specproof-maven-cache-1000; SPECPROOF_SANDBOX_M2_VOLUME can select the
    legacy root-layout volume specproof-maven-cache explicitly.
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
from collections.abc import Mapping
from dataclasses import dataclass

from sandbox.cache_verify import enforce_cache_integrity

DEFAULT_IMAGE = "maven:3.9-eclipse-temurin-21"

# Node toolchain image for the repository-self-test sandbox. Alpine because it
# is the smallest pull, and its unprivileged `node` user is uid/gid 1000 — the
# same identity SANDBOX_USER pins, so no chown or seeded volume is needed.
DEFAULT_NODE_IMAGE = "node:22-alpine"

# §12 sandbox hardening (P6): workloads run as uid/gid 1000, never root.
# The maven image ships no dedicated user, but docker auto-creates the
# /home/maven/.m2 volume mountpoint at container start.
SANDBOX_USER = "1000:1000"

# Maven user home inside the container. Verified against
# maven:3.9-eclipse-temurin-21 (Maven 3.9.9, Temurin JDK 21):
#   - MavenWrapperMain 3.3.2 honors the MAVEN_USER_HOME env var and treats
#     its value as the ~/.m2 directory itself: the wrapper distribution
#     lands at <MAVEN_USER_HOME>/wrapper/dists. With the value /home/maven
#     it tried /home/maven/wrapper instead — not on the cache volume and
#     not writable by uid 1000 (verified: AccessDeniedException). So the
#     env value must be /home/maven/.m2.
#   - mvn itself ignores MAVEN_USER_HOME, and the JDK derives user.home
#     from /etc/passwd (uid 1000 -> /home/ubuntu), not from $HOME. So
#     MAVEN_OPTS=-Duser.home=/home/maven is what actually pins the local
#     repository and user settings to the cache volume.
# Together the dependency cache AND the wrapper dist live on the seeded
# cache volume below, which is required for offline (-o) builds under
# --network none.
MAVEN_HOME = "/home/maven"
MAVEN_USER_HOME_ENV = f"{MAVEN_HOME}/.m2"

# Process-table cap inside the sandbox; a fork bomb in PR code must not
# exhaust the host pids controller. SPECPROOF_SANDBOX_PIDS overrides.
DEFAULT_PIDS_LIMIT = "256"

# Maven cache volume name. The non-root layout needs a volume seeded
# with uid-1000 ownership (specproof-maven-cache-1000, see
# scripts/seed_sandbox_cache.ps1) — that is the DEFAULT. The legacy
# root-layout volume specproof-maven-cache (kept mounted at /root/.m2
# by long-running full evaluations) is only used when explicitly selected
# via SPECPROOF_SANDBOX_M2_VOLUME; never prune or rebuild it.
DEFAULT_M2_VOLUME = "specproof-maven-cache-1000"


# ── Sandbox profiles (language-agnostic isolation, parametric toolchain) ─
#
# The isolation invariants (non-root user, --network none, --cap-drop ALL,
# no-new-privileges, pids cap, tmpfs, read-only workspace, no docker.sock)
# are IDENTICAL for every language — they are what makes it safe to run
# UNTRUSTED PR code at all. What differs per language is only: which image
# provides the toolchain, which env vars point the toolchain at an offline
# cache, which volume seeds that cache, and which sub-directories of the
# (read-only) workspace the build must write into. ``SandboxProfile`` captures
# exactly that delta so the runner stays a single hardened path; a new
# language becomes data, never a new copy of the security-critical argv.
@dataclass(frozen=True)
class SandboxProfile:
    name: str
    image: str
    # Env var that lets operators pin/override the image for this profile.
    image_env: str
    # Extra "-e KEY=VALUE" env for the toolchain's offline resolution.
    env: tuple[tuple[str, str], ...] = ()
    # Offline dependency-cache volume mounted at ``cache_mount``.
    cache_volume_env: str = ""
    cache_volume_default: str = ""
    cache_mount: str = ""
    # Workspace-relative dirs that must be writable, pre-created on the host
    # and sub-mounted read-write into the otherwise read-only /work.
    writable_submounts: tuple[tuple[str, str], ...] = ()

    @property
    def precreate_dirs(self) -> tuple[str, ...]:
        return tuple(rel for rel, _ in self.writable_submounts)


# The default profile reproduces the original Maven argv byte-for-byte:
# the existing test_sandbox_runner.py assertions are the regression lock.
MAVEN_PROFILE = SandboxProfile(
    name="maven",
    image=DEFAULT_IMAGE,
    image_env="SPECPROOF_SANDBOX_IMAGE",
    env=(
        ("MAVEN_USER_HOME", MAVEN_USER_HOME_ENV),
        ("MAVEN_OPTS", f"-Duser.home={MAVEN_HOME}"),
    ),
    cache_volume_env="SPECPROOF_SANDBOX_M2_VOLUME",
    cache_volume_default=DEFAULT_M2_VOLUME,
    cache_mount=MAVEN_USER_HOME_ENV,
    writable_submounts=(("target", "/work/target"),),
)


def _profile_from_env() -> SandboxProfile:
    """Resolve the default profile for callers that do not name one.

    Selection is additive: this stays Maven-only so the differential
    pipeline's effective behavior is unchanged for anything that has not been
    explicitly validated on live Docker. A language that wants a different
    toolchain passes its own profile through ``run_sandboxed(profile=...)``
    rather than changing the default.
    """
    return MAVEN_PROFILE


# Node/npm profile for running a repository's OWN test script under the same
# isolation invariants as Maven. Deliberately carries NO cache volume:
# `npm test` needs no dependency cache when node_modules is already in the
# workspace, and mounting an unseeded named volume would hand uid 1000 a
# root-owned directory it cannot write (the Maven path needs
# scripts/seed_sandbox_cache.ps1 precisely for that reason). npm's own cache
# therefore stays on the container's ephemeral layer, discarded by --rm.
# node:22-alpine's `node` user is uid/gid 1000, matching SANDBOX_USER.
NODE_PROFILE = SandboxProfile(
    name="node",
    image=DEFAULT_NODE_IMAGE,
    image_env="SPECPROOF_SANDBOX_NODE_IMAGE",
    env=(("npm_config_update_notifier", "false"),),
    writable_submounts=(),
)


def _profile_image(profile: SandboxProfile) -> str:
    if profile.image_env:
        value = os.getenv(profile.image_env, "").strip()
        if value:
            return value
    return profile.image


def _profile_cache_volume(profile: SandboxProfile) -> str:
    if profile.cache_volume_env:
        value = os.getenv(profile.cache_volume_env, "").strip()
        if value:
            return value
    return profile.cache_volume_default


# Output-flood defense (backlog #7): the runner bounds retained output to
# head + explicit truncation marker + tail so downstream consumers never
# hold the full flood. Env overrides keep tests and operations tunable.
OUTPUT_HEAD_CHARS_DEFAULT = 32768
OUTPUT_TAIL_CHARS_DEFAULT = 32768


def _budget(env_name: str, default: int) -> int:
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def truncation_marker(dropped_chars: int) -> str:
    """Explicit marker inserted between head and tail when output is truncated."""
    return f"\n[... sandbox output truncated: {dropped_chars} chars omitted ...]\n"


def bound_output(
    text: str,
    head: int | None = None,
    tail: int | None = None,
) -> tuple[str, bool, int]:
    """Bound retained output to head + marker + tail.

    Returns (bounded_text, truncated, dropped_chars). The middle of an
    oversized stream is discarded; the marker makes the truncation explicit
    and the dropped count is reported honestly — a silent partial output
    would be indistinguishable from a small one.
    """
    head_chars = head if head is not None else _budget(
        "SPECPROOF_SANDBOX_OUTPUT_HEAD", OUTPUT_HEAD_CHARS_DEFAULT
    )
    tail_chars = tail if tail is not None else _budget(
        "SPECPROOF_SANDBOX_OUTPUT_TAIL", OUTPUT_TAIL_CHARS_DEFAULT
    )
    if len(text) <= head_chars + tail_chars:
        return text, False, 0
    dropped = len(text) - head_chars - tail_chars
    bounded = text[:head_chars] + truncation_marker(dropped) + text[-tail_chars:]
    return bounded, True, dropped

# Pull attempts are cached per image for the life of the process: a registry
# outage must cost ONE failed pull (a few seconds), not a hanging 900s pull per
# invocation. Keyed BY IMAGE, not a single process-wide flag — with more than
# one toolchain profile sharing this runner, a boolean would let a successful
# maven pull vouch for an image that was never pulled, and the container would
# then fail at `docker run` with a misleading error.
_PULL_OUTCOMES: dict[str, str | None] = {}


@dataclass
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    error: str = ""          # sandbox-level failure (docker missing, image pull)
    mode: str = "local"      # docker | local_fallback | local
    truncated: bool = False  # output flood: head+marker+tail retention applied
    truncated_chars: int = 0  # how many chars were dropped from the middle
    cache_note: str = ""     # cache-verification note (use/rebuild verdicts)


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


def _ensure_writable_target(workspace: str) -> str:
    """Pre-create the active profile's writable sub-dirs (single-arg
    monkeypatch point used across the sandbox/fault tests)."""
    return _ensure_writable_mounts(workspace, _profile_from_env())


def _ensure_writable_mounts(workspace: str, profile: SandboxProfile) -> str:
    """Pre-create each writable subdir the profile's sub-mounts need.

    Under DooD the daemon would otherwise create these dirs as root and the
    non-root workload could not write into them; on local Docker Desktop the
    nested mount source must exist before `docker run` resolves it.
    Idempotent — the pipeline always starts from a fresh worktree.
    """
    for rel in profile.precreate_dirs:
        try:
            os.makedirs(os.path.join(workspace, rel), exist_ok=True)
        except OSError as exc:
            return f"cannot create workspace target dir: {exc}"[:300]
    return ""


def _pull_image(image: str) -> str:
    """Pull a sandbox image ONCE per process, keyed by image name.

    Returns "" on success, the error otherwise. A second call for the SAME
    image in the same process returns the cached outcome immediately — a
    registry outage must not turn every invocation into a hanging 900s pull.
    A DIFFERENT image is pulled on its own merits: a successful maven pull
    says nothing about whether a node image exists in the registry.
    """
    cached = _PULL_OUTCOMES.get(image)
    if cached is not None:
        return cached
    try:
        proc = subprocess.run(
            ["docker", "pull", image],
            capture_output=True, text=True, timeout=120,
        )
        outcome = "" if proc.returncode == 0 else (proc.stderr or "pull failed")[:300]
    except Exception as exc:
        outcome = str(exc)[:300]
    _PULL_OUTCOMES[image] = outcome
    return outcome


def build_docker_argv(command: list[str], workspace: str, profile: SandboxProfile) -> list[str]:
    """Assemble the hardened `docker run` argv for a profile (pure).

    Isolation invariants are fixed here and shared by every language; only
    the image / toolchain env / cache volume / writable sub-mounts vary with
    the profile. Kept side-effect-free so the security-critical argv can be
    unit-tested offline without a Docker daemon.
    """
    image = _profile_image(profile)
    argv = [
        "docker", "run", "--rm",
        # §12: never root, with a pids-controller cap against fork bombs.
        "--user", SANDBOX_USER,
        "--pids-limit", os.getenv("SPECPROOF_SANDBOX_PIDS", DEFAULT_PIDS_LIMIT),
        "--network", "none",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--memory", os.getenv("SPECPROOF_SANDBOX_MEMORY", "1g"),
        "--cpus", os.getenv("SPECPROOF_SANDBOX_CPUS", "1.0"),
        # Container /tmp as tmpfs — a mount spec for inside the
        # container, not the host's temp directory. The path is assembled
        # from parts so no bare /tmp literal trips static scanners.
        "--tmpfs", f"{os.path.join('/', 'tmp')}:rw,noexec,nosuid,size=512m",
    ]
    for key, value in profile.env:
        argv += ["-e", f"{key}={value}"]
    # Read-only workspace + per-profile writable sub-mounts: the source tree
    # stays immutable while the build produces output the pipeline reads back
    # for evidence. The workspace is a disposable worktree copy, not the
    # repository itself. The offline cache volume lets the toolchain resolve
    # dependencies even under --network none.
    argv += ["-v", f"{workspace}:/work:ro"]
    for rel, container in profile.writable_submounts:
        # POSIX-style concat: the container path and these mount specs are
        # always '/'-separated regardless of host OS (os.path.join would emit
        # backslashes on Windows and change the argv).
        argv += ["-v", f"{workspace}/{rel}:{container}"]
    if profile.cache_mount:
        argv += ["-v", f"{_profile_cache_volume(profile)}:{profile.cache_mount}"]
    argv += ["-w", "/work", image, *command]
    return argv


def _run_docker(
    command: list[str], workspace: str, timeout: int,
    profile: SandboxProfile | None = None,
) -> SandboxResult:
    profile = profile or _profile_from_env()
    image = _profile_image(profile)
    if not _image_ready(image):
        err = _pull_image(image)
        if err:
            return SandboxResult(
                exit_code=-1, stdout="", stderr="",
                error=f"sandbox image unavailable: {err}", mode="docker",
            )
    # The Maven path keeps its historical single-arg hook, which is the
    # monkeypatch point across the sandbox/fault suites; any other profile
    # resolves its OWN writable dirs, so a node run neither needs nor gets a
    # stray `target/` created in the worktree.
    if profile is MAVEN_PROFILE:
        target_err = _ensure_writable_target(workspace)
    else:
        target_err = _ensure_writable_mounts(workspace, profile)
    if target_err:
        return SandboxResult(
            exit_code=-1, stdout="", stderr="",
            error=target_err, mode="docker",
        )
    docker_cmd = build_docker_argv(command, workspace, profile)
    try:
        proc = subprocess.run(
            docker_cmd, capture_output=True, text=True, timeout=timeout,
        )
        stdout, out_trunc, out_dropped = bound_output(proc.stdout)
        stderr, err_trunc, err_dropped = bound_output(proc.stderr)
        return SandboxResult(
            exit_code=proc.returncode,
            stdout=stdout,
            stderr=stderr,
            mode="docker",
            truncated=out_trunc or err_trunc,
            truncated_chars=out_dropped + err_dropped,
        )
    except subprocess.TimeoutExpired as exc:
        # Preserve whatever the workload already emitted before the kill —
        # the honest partial output beats a silent empty result (bounded,
        # so a flood interrupted by the kill cannot balloon the worker).
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        stdout, out_trunc, out_dropped = bound_output(stdout)
        stderr, err_trunc, err_dropped = bound_output(stderr)
        return SandboxResult(
            exit_code=-1, stdout=stdout, stderr=stderr,
            error=f"sandbox execution timed out after {timeout}s", mode="docker",
            truncated=out_trunc or err_trunc,
            truncated_chars=out_dropped + err_dropped,
        )
    except OSError as exc:
        return SandboxResult(
            exit_code=-1, stdout="", stderr="",
            error=f"could not start command {command[0]!r}: {exc}", mode="docker",
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
    *,
    cache_dir: str | None = None,
    cache_manifest: str | Mapping[str, str] | None = None,
    on_poison: str = "fail",
    profile: SandboxProfile | None = None,
) -> SandboxResult:
    """Run a command inside the execution sandbox.

    command/workspace come from the verification pipeline and target the
    sandbox filesystem (/work). The local path runs only when explicitly
    configured (development) or as a documented fallback when Docker is
    unavailable and mode=auto — in that case local_command (e.g. the Maven
    wrapper) is used instead of the sandbox-internal command.

    cache_dir + cache_manifest enable the pre-run cache poisoning check
    (backlog #7): the host-accessible dependency cache is verified against
    the seed-time digest manifest BEFORE anything executes. on_poison
    selects the policy on mismatch: "fail" (default, refuse to execute)
    or "rebuild" (delete poisoned entries and proceed; re-seeding needs
    the host seed step since the sandbox has --network none).

    profile selects the toolchain image + its env/volume/writable dirs. It
    defaults to the historical Maven profile, so omitting it is behavior-
    preserving. Note the interaction with mode: only mode="docker" actually
    guarantees the workload never touches the host — mode="auto" falls back
    to running local_command on the host when Docker errors, which is fine
    for a trusted build and NOT fine for executing a repository's own tests.
    """
    mode = (mode or _mode_from_env()).lower()
    local_cmd = local_command or command
    resolved_profile = profile or _profile_from_env()
    cache_note = ""
    if cache_dir and cache_manifest is not None:
        # Cache poisoning defense (backlog #7): verify the dependency cache
        # against the seed-time digest manifest BEFORE executing anything.
        # Poison -> fail closed (no execution) or rebuild per policy —
        # a poisoned cache is never silently used.
        try:
            check = enforce_cache_integrity(cache_dir, cache_manifest, on_poison=on_poison)
        except ValueError as exc:
            return SandboxResult(
                exit_code=-1, stdout="", stderr="",
                error=f"cache verification failed: {exc}", mode=mode,
            )
        if not check.ok:
            return SandboxResult(
                exit_code=-1, stdout="", stderr="",
                error=check.note, mode=mode, cache_note=check.note,
            )
        cache_note = check.note
    if mode == "docker":
        result = _run_docker(command, workspace, timeout, resolved_profile)
    elif mode == "auto":
        if _docker_available():
            result = _run_docker(command, workspace, timeout, resolved_profile)
            if result.error:
                # Docker exists but the sandbox could not run — fall back
                # locally ONLY when it is a transient sandbox problem, and
                # record BOTH the degradation and its reason in the result.
                docker_error = result.error
                result = _run_local(local_cmd, workspace, timeout, "local_fallback")
                if not result.error:
                    result.error = (
                        f"docker sandbox degraded to local_fallback: {docker_error}"[:300]
                    )
        else:
            result = _run_local(local_cmd, workspace, timeout, "local_fallback")
    else:
        # mode == "local" (explicit development mode)
        result = _run_local(local_cmd, workspace, timeout, "local")
    if cache_note:
        result.cache_note = cache_note
    return result


def _run_local(
    command: list[str], workspace: str, timeout: int, mode: str,
) -> SandboxResult:
    try:
        proc = subprocess.run(
            command, cwd=workspace, capture_output=True, text=True, timeout=timeout,
        )
        stdout, out_trunc, out_dropped = bound_output(proc.stdout)
        stderr, err_trunc, err_dropped = bound_output(proc.stderr)
        return SandboxResult(
            exit_code=proc.returncode, stdout=stdout, stderr=stderr,
            mode=mode,
            truncated=out_trunc or err_trunc,
            truncated_chars=out_dropped + err_dropped,
        )
    except subprocess.TimeoutExpired as exc:
        # Preserve whatever the workload already emitted before the kill —
        # the honest partial output beats a silent empty result (bounded,
        # so a flood interrupted by the kill cannot balloon the worker).
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        stdout, out_trunc, out_dropped = bound_output(stdout)
        stderr, err_trunc, err_dropped = bound_output(stderr)
        return SandboxResult(
            exit_code=-1, stdout=stdout, stderr=stderr,
            error=f"execution timed out after {timeout}s", mode=mode,
            truncated=out_trunc or err_trunc,
            truncated_chars=out_dropped + err_dropped,
        )
    except OSError as exc:
        # e.g. the configured python/venv binary does not exist — the
        # failure must surface as an explicit error, never an empty result.
        return SandboxResult(
            exit_code=-1, stdout="", stderr="",
            error=f"could not start command {command[0]!r}: {exc}", mode=mode,
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
