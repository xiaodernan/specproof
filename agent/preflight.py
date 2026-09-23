"""Environment preflight — detect the toolchain a repository actually needs,
then fail fast with actionable guidance when it is missing.

Design constraint (roadmap Phase 1.4): the checks are **language-aware**.
A Node or Python repository must never be blocked because a JDK is absent.
The previous implementation ran JDK / JAVA_HOME / Maven-wrapper / Docker
unconditionally, which is precisely why it could never be wired into the
pipeline without breaking every non-Java job — so it stayed uncalled.

Result contract
---------------
``errors``    blocking — the pipeline cannot produce real evidence.
``warnings``  non-blocking — degraded but still able to run.
``skipped``   check ids deliberately not run for this language.

Messages stay in English (the canonical transport language of this
codebase); the web layer maps them to Chinese action cards via
``apps/web/src/ui/errorHints.ts``.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LANGUAGE_UNKNOWN = "unknown"
LANGUAGE_JAVA = "java"
LANGUAGE_NODE = "node"
LANGUAGE_PYTHON = "python"
LANGUAGE_GO = "go"

# Ordered: the first language whose marker file is found wins. Java first
# because a Java repo frequently also carries a package.json (frontend app).
_LANGUAGE_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        LANGUAGE_JAVA,
        (
            "pom.xml",
            "build.gradle",
            "build.gradle.kts",
            "mvnw",
            "mvnw.cmd",
            "gradlew",
            "gradlew.bat",
        ),
    ),
    (LANGUAGE_NODE, ("package.json",)),
    (
        LANGUAGE_PYTHON,
        (
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "requirements.txt",
            "pytest.ini",
            "tox.ini",
            "Pipfile",
        ),
    ),
    (LANGUAGE_GO, ("go.mod",)),
)

# Marker sets that mean "this language is genuinely absent", so the check
# can be reported as skipped rather than silently ignored.
_CHECKS_BY_LANGUAGE: dict[str, tuple[str, ...]] = {
    LANGUAGE_JAVA: ("java", "javac", "JAVA_HOME", "maven_wrapper"),
    LANGUAGE_NODE: ("node", "node_test_script", "package_manager"),
    LANGUAGE_PYTHON: ("python", "pytest"),
    LANGUAGE_GO: ("go",),
}

# Timeout per probe. Environment probes must never be the reason a
# verification job hangs — 15s is generous for `java -version`.
PROBE_TIMEOUT_SECONDS = 15

# Exit codes used by _probe when the process could not be started at all.
EXIT_NOT_FOUND = 127
EXIT_OS_ERROR = 126
EXIT_TIMEOUT = 124


def detect_language(repo_path: str | None, app_dir: str = "") -> str:
    """Best-effort repository language detection from marker files.

    ``app_dir`` is the subdirectory that holds the build file ("" = repo
    root); both are consulted. Returns ``LANGUAGE_UNKNOWN`` when nothing
    matches — callers must treat unknown as "run universal checks only".
    """
    roots: list[Path] = []
    if repo_path:
        roots.append(Path(repo_path))
    if app_dir:
        candidate = Path(app_dir)
        if not candidate.is_absolute() and repo_path:
            candidate = Path(repo_path) / candidate
        roots.append(candidate)

    for language, markers in _LANGUAGE_MARKERS:
        for root in roots:
            try:
                if not root.is_dir():
                    continue
            except OSError:
                continue
            for marker in markers:
                if (root / marker).exists():
                    return language
    return LANGUAGE_UNKNOWN


@dataclass
class PreflightResult:
    passed: bool = True
    language: str = LANGUAGE_UNKNOWN
    checks: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Wire/database shape. Keeps the original dict-check structure so
        the web layer can render it without a second schema."""
        return {
            "passed": self.passed,
            "language": self.language,
            "checks": list(self.checks),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "skipped": list(self.skipped),
        }


def _add(
    result: PreflightResult,
    name: str,
    status: str,
    detail: str,
) -> None:
    result.checks.append({"check": name, "status": status, "detail": detail})


