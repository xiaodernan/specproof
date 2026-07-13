"""Preflight checks — verify environment before running verification.

Phase 0.5: fail-fast with clear messages when prerequisites are missing.
Never silently skip core verification tests.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field


@dataclass
class PreflightResult:
    passed: bool = True
    checks: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def run_preflight(workspace_path: str | None = None) -> PreflightResult:
    """Run all environment preflight checks.

    Args:
        workspace_path: Optional path to the demo/spring-backend directory.
                       If None, skips Maven/Docker checks.

    Returns a PreflightResult with detailed check results.
    """
    result = PreflightResult()

    _check_java(result)
    _check_javac(result)
    _check_java_home(result)
    _check_disk_space(result)

    if workspace_path:
        _check_maven_wrapper(result, workspace_path)

    _check_docker(result)

    result.passed = len(result.errors) == 0
    return result


def _add_check(result: PreflightResult, check: str, status: str, detail: str) -> None:
    """Append a check dict to the result."""
    result.checks.append({"check": check, "status": status, "detail": detail})


def _check_java(result: PreflightResult) -> None:
    """Check java -version works."""
    java_home = os.environ.get("JAVA_HOME", "")
    java_bin = os.path.join(java_home, "bin", "java.exe") if java_home else "java"
    java_cmd = java_bin if (sys.platform == "win32" and java_home) else "java"

    try:
        proc = subprocess.run(
            [java_cmd, "-version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        output = proc.stdout + proc.stderr
        first_line = output.splitlines()[0] if output.splitlines() else "ok"
        if "21." in output or "21.0" in output:
            _add_check(result, "java", "PASS", first_line)
        else:
            found_ver = output.splitlines()[0] if output.splitlines() else "unknown"
            result.errors.append(
                f"JDK 21 required. Found: {found_ver}. "
                "Install Eclipse Temurin JDK 21: https://adoptium.net/"
            )
            _add_check(result, "java", "FAIL", "Wrong version")
    except FileNotFoundError:
        result.errors.append(
            "Java not found. Install Eclipse Temurin JDK 21 "
            "from https://adoptium.net/ "
            "and set JAVA_HOME environment variable."
        )
        _add_check(result, "java", "FAIL", "Not found")
    except Exception as exc:
        result.errors.append(f"Java check failed: {exc}")
        _add_check(result, "java", "FAIL", str(exc))


def _check_javac(result: PreflightResult) -> None:
    """Check javac -version works."""
    java_home = os.environ.get("JAVA_HOME", "")
    java_home_bin = os.path.join(java_home, "bin")
    javac_bin = os.path.join(java_home_bin, "javac.exe") if java_home else "javac"
    javac_cmd = javac_bin if (sys.platform == "win32" and java_home) else "javac"

    try:
        proc = subprocess.run(
            [javac_cmd, "-version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        output = proc.stdout + proc.stderr
        if "21" in output:
            _add_check(result, "javac", "PASS", output.strip())
        else:
            result.errors.append(
                f"JDK 21 javac required. Found: {output.strip()}. Install Eclipse Temurin JDK 21."
            )
            _add_check(result, "javac", "FAIL", "Wrong version")
    except FileNotFoundError:
        result.errors.append("javac not found. Install JDK 21 and set JAVA_HOME.")
        _add_check(result, "javac", "FAIL", "Not found")
    except Exception as exc:
        result.errors.append(f"javac check failed: {exc}")
        _add_check(result, "javac", "FAIL", str(exc))


def _check_java_home(result: PreflightResult) -> None:
    """Check JAVA_HOME is set and points to a valid JDK."""
    java_home = os.environ.get("JAVA_HOME", "")
    if not java_home:
        result.errors.append(
            "JAVA_HOME is not set. Set it to your JDK 21 installation directory, e.g.:\n"
            r'  $env:JAVA_HOME = "C:\path\to\jdk-21"'
        )
        _add_check(result, "JAVA_HOME", "FAIL", "Not set")
        return

    java_exe = os.path.join(java_home, "bin", "java.exe")
    if sys.platform != "win32":
        java_exe = os.path.join(java_home, "bin", "java")

    if os.path.isfile(java_exe):
        _add_check(result, "JAVA_HOME", "PASS", java_home)
    else:
        result.errors.append(
            f"JAVA_HOME={java_home} but {java_exe} not found. Verify the JDK installation path."
        )
        _add_check(result, "JAVA_HOME", "FAIL", "Invalid path")


def _check_disk_space(result: PreflightResult) -> None:
    """Check available disk space on the working drive."""
    try:
        cwd = os.getcwd()
        drive = os.path.splitdrive(cwd)[0] or "C:" if sys.platform == "win32" else "/"

        usage = shutil.disk_usage(drive)
        free_gb = usage.free / (1024**3)
        gb_str = f"{free_gb:.1f} GB"
        if free_gb < 1.0:
            result.errors.append(
                f"Low disk space: {gb_str} free on {drive}. "
                "At least 1 GB required for Maven dependencies and build artifacts."
            )
            _add_check(result, "disk_space", "FAIL", gb_str)
        elif free_gb < 5.0:
            result.warnings.append(f"Disk space low: {gb_str} free on {drive}.")
            _add_check(result, "disk_space", "WARN", gb_str)
        else:
            _add_check(result, "disk_space", "PASS", gb_str)
    except Exception as exc:
        result.warnings.append(f"Could not check disk space: {exc}")
        _add_check(result, "disk_space", "WARN", str(exc))


def _check_maven_wrapper(result: PreflightResult, workspace_path: str) -> None:
    """Check Maven Wrapper files exist in workspace."""
    mvnw_cmd = os.path.join(workspace_path, "mvnw.cmd")
    mvnw_sh = os.path.join(workspace_path, "mvnw")
    props = os.path.join(workspace_path, ".mvn", "wrapper", "maven-wrapper.properties")

    if not os.path.isfile(mvnw_cmd) and not os.path.isfile(mvnw_sh):
        result.errors.append(
            f"No Maven Wrapper found in {workspace_path}. "
            "Run 'mvn -N wrapper:wrapper' or commit mvnw/mvnw.cmd files."
        )
        _add_check(result, "maven_wrapper", "FAIL", "Not found")
        return

    if not os.path.isfile(props):
        result.errors.append(
            f"maven-wrapper.properties not found in {workspace_path}/.mvn/wrapper/"
        )
        _add_check(result, "maven_wrapper", "FAIL", "No properties")
        return

    # Verify distributionUrl
    try:
        with open(props, encoding="utf-8") as f:
            content = f.read()
        if "repo.maven.apache.org" not in content:
            result.errors.append(
                "maven-wrapper.properties does not use official "
                "Apache Maven repository. distributionUrl must "
                "point to repo.maven.apache.org."
            )
            _add_check(result, "maven_wrapper", "FAIL", "Bad distributionUrl")
        elif "distributionSha256Sum" not in content:
            result.warnings.append(
                "maven-wrapper.properties missing distributionSha256Sum. "
                "Maven distribution integrity will not be verified "
                "on download."
            )
            _add_check(result, "maven_wrapper", "WARN", "No SHA-256 checksum")
        else:
            _add_check(result, "maven_wrapper", "PASS", "OK")
    except Exception as exc:
        result.warnings.append(f"Could not verify maven-wrapper.properties: {exc}")
        _add_check(result, "maven_wrapper", "WARN", str(exc))


def _check_docker(result: PreflightResult) -> None:
    """Check Docker availability (optional for Phase 0)."""
    try:
        proc = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if proc.returncode == 0:
            _add_check(result, "docker", "PASS", proc.stdout.strip())
        else:
            result.warnings.append(
                "Docker not available. Phase 0 can run without "
                "Docker, but Testcontainers-based tests will be skipped."
            )
            _add_check(result, "docker", "WARN", "Not available")
    except FileNotFoundError:
        result.warnings.append(
            "Docker not found. Phase 0 can proceed, Testcontainers tests will not run."
        )
        _add_check(result, "docker", "WARN", "Not installed")
    except Exception as exc:
        result.warnings.append(f"Docker check failed: {exc}")
        _add_check(result, "docker", "WARN", str(exc))


def format_preflight_report(result: PreflightResult) -> str:
    """Format preflight results as a human-readable report."""
    lines = []
    lines.append("=" * 60)
    lines.append("SpecProof P0.5 Environment Preflight")
    lines.append("=" * 60)

    for check in result.checks:
        icon = {"PASS": "[+]", "FAIL": "[!]", "WARN": "[~]"}.get(check["status"], "[?]")
        lines.append(f"  {icon} {check['check']}: {check['detail']}")

    if result.warnings:
        lines.append(f"\nWarnings ({len(result.warnings)}):")
        for w in result.warnings:
            lines.append(f"  ! {w}")

    if result.errors:
        lines.append(f"\nERRORS ({len(result.errors)}):")
        for e in result.errors:
            lines.append(f"  X {e}")
        lines.append(f"\nPreflight: FAILED — {len(result.errors)} error(s)")
    else:
        lines.append("\nPreflight: PASSED")

    return "\n".join(lines)
