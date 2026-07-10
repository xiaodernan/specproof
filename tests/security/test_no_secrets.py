"""Security tests — verify no API key leakage."""

import os
import re

import pytest


class TestNoSecretLeakage:
    """Ensure secrets never appear in files or environment dumps."""

    def test_env_example_has_no_real_keys(self) -> None:
        env_path = os.path.join(
            os.path.dirname(__file__), "..", "..", ".env.example"
        )
        if not os.path.exists(env_path):
            pytest.skip(".env.example not found")

        with open(env_path, encoding="utf-8") as f:
            content = f.read()

        assert "sk-" not in content, "Real API key pattern found in .env.example"
        for line in content.splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                value = line.split("=", 1)[1].strip()
                if value and "KEY" in line.upper():
                    assert value == "replace_me", (
                        f"Non-placeholder value in .env.example: {line}"
                    )

    def test_compose_file_has_no_real_keys(self) -> None:
        compose_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "compose.phase0.yml"
        )
        if not os.path.exists(compose_path):
            pytest.skip("compose.phase0.yml not found")

        with open(compose_path, encoding="utf-8") as f:
            content = f.read()

        assert "sk-" not in content, "Real API key pattern found in compose file"

    def test_source_code_no_hardcoded_apikey(self) -> None:
        """Scan all Python files for hard-coded API key patterns."""
        project_root = os.path.join(os.path.dirname(__file__), "..", "..")
        key_pattern = re.compile(r'sk-[a-zA-Z0-9]{20,}')

        for dirpath, dirnames, filenames in os.walk(project_root):
            dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".venv", "venv")]
            for fname in filenames:
                if fname.endswith(".py"):
                    fpath = os.path.join(dirpath, fname)
                    with open(fpath, encoding="utf-8") as f:
                        content = f.read()
                    if key_pattern.search(content):
                        pytest.fail(f"API key pattern found in {fpath}")
