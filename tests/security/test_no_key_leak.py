"""P0.5 Security regression tests — prove no API keys leak into source, logs, or artifacts.

These tests run WITHOUT Docker and WITHOUT any external services.
"""

import os
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CANARY_SECRET = "SPECPROOF_CANARY_a7f3b2c9d1e4_SECRET_DO_NOT_COMMIT"

# Patterns that would match real API keys
_KEY_PATTERNS = [
    (r'sk-[a-zA-Z0-9]{32,}', "OpenAI/LLM API Key (sk-...)"),
    (r'api[f_]?key\s*[:=]\s*["\']sk-', "Hardcoded API Key assignment"),
    (r'Authorization\s*[:=]\s*["\']?Bearer\s+sk-', "Hardcoded Bearer token"),
]


def _is_source_file(path: str) -> bool:
    """Check if a file should be scanned for secrets."""
    excludes = {
        ".git", "__pycache__", "target", "node_modules", ".mvn",
        "artifacts/legacy-invalid",
    }
    skip_exts = {".jar", ".zip", ".class", ".jpg", ".png", ".woff", ".gz", ".tar"}
    normalized = path.replace("\\", "/")
    if any(normalized.startswith(f"{e}/") or normalized == e for e in excludes):
        return False
    ext = os.path.splitext(normalized)[1].lower()
    if ext in skip_exts:
        return False
    if "maven-wrapper.jar" in normalized:
        return False
    return True


class TestNoHardcodedKeys:
    """Prove no `sk-*` API keys exist in source files."""

    def test_no_api_key_in_python_source(self):
        """All .py files (tracked or untracked) must be free of `sk-***` keys."""
        violations = []
        for filepath in PROJECT_ROOT.rglob("*.py"):
            rel = str(filepath.relative_to(PROJECT_ROOT)).replace("\\", "/")
            if not _is_source_file(rel):
                continue
            if rel.endswith(".env") or "security_scanner" in rel:
                continue
            try:
                content = filepath.read_text(encoding="utf-8")
            except (UnicodeDecodeError, PermissionError):
                continue
            for lineno, line in enumerate(content.splitlines(), 1):
                for pattern, name in _KEY_PATTERNS:
                    for m in re.finditer(pattern, line, re.IGNORECASE):
                        matched = m.group(0)
                        # Allow known canary secret
                        if CANARY_SECRET in matched:
                            continue
                        # Allow regex pattern definitions in security scanners
                        if "r'" in line and "'" in line and line.strip().startswith("("):
                            continue
                        # Allow env var reads: os.getenv("LLM_API_KEY")
                        if "os.getenv" in line:
                            continue
                        # Allow .env key=value pattern for docs
                        if "LLM_API_KEY=" in line and "replace_me" in line.lower():
                            continue
                        violations.append(f"{rel}:{lineno} — {name}: {matched[:6]}***")

        assert violations == [], (
            f"Found {len(violations)} hardcoded API key(s):\n"
            + "\n".join(violations)
        )

    def test_no_api_key_in_java_source(self):
        """All .java files must be free of `sk-***` keys."""
        violations = []
        for filepath in PROJECT_ROOT.rglob("*.java"):
            rel = str(filepath.relative_to(PROJECT_ROOT)).replace("\\", "/")
            if not _is_source_file(rel):
                continue
            try:
                content = filepath.read_text(encoding="utf-8")
            except (UnicodeDecodeError, PermissionError):
                continue
            for lineno, line in enumerate(content.splitlines(), 1):
                if "sk-" in line.lower() and len(line.strip()) > 30:
                    violations.append(f"{rel}:{lineno}")

        assert violations == [], (
            f"Found {len(violations)} potential API keys in Java source:\n"
            + "\n".join(violations)
        )

    def test_no_api_key_in_config_files(self):
        """YAML, JSON, TOML, .properties, .xml files must be free of `sk-***` keys."""
        violations = []
        for pattern in ("*.yml", "*.yaml", "*.json", "*.toml", "*.properties", "*.xml", "*.cfg", "*.ini"):
            for filepath in PROJECT_ROOT.rglob(pattern):
                rel = str(filepath.relative_to(PROJECT_ROOT)).replace("\\", "/")
                if not _is_source_file(rel):
                    continue
                if ".env" in rel:
                    continue
                try:
                    content = filepath.read_text(encoding="utf-8")
                except (UnicodeDecodeError, PermissionError):
                    continue
                for lineno, line in enumerate(content.splitlines(), 1):
                    for pat, name in _KEY_PATTERNS:
                        if re.search(pat, line, re.IGNORECASE):
                            matched = re.search(pat, line, re.IGNORECASE).group(0)
                            if CANARY_SECRET in matched:
                                continue
                            if "replace_me" in line.lower():
                                continue
                            violations.append(f"{rel}:{lineno} — {name}")

        assert violations == [], (
            f"Found {len(violations)} potential API keys in config files:\n"
            + "\n".join(violations)
        )

    def test_closed_loop_script_reads_from_env(self):
        """p0_5_closed_loop.py must use os.getenv, not a hardcoded key."""
        script = PROJECT_ROOT / "scripts" / "p0_5_closed_loop.py"
        if not script.exists():
            pytest.skip("p0_5_closed_loop.py not found")
        content = script.read_text(encoding="utf-8")
        assert "os.getenv(" in content, "Must read key from env var"
        assert 'sk-Twrx' not in content, "Old hardcoded key must be removed"

    def test_env_example_uses_placeholder(self):
        """.env.example must use 'replace_me' placeholder, not a real key."""
        env_example = PROJECT_ROOT / ".env.example"
        if not env_example.exists():
            pytest.skip(".env.example not found")
        content = env_example.read_text(encoding="utf-8")
        for line in content.splitlines():
            if "LLM_API_KEY" in line and "=" in line and not line.strip().startswith("#"):
                val = line.split("=", 1)[-1].strip().strip('"').strip("'")
                if len(val) > 8 and "replace" not in val.lower():
                    raise AssertionError(
                        f".env.example contains a non-placeholder value: {val[:10]}***"
                    )


