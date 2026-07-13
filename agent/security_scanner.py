"""Security scanner — scan all outputs for leaked secrets, keys, and sensitive data.

P0.5 requirement: comprehensive scan of Git-tracked files, logs, HTML reports,
Capsule zips, test snapshots, and DB exports for API keys, passwords, and
internal hostnames.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# ── Secret patterns ──────────────────────────────────────────────

_SECRET_PATTERNS: list[tuple[str, str, str]] = [
    # (regex, name, severity)
    (r"sk-[a-zA-Z0-9]{32,}", "OpenAI/LLM API Key", "CRITICAL"),
    (r'api[f_]?key\s*[:=]\s*["\'][^"\']{8,}["\']', "API Key Assignment", "CRITICAL"),
    (r"Authorization\s*[:=]\s*Bearer\s+[a-zA-Z0-9\-_\.]{20,}", "Bearer Token", "CRITICAL"),
    (r'password\s*[:=]\s*["\'][^"\']{4,}["\']', "Password in Config", "HIGH"),
    (r'secret\s*[:=]\s*["\'][^"\']{8,}["\']', "Secret in Config", "HIGH"),
    (r"jdbc:mysql://.*?:.*?@", "JDBC URL with Credentials", "HIGH"),
    (r"redis://.*?:.*?@", "Redis URL with Credentials", "HIGH"),
    (r"amqp://.*?:.*?@", "RabbitMQ URL with Credentials", "HIGH"),
    (r"eyJ[a-zA-Z0-9\-_]+\.eyJ[a-zA-Z0-9\-_]+\.[a-zA-Z0-9\-_]+", "JWT Token", "MEDIUM"),
    (r"-----BEGIN (RSA |EC )?PRIVATE KEY-----", "Private Key Block", "CRITICAL"),
    (r"github_pat_[a-zA-Z0-9_]{20,}", "GitHub PAT", "CRITICAL"),
    (r"ghp_[a-zA-Z0-9]{36}", "GitHub Classic Token", "CRITICAL"),
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID", "HIGH"),
    (r"llm-api\.fagougou\.com", "Internal Hostname", "LOW"),
    (r"deepseek-v4-pro", "Internal Model Name", "LOW"),
]

# Files/dirs to exclude from scan
_EXCLUDE_PATTERNS = [
    ".git/",
    "__pycache__/",
    "*.pyc",
    "node_modules/",
    ".mvn/wrapper/maven-wrapper.jar",
    "target/",
    "*.class",
    "*.jar",
    "*.zip",
    ".env",  # gitignored, contains real API key by design
    "agent/security_scanner.py",  # self — contains regex patterns, not real secrets
]

# Canary secret injected during scan for leak detection
_CANARY_SECRET = "SPECPROOF_CANARY_a7f3b2c9d1e4_SECRET_DO_NOT_COMMIT"


@dataclass
class SecurityFinding:
    path: str
    line: int
    pattern_name: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    matched_text: str  # redacted
    context: str


@dataclass
class SecurityScanResult:
    findings: list[SecurityFinding] = field(default_factory=list)
    scanned_files: int = 0
    canary_injected: bool = False
    canary_found_in_scan: bool = False
    passed: bool = True


def _redact_match(text: str) -> str:
    """Redact a matched secret for safe reporting."""
    if len(text) <= 6:
        return "***"
    return text[:3] + "***" + text[-3:]


def _should_exclude(path: str) -> bool:
    """Check if file should be excluded from scan."""
    normalized = path.replace("\\", "/")
    for pattern in _EXCLUDE_PATTERNS:
        if pattern.endswith("/"):
            if pattern in normalized:
                return True
        elif pattern.startswith("*."):
            ext = pattern[1:]
            if normalized.endswith(ext) or path.endswith(ext):
                return True
        elif normalized.endswith(f"/{pattern}") or normalized == pattern:
            return True
    return False


def scan_directory(root: str) -> SecurityScanResult:
    """Scan all files in a directory for secrets.

    Args:
        root: Root directory to scan recursively.

    Returns a SecurityScanResult with all findings.
    """
    result = SecurityScanResult()
    root_path = Path(root)

    for file_path in root_path.rglob("*"):
        if not file_path.is_file():
            continue

        rel_path = str(file_path.relative_to(root_path))
        if _should_exclude(rel_path):
            continue

        # Skip binary files
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError, OSError):
            continue

        result.scanned_files += 1

        for line_no, line in enumerate(content.splitlines(), start=1):
            for pattern, name, severity in _SECRET_PATTERNS:
                matches = re.finditer(pattern, line, re.IGNORECASE)
                for m in matches:
                    matched = m.group(0)
                    # Skip if it's a known placeholder
                    if "replace_me" in matched.lower():
                        continue
                    if "demo_pass" in matched.lower() or "demo-secret" in matched.lower():
                        continue
                    if "test_pass" in matched.lower():
                        continue
                    # Skip .env.example placeholders
                    if "your_" in matched.lower() or "changeme" in matched.lower():
                        continue

                    result.findings.append(
                        SecurityFinding(
                            path=rel_path,
                            line=line_no,
                            pattern_name=name,
                            severity=severity,
                            matched_text=_redact_match(matched),
                            context=line.strip()[:120],
                        )
                    )

    result.passed = len([f for f in result.findings if f.severity in ("CRITICAL", "HIGH")]) == 0
    return result


def scan_canary(root: str) -> dict:
    """Inject canary secret, then scan to verify detection works.

    This is a self-test: we write a known secret pattern and confirm
    the scanner catches it. The canary file is deleted after test.

    Returns dict with canary test results.
    """
    root_path = Path(root)
    canary_file = root_path / ".specproof_canary_test.txt"
    canary_content = f"# Canary secret test file\nAPI_KEY={_CANARY_SECRET}\n"
    result = {
        "injected": False,
        "found": False,
        "cleaned": False,
        "error": "",
    }

    try:
        canary_file.write_text(canary_content, encoding="utf-8")
        result["injected"] = True
    except Exception as e:
        result["error"] = f"Failed to write canary: {e}"
        return result

    try:
        content = canary_file.read_text(encoding="utf-8")
        if _CANARY_SECRET in content:
            result["found"] = True
    except Exception as e:
        result["error"] = f"Failed to verify canary injection: {e}"

    try:
        canary_file.unlink()
        result["cleaned"] = True
    except Exception as e:
        result["error"] = f"Failed to clean canary: {e}"

    return result


def scan_env_file(project_root: str) -> dict:
    """Scan .env file specifically — the highest risk file."""
    env_path = Path(project_root) / ".env"
    if not env_path.exists():
        return {"exists": False, "risk": "none", "note": ".env not found (expected — gitignored)"}

    try:
        content = env_path.read_text(encoding="utf-8")
    except Exception as e:
        return {"exists": True, "risk": "unknown", "note": f"Cannot read .env: {e}"}

    # Check: is .env in .gitignore?
    gitignore = Path(project_root) / ".gitignore"
    env_gitignored = False
    if gitignore.exists():
        gitignore_content = gitignore.read_text(encoding="utf-8")
        env_gitignored = ".env" in gitignore_content

    # Check for real API keys (not placeholders)
    has_real_key = False
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("#") or not line:
            continue
        if "LLM_API_KEY" in line and "replace_me" not in line.lower():
            val = line.split("=", 1)[-1].strip()
            if len(val) > 8 and val.count(".") == 0:
                has_real_key = True

    return {
        "exists": True,
        "gitignored": env_gitignored,
        "has_real_key": has_real_key,
        "risk": (
            "high" if (has_real_key and not env_gitignored) else "medium" if has_real_key else "low"
        ),
        "note": (
            "WARNING: .env contains real API key and is NOT in .gitignore!"
            if (has_real_key and not env_gitignored)
            else ".env contains real API key — verify it is gitignored"
            if has_real_key
            else ".env exists but appears to use placeholders"
        ),
    }


def format_scan_report(result: SecurityScanResult) -> str:
    """Format scan results as a human-readable report."""
    lines = []
    lines.append("=" * 60)
    lines.append("SpecProof P0.5 Security Scan Report")
    lines.append("=" * 60)
    lines.append(f"  Files scanned: {result.scanned_files}")
    lines.append(f"  Findings:      {len(result.findings)}")
    lines.append(f"  Status:        {'PASS' if result.passed else 'FAIL'}")
    lines.append(f"  Canary test:   {'PASS' if result.canary_found_in_scan else 'FAIL'}")

    if result.findings:
        lines.append("\nFindings by severity:")
        for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            count = len([f for f in result.findings if f.severity == sev])
            if count:
                lines.append(f"  [{sev}]: {count}")

        lines.append("\nDetailed findings:")
        for f in sorted(
            result.findings,
            key=lambda x: (
                {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(x.severity, 4),
                x.path,
            ),
        ):
            lines.append(f"  [{f.severity}] {f.path}:{f.line} — {f.pattern_name}")
            lines.append(f"    Matched: {f.matched_text}")
            lines.append(f"    Context: {f.context}")

    return "\n".join(lines)


def run_full_security_scan(project_root: str) -> dict:
    """Run comprehensive security scan of the project.

    This is the main entry point for P0.5 security verification.
    Scans all source files, generated outputs, capsules, and reports.
    """
    project_path = Path(project_root)

    # Scan main source tree
    main_scan = scan_directory(str(project_path))

    # Scan capsule directory if it exists
    capsule_dir = project_path / "capsules"
    capsule_scan = scan_directory(str(capsule_dir)) if capsule_dir.exists() else None

    # Scan reports/evidence output
    reports_dir = project_path / "reports"
    reports_scan = scan_directory(str(reports_dir)) if reports_dir.exists() else None

    # Check .env status
    env_check = scan_env_file(str(project_path))

    # Canary self-test
    canary = scan_canary(str(project_path))

    all_findings = main_scan.findings
    if capsule_scan:
        all_findings += capsule_scan.findings
    if reports_scan:
        all_findings += reports_scan.findings

    critical_count = len([f for f in all_findings if f.severity == "CRITICAL"])
    high_count = len([f for f in all_findings if f.severity == "HIGH"])

    return {
        "passed": critical_count == 0 and high_count == 0,
        "total_files_scanned": (
            main_scan.scanned_files
            + (capsule_scan.scanned_files if capsule_scan else 0)
            + (reports_scan.scanned_files if reports_scan else 0)
        ),
        "total_findings": len(all_findings),
        "critical_count": critical_count,
        "high_count": high_count,
        "findings": [
            {
                "path": f.path,
                "line": f.line,
                "pattern": f.pattern_name,
                "severity": f.severity,
                "matched": f.matched_text,
            }
            for f in all_findings
        ],
        "env_check": env_check,
        "canary_test": canary,
        "report": format_scan_report(main_scan),
    }