def _probe_variants(cmd: list[str]) -> list[list[str]]:
    """Windows PATHEXT variants for a bare command name.

    Python's subprocess does not resolve PATHEXT, so `npm` (shipped as
    npm.cmd) and `yarn`/`pnpm` are invisible without an explicit extension.
    Without this a perfectly healthy Node toolchain is reported missing —
    a false blocker is worse than no preflight at all.
    """
    program = cmd[0]
    if sys.platform != "win32":
        return [cmd]
    if Path(program).suffix:
        return [cmd]
    return [[f"{program}{ext}", *cmd[1:]] for ext in (".cmd", ".exe", ".bat", "")]


def _probe(cmd: list[str], timeout: int = PROBE_TIMEOUT_SECONDS) -> tuple[int, str]:
    """Run a probe command. Returns (exit_code, combined_output).

    Never raises: a missing binary is a normal outcome, not an exception,
    and the caller needs to turn it into actionable guidance.
    """
    last_code, last_output = EXIT_NOT_FOUND, ""
    for candidate in _probe_variants(cmd):
        try:
            proc = subprocess.run(
                candidate,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            return EXIT_TIMEOUT, f"timed out after {timeout}s"
        except OSError as exc:
            last_code, last_output = EXIT_OS_ERROR, str(exc)
            continue
        return proc.returncode, f"{proc.stdout or ''}{proc.stderr or ''}"
    return last_code, last_output


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return "unknown"


def _major_version(text: str) -> int | None:
    """Extract the leading major version from tool output like
    ``openjdk version "21.0.4"`` or ``v18.17.0``."""
    match = re.search(r"(\d+)\.(\d+)?", text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _java_executable(name: str) -> list[str]:
    """Resolve java/javac honouring JAVA_HOME when it is set."""
    java_home = os.environ.get("JAVA_HOME", "").strip()
    if java_home:
        suffix = ".exe" if sys.platform == "win32" else ""
        candidate = Path(java_home) / "bin" / f"{name}{suffix}"
        if candidate.is_file():
            return [str(candidate)]
    return [name]


# ── Universal checks ────────────────────────────────────────────────────


def _check_disk_space(result: PreflightResult) -> None:
    """Free disk space on the working drive (universal)."""
    try:
        if sys.platform == "win32":
            drive = os.path.splitdrive(os.getcwd())[0] or "C:"
        else:
            drive = "/"
        usage = shutil.disk_usage(drive)
        free_gb = usage.free / (1024**3)
    except Exception as exc:  # noqa: BLE001 - probe, never fatal
        result.warnings.append(f"Could not check disk space: {exc}")
        _add(result, "disk_space", "WARN", str(exc))
        return

    if free_gb < 1.0:
        result.errors.append(
            f"Low disk space: {free_gb:.1f} GB free on {drive}. "
            "At least 1 GB is required for dependencies and build artifacts."
        )
        _add(result, "disk_space", "FAIL", f"{free_gb:.1f} GB")
    elif free_gb < 5.0:
        result.warnings.append(f"Disk space low: {free_gb:.1f} GB free on {drive}.")
        _add(result, "disk_space", "WARN", f"{free_gb:.1f} GB")
    else:
        _add(result, "disk_space", "PASS", f"{free_gb:.1f} GB")


# ── Java checks ─────────────────────────────────────────────────────────


def _check_java(result: PreflightResult) -> None:
    code, output = _probe([*_java_executable("java"), "-version"])
    if code == EXIT_NOT_FOUND:
        result.errors.append(
            "Java not found. Install Eclipse Temurin JDK 21 from "
            "https://adoptium.net/ and set the JAVA_HOME environment variable."
        )
        _add(result, "java", "FAIL", "Not found")
        return
    if code != 0:
        result.errors.append(
            f"Java probe failed (exit {code}): {_first_line(output)}. "
            "Verify the JDK 21 installation."
        )
        _add(result, "java", "FAIL", _first_line(output))
        return

    version = _major_version(output)
    if version is None or version < 21:
        result.errors.append(
            f"JDK 21 required, found: {_first_line(output)}. "
            "Install Eclipse Temurin JDK 21: https://adoptium.net/"
        )
        _add(result, "java", "FAIL", _first_line(output))
        return
    _add(result, "java", "PASS", _first_line(output))


def _check_javac(result: PreflightResult) -> None:
    code, output = _probe([*_java_executable("javac"), "-version"])
    if code == EXIT_NOT_FOUND:
        result.errors.append(
            "javac not found — a JRE alone cannot compile the project. "
            "Install a full JDK 21 and set JAVA_HOME."
        )
        _add(result, "javac", "FAIL", "Not found")
        return
    if code != 0:
        result.warnings.append(f"javac probe failed (exit {code}): {_first_line(output)}")
        _add(result, "javac", "WARN", _first_line(output))
        return
    _add(result, "javac", "PASS", _first_line(output))


def _check_java_home(result: PreflightResult) -> None:
    """JAVA_HOME is advisory, not mandatory: many build scripts need it, but
    a working `java` on PATH is sufficient for SpecProof to proceed."""
    java_home = os.environ.get("JAVA_HOME", "").strip()
    if not java_home:
        result.warnings.append(
            "JAVA_HOME is not set. Maven wrapper and most build scripts resolve "
            "the JDK through it; set JAVA_HOME to your JDK 21 directory if the "
            "build fails to find a compiler."
        )
        _add(result, "JAVA_HOME", "WARN", "Not set")
        return

    suffix = ".exe" if sys.platform == "win32" else ""
    java_exe = Path(java_home) / "bin" / f"java{suffix}"
    if java_exe.is_file():
        _add(result, "JAVA_HOME", "PASS", java_home)
        return
    result.warnings.append(
        f"JAVA_HOME={java_home} but {java_exe} was not found. "
        "Verify the JDK installation path."
    )
    _add(result, "JAVA_HOME", "WARN", "Invalid path")


def _check_maven_wrapper(result: PreflightResult, workspace_path: str) -> None:
    root = Path(workspace_path)
    mvnw_cmd = root / "mvnw.cmd"
    mvnw_sh = root / "mvnw"
    props = root / ".mvn" / "wrapper" / "maven-wrapper.properties"

    if not mvnw_cmd.is_file() and not mvnw_sh.is_file():
        # A repository may legitimately build with a system-wide Maven.
        # Blocking here would reject every wrapper-less Maven project even
        # though `mvn` is installed — fail only when neither exists.
        code, output = _probe(["mvn", "--version"])
        if code == 0:
            _add(result, "maven_wrapper", "PASS", f"system mvn: {_first_line(output)}")
            return
        result.errors.append(
            f"No Maven Wrapper ({mvnw_cmd.name}/mvnw) found in {workspace_path} "
            "and no 'mvn' executable on PATH. Commit mvnw/mvnw.cmd, run "
            "'mvn -N wrapper:wrapper', or install Maven."
        )
        _add(result, "maven_wrapper", "FAIL", "Not found")
        return

    if not props.is_file():
        result.errors.append(
            f"maven-wrapper.properties not found in {root / '.mvn' / 'wrapper'}."
        )
        _add(result, "maven_wrapper", "FAIL", "No properties")
        return

    try:
        content = props.read_text(encoding="utf-8")
    except OSError as exc:
        result.warnings.append(f"Could not read maven-wrapper.properties: {exc}")
        _add(result, "maven_wrapper", "WARN", str(exc))
        return

    if "repo.maven.apache.org" not in content:
        result.errors.append(
            "maven-wrapper.properties does not use the official Apache Maven "
            "repository; distributionUrl must point to repo.maven.apache.org."
        )
        _add(result, "maven_wrapper", "FAIL", "Bad distributionUrl")
        return
    if "distributionSha256Sum" not in content:
        result.warnings.append(
            "maven-wrapper.properties is missing distributionSha256Sum; the "
            "Maven distribution integrity will not be verified on download."
        )
        _add(result, "maven_wrapper", "WARN", "No SHA-256 checksum")
        return
    _add(result, "maven_wrapper", "PASS", "OK")


# ── Node checks ─────────────────────────────────────────────────────────


def _check_node(result: PreflightResult) -> None:
    code, output = _probe(["node", "--version"])
    if code == EXIT_NOT_FOUND:
        result.errors.append(
            "Node.js not found. Install Node.js 18+ from https://nodejs.org/ ."
        )
        _add(result, "node", "FAIL", "Not found")
        return
    if code != 0:
        result.errors.append(
            f"Node.js probe failed (exit {code}): {_first_line(output)}"
        )
        _add(result, "node", "FAIL", _first_line(output))
        return
    version = _major_version(output)
    if version is None or version < 18:
        result.warnings.append(
            f"Node.js 18+ recommended, found {_first_line(output)}."
        )
        _add(result, "node", "WARN", _first_line(output))
        return
    _add(result, "node", "PASS", _first_line(output))


def _check_package_manager(result: PreflightResult) -> None:
    for name in ("npm", "pnpm", "yarn"):
        code, output = _probe([name, "--version"])
        if code == 0:
            _add(result, "package_manager", "PASS", f"{name} {_first_line(output)}")
            return
    result.errors.append(
        "No Node package manager found (npm / pnpm / yarn). Install Node.js "
        "from https://nodejs.org/ so the test script can be executed."
    )
    _add(result, "package_manager", "FAIL", "Not found")


def _check_node_test_script(result: PreflightResult, workspace_path: str) -> None:
    import json

    pkg = Path(workspace_path) / "package.json"
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        result.warnings.append(f"Could not read package.json: {exc}")
        _add(result, "node_test_script", "WARN", str(exc))
        return
    scripts = data.get("scripts") or {}
    if scripts.get("test"):
        _add(result, "node_test_script", "PASS", str(scripts["test"]))
        return
    result.warnings.append(
        "package.json has no 'scripts.test'. SpecProof runs the project's own "
        "test command; without it the differential step has nothing to execute "
        "and the change stays UNVERIFIED."
    )
    _add(result, "node_test_script", "WARN", "No scripts.test")


# ── Python checks ───────────────────────────────────────────────────────


def _python_candidates() -> list[list[str]]:
    """Prefer the interpreter running SpecProof, then PATH fallbacks."""
    return [[sys.executable, "--version"], ["python3", "--version"], ["python", "--version"]]


def _check_python(result: PreflightResult) -> None:
    last_detail = "unknown"
    for cmd in _python_candidates():
        code, output = _probe(cmd)
        if code == EXIT_NOT_FOUND:
            continue
        last_detail = _first_line(output) or "unknown"
        if code == 0:
            match = re.search(r"(\d+)\.(\d+)", output)
            if match:
                major, minor = int(match.group(1)), int(match.group(2))
                if (major, minor) < (3, 9):
                    result.warnings.append(
                        "Python 3.9+ recommended for the target project, "
                        f"found {last_detail}."
                    )
                    _add(result, "python", "WARN", last_detail)
                    return
            _add(result, "python", "PASS", last_detail)
            return
    result.errors.append(
        "No working Python interpreter found on PATH. Install Python 3.9+ "
        "from https://www.python.org/ ."
    )
    _add(result, "python", "FAIL", last_detail)


def _check_pytest(result: PreflightResult) -> None:
    code, output = _probe([sys.executable, "-m", "pytest", "--version"])
    if code == 0:
        _add(result, "pytest", "PASS", _first_line(output))
        return
    result.warnings.append(
        "pytest is not importable by the current interpreter. Repositories "
        "using another runner (unittest, tox) are still supported, but the "
        "differential step needs a runner it can invoke."
    )
    _add(result, "pytest", "WARN", "Not available")


# ── Go checks ───────────────────────────────────────────────────────────


def _check_go(result: PreflightResult) -> None:
    code, output = _probe(["go", "version"])
    if code == EXIT_NOT_FOUND:
        result.errors.append(
            "Go toolchain not found. Install Go from https://go.dev/dl/ ."
        )
        _add(result, "go", "FAIL", "Not found")
        return
    if code != 0:
        result.warnings.append(f"Go probe failed (exit {code}): {_first_line(output)}")
        _add(result, "go", "WARN", _first_line(output))
        return
    _add(result, "go", "PASS", _first_line(output))


# ── Entry point ─────────────────────────────────────────────────────────


def _skip(result: PreflightResult, names: tuple[str, ...]) -> None:
    result.skipped.extend(names)


def run_preflight(
    workspace_path: str | None = None,
    language: str | None = None,
) -> PreflightResult:
    """Run the environment checks that matter for this repository.

    Args:
        workspace_path: directory holding the build file (repo root or the
            ``app_dir`` subdirectory). Maven-wrapper / package.json checks
            are skipped when it is None or does not exist.
        language: pre-detected language. When None it is detected from
            ``workspace_path``; when ``LANGUAGE_UNKNOWN`` only the universal
            checks run — an undetectable repository is never blocked here.

    A failed check never raises. Blocking problems land in ``errors``; the
    caller decides whether to abort.
    """
    result = PreflightResult()

    if language is None:
        language = detect_language(workspace_path)
    result.language = language

    workspace: str | None = None
    if workspace_path:
        try:
            if Path(workspace_path).is_dir():
                workspace = workspace_path
        except OSError:
            workspace = None

    # Universal — always.
    _check_disk_space(result)

    if language == LANGUAGE_JAVA:
        _check_java(result)
        _check_javac(result)
        _check_java_home(result)
        if workspace:
            _check_maven_wrapper(result, workspace)
        else:
            _add(result, "maven_wrapper", "WARN", "Workspace path unavailable")
            result.warnings.append(
                "Maven wrapper not checked: the workspace path was unavailable."
            )
    elif language == LANGUAGE_NODE:
        _check_node(result)
        _check_package_manager(result)
        if workspace:
            _check_node_test_script(result, workspace)
        else:
            _add(result, "node_test_script", "WARN", "Workspace path unavailable")
    elif language == LANGUAGE_PYTHON:
        _check_python(result)
        _check_pytest(result)
    elif language == LANGUAGE_GO:
        _check_go(result)

    # Record what was deliberately not run, so the UI can explain why a JDK
    # problem is absent rather than looking like a silent pass.
    ran = {c["check"] for c in result.checks}
    for other_language, names in _CHECKS_BY_LANGUAGE.items():
        if other_language == language:
            continue
        _skip(result, tuple(name for name in names if name not in ran))

    result.passed = not result.errors
    return result


def format_preflight_report(result: PreflightResult) -> str:
    """Human-readable report (CLI / logs)."""
    lines = [
        "=" * 60,
        f"SpecProof Environment Preflight (language: {result.language})",
        "=" * 60,
    ]

    icons = {"PASS": "[+]", "FAIL": "[!]", "WARN": "[~]"}
    for check in result.checks:
        icon = icons.get(check["status"], "[?]")
        lines.append(f"  {icon} {check['check']}: {check['detail']}")

    if result.skipped:
        lines.append(f"\nNot applicable ({len(result.skipped)}): {', '.join(result.skipped)}")

    if result.warnings:
        lines.append(f"\nWarnings ({len(result.warnings)}):")
        lines.extend(f"  ! {w}" for w in result.warnings)

    if result.errors:
        lines.append(f"\nERRORS ({len(result.errors)}):")
        lines.extend(f"  X {e}" for e in result.errors)
        lines.append(f"\nPreflight: FAILED — {len(result.errors)} error(s)")
    else:
        lines.append("\nPreflight: PASSED")

    return "\n".join(lines)


__all__ = [
    "LANGUAGE_GO",
    "LANGUAGE_JAVA",
    "LANGUAGE_NODE",
    "LANGUAGE_PYTHON",
    "LANGUAGE_UNKNOWN",
    "PreflightResult",
    "detect_language",
    "format_preflight_report",
    "run_preflight",
]