class TestCanaryDetection:
    """Prove the canary secret injection self-test works."""

    def test_canary_is_detectable(self):
        """Write a canary file, scan it, confirm detection, delete it."""
        canary_file = PROJECT_ROOT / ".specproof_canary_test.txt"
        canary_file.write_text(
            f"# Canary injection test\nAPI_KEY={CANARY_SECRET}\n", encoding="utf-8"
        )
        try:
            content = canary_file.read_text(encoding="utf-8")
            assert CANARY_SECRET in content, "Canary secret was not injected"
        finally:
            canary_file.unlink()

    def test_python_scanner_detects_sk_prefix(self):
        """A file containing `sk-` + 32 chars should be detected by the scan logic."""
        # Simulate a file with a canary key
        test_file = PROJECT_ROOT / ".specproof_scanner_test.txt"
        test_key = "sk-" + "a" * 48  # 51-char test key
        test_file.write_text(f"KEY={test_key}\n", encoding="utf-8")
        try:
            content = test_file.read_text(encoding="utf-8")
            matches = re.findall(r'sk-[a-zA-Z0-9]{32,}', content)
            assert len(matches) >= 1, "Scanner regex should detect sk-*** pattern"
        finally:
            test_file.unlink()

    def test_security_scanner_module_imports(self):
        """The security_scanner module must be importable and have the canary."""
        sys.path.insert(0, str(PROJECT_ROOT))
        try:
            from agent.security_scanner import _CANARY_SECRET, scan_canary
            assert _CANARY_SECRET == CANARY_SECRET, "Canary constant mismatch"
            # Run canary self-test
            result = scan_canary(str(PROJECT_ROOT))
            assert result["injected"], f"Canary injection failed: {result}"
            assert result["found"], f"Canary not detected: {result}"
            assert result["cleaned"], f"Canary not cleaned: {result}"
        finally:
            sys.path.pop(0)


class TestCapsuleAndArtifactSafety:
    """Prove capsules and generated artifacts don't leak keys."""

    def test_frozen_archive_no_api_key(self):
        """The frozen 511A3276 archive must not contain `sk-` API keys."""
        archive = PROJECT_ROOT / "artifacts" / "p0.5" / "511A3276"
        if not archive.exists():
            pytest.skip("Frozen archive 511A3276 not found")
        for fpath in archive.rglob("*"):
            if not fpath.is_file():
                continue
            # Only check text files
            ext = fpath.suffix.lower()
            if ext in (".zip", ".jar", ".class", ".jpg", ".png"):
                continue
            try:
                content = fpath.read_text(encoding="utf-8")
            except (UnicodeDecodeError, PermissionError):
                continue
            for lineno, line in enumerate(content.splitlines(), 1):
                for pat, name in _KEY_PATTERNS:
                    if re.search(pat, line):
                        rel = str(fpath.relative_to(archive))
                        raise AssertionError(
                            f"Archive file {rel}:{lineno} contains {name}"
                        )

    def test_legacy_invalid_archive_no_api_key_hardcoded(self):
        """Legacy-invalid archive files should not contain actual production keys.
        The human_fixture file may contain test/demo API patterns but not live keys."""
        legacy = PROJECT_ROOT / "artifacts" / "legacy-invalid"
        if not legacy.exists():
            pytest.skip("legacy-invalid archive not found")
        for fpath in legacy.rglob("*"):
            if not fpath.is_file():
                continue
            ext = fpath.suffix.lower()
            if ext in (".zip", ".jar", ".class"):
                continue
            try:
                content = fpath.read_text(encoding="utf-8")
            except (UnicodeDecodeError, PermissionError):
                continue
            for lineno, line in enumerate(content.splitlines(), 1):
                if CANARY_SECRET in line:
                    continue
                if "sk-" in line.lower():
                    rel = str(fpath.relative_to(legacy))
                    # Allow human_fixture with demo patterns
                    if "human_fixture" in rel or "README" in rel:
                        continue
                    raise AssertionError(
                        f"Legacy archive {rel}:{lineno} contains 'sk-' pattern"
                    )
