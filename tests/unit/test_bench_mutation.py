"""Unit tests for the mutation kill-rate benchmark (offline, no Docker/network).

The offline sample (scripts/mutation_sample) is hand-defined and
deterministic: exactly 6 mutants, of which 5 are killed and 1 survives
(M06 targets an out-of-spec, untested behavior — the honest gap). M04 is
killed by the SpecProof verdict alone because the test suite deliberately
does not probe the 100.0 free-shipping boundary.
"""

import json
import shutil
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import mutation_bench_lib  # noqa: E402
from mutation_bench_lib import (  # noqa: E402
    OFFLINE_SAMPLE,
    BenchError,
    run_mutation_bench,
)

SAMPLE_MUTANT_IDS = {"M01", "M02", "M03", "M04", "M05", "M06"}


def test_offline_sample_kill_rate_and_records(tmp_path: Path) -> None:
    out_json = tmp_path / "mutation-results.json"
    out_md = tmp_path / "mutation-results.md"
    result = run_mutation_bench(OFFLINE_SAMPLE, 10, out_json=out_json, out_md=out_md)

    assert result.mutants_requested == 10
    assert result.mutants_total == 6
    assert result.killed == 5
    assert result.survived == 1
    assert result.skipped == 0
    assert 0.0 <= result.kill_rate <= 1.0
    assert result.kill_rate == pytest.approx(5 / 6, abs=1e-3)
    assert result.baseline_ok

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["summary"]["kill_rate"] == pytest.approx(5 / 6, abs=1e-3)
    records = payload["records"]
    assert len(records) == 6
    for record in records:
        assert record["mutant_id"] in SAMPLE_MUTANT_IDS
        assert record["status"] in {"killed", "survived", "skipped"}
        assert record["killed_by"] is not None

    m04 = next(record for record in records if record["mutant_id"] == "M04")
    assert m04["status"] == "killed"
    assert m04["killed_by"] == ["spec_verdict"]
    assert m04["test_exit_code"] == 0

    m06 = next(record for record in records if record["mutant_id"] == "M06")
    assert m06["status"] == "survived"
    assert m06["killed_by"] == []

    assert out_md.is_file()
    assert "变异杀死率" in out_md.read_text(encoding="utf-8")


def test_mutant_cap_respected(tmp_path: Path) -> None:
    result = run_mutation_bench(OFFLINE_SAMPLE, 3)
    assert result.mutants_requested == 3
    assert result.mutants_total == 3
    assert result.killed + result.survived + result.skipped == 3


def test_unavailable_checkers_skip_honestly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "sample"
    shutil.copytree(OFFLINE_SAMPLE, target)
    (target / "spec" / "contract.py").unlink()
    monkeypatch.setattr(
        mutation_bench_lib,
        "_pytest_command",
        lambda: [str(tmp_path / "missing-python.exe")],
    )
    out_json = tmp_path / "mutation-results.json"

    result = run_mutation_bench(target, 10, out_json=out_json)

    assert result.killed == 0
    assert result.survived == 0
    assert result.skipped == result.mutants_total == 6
    assert result.kill_rate == 0.0
    assert not result.baseline_ok
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["summary"]["skipped"] == 6
    assert all(record["status"] == "skipped" for record in payload["records"])
    assert all(record["killed_by"] == [] for record in payload["records"])


def test_invalid_manifest_old_string_raises(tmp_path: Path) -> None:
    target = tmp_path / "sample"
    shutil.copytree(OFFLINE_SAMPLE, target)
    manifest_path = target / "mutants" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["mutants"][0]["old"] = "="  # occurs many times -> not exactly once
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(BenchError):
        run_mutation_bench(target, 10)


def test_cli_offline_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(Path(__file__).resolve().parents[2])
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    from bench_mutation import main  # noqa: E402

    out_json = tmp_path / "mutation-results.json"
    out_md = tmp_path / "mutation-results.md"
    exit_code = main([
        "--offline",
        "--json",
        str(out_json),
        "--markdown",
        str(out_md),
    ])

    assert exit_code == 0
    assert out_json.is_file()
    assert out_md.is_file()
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["summary"]["mutants_total"] == 6
