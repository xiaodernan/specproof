"""`specproof doctor` runs the same preflight this pipeline runs inline.

The pipeline exercises the probe in the worker; the operator exercises the
same probe through `specproof doctor`. The two must agree on the shape —
this gate locks the shape and the command surface.
"""

from __future__ import annotations

import json

from click.testing import CliRunner

from agent.preflight import LANGUAGE_UNKNOWN
from cli.specproof.main import cli


def test_doctor_exits_zero_on_a_passing_repo(tmp_path) -> None:  # noqa: ANN001
    (tmp_path / "pyproject.toml").write_text("[build-system]\nrequires = []\n", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(cli, ["doctor", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "Preflight: PASSED" in result.output


def test_doctor_json_emits_the_preflight_dict(tmp_path) -> None:  # noqa: ANN001
    (tmp_path / "pyproject.toml").write_text("[build-system]\nrequires = []\n", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(cli, ["doctor", str(tmp_path), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["language"] == "python"
    assert payload["passed"] is True


def test_doctor_language_unknown_only_runs_universal(tmp_path) -> None:  # noqa: ANN001
    runner = CliRunner()
    result = runner.invoke(cli, ["doctor", str(tmp_path), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["language"] == LANGUAGE_UNKNOWN
    names = {c["check"] for c in payload["checks"]}
    assert "disk_space" in names


def test_doctor_fails_on_missing_directory() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["doctor", r"C:\definitely\does\not\exist"])
    assert result.exit_code != 0
