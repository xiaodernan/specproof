"""specproof evidence CLI tests (Phase 2).

The three subcommands are the operator's way IN to the phase-2 capabilities.
Their output is what an operator reads when something went wrong, so the
tests pin the honest parts:

- replay-batch refuses to run without a repository (a batch that judged
  nothing is not a batch that passed);
- a batch where nothing could be judged exits non-zero;
- verify-cert says "digest attestation", never "signed certificate", for
  an unsigned document;
- verify-cert exits non-zero for anything that is not "valid";
- scan reports findings and exits non-zero, and deletes nothing.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from cli.specproof.commands.evidence import evidence_cmd


def _zip(path: Path, finding_id: str = "F-1") -> Path:
    manifest = {
        "finding_id": finding_id,
        "severity": "MAJOR",
        "contract_id": "C-1",
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("run.sh", "#!/bin/bash\necho '>> REGRESSION CONFIRMED <<'\n")
    return path


def _certificate(path: Path, *, signed: bool) -> Path:
    document = {
        "subject": {"repository": "/repo", "commit_sha": "abc"},
        "requirements_digest": "sha256:req",
        "result": "VERIFIED",
        "verified_contracts": 1,
        "unverified_contracts": 0,
        "evidence_digests": [],
        "toolchain": {},
        "issued_at": "2026-10-20T00:00:00+00:00",
        "issuer": "SpecProof",
        "version": "0.1.0",
    }
    if signed:
        import os

        from evidence.signing import generate_key_hex, sign_statement

        os.environ["SPECPROOF_SIGNING_KEY"] = generate_key_hex()
        document = sign_statement(document)
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return path


# ── replay-batch ───────────────────────────────────────────────────────────


def test_replay_batch_without_repo_refuses_to_run(tmp_path: Path) -> None:
    """No repo means nothing was judged — that is not a passing batch."""
    _zip(tmp_path / "c.zip")
    result = CliRunner().invoke(
        evidence_cmd, ["replay-batch", str(tmp_path)]
    )
    assert result.exit_code == 1
    assert "--repo is required" in result.output


def test_replay_batch_with_no_capsules_fails(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    result = CliRunner().invoke(
        evidence_cmd, ["replay-batch", str(tmp_path), "--repo", str(repo)]
    )
    assert result.exit_code == 1
    assert "no capsule" in result.output


def test_replay_batch_reports_a_batch_that_judged_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing judged ⇒ non-zero exit: a cron wrapper must not read silence
    as success."""
    _zip(tmp_path / "c.zip")
    repo = tmp_path / "repo"
    repo.mkdir()

    def fake_replay(work_dir: Path, target: Path, timeout: int) -> dict[str, Any]:
        return {"status": "clone_failed", "error": "sandbox down"}

    monkeypatch.setattr(
        "evidence.capsule_replay.run_capsule_replay", fake_replay
    )
    result = CliRunner().invoke(
        evidence_cmd,
        [
            "replay-batch", str(tmp_path),
            "--repo", str(repo),
            "--output", str(tmp_path / "report.json"),
        ],
    )
    assert result.exit_code == 1
    assert "未判定" in result.output or "judged" in result.output.lower()
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["judged"] == 0
    assert report["success_rate"] is None
    assert report["by_outcome"]["environment_failure"] == 1


def test_replay_batch_json_output_is_machine_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _zip(tmp_path / "c.zip")
    repo = tmp_path / "repo"
    repo.mkdir()

    def fake_replay(work_dir: Path, target: Path, timeout: int) -> dict[str, Any]:
        return {
            "status": "replayed",
            "exit_code": 0,
            "error": "",
            "verdict": "regression_confirmed",
        }

    monkeypatch.setattr(
        "evidence.capsule_replay.run_capsule_replay", fake_replay
    )
    result = CliRunner().invoke(
        evidence_cmd,
        [
            "replay-batch", str(tmp_path),
            "--repo", str(repo),
            "--output", str(tmp_path / "report.json"),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["judged"] == 1
    assert payload["success_rate"] == 1.0


# ── verify-cert ────────────────────────────────────────────────────────────


def test_verify_cert_of_an_unsigned_document_is_digest_attestation(
    tmp_path: Path,
) -> None:
    cert = _certificate(tmp_path / "cert.json", signed=False)
    result = CliRunner().invoke(evidence_cmd, ["verify-cert", str(cert)])
    assert result.exit_code == 1  # not "valid"
    assert "digest_attestation" in result.output
    assert "NOT a signed certificate" in result.output


def test_verify_cert_of_a_signed_certificate_is_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from evidence.signing import public_key_hex

    cert = _certificate(tmp_path / "cert.json", signed=True)
    key = public_key_hex()
    result = CliRunner().invoke(
        evidence_cmd, ["verify-cert", str(cert), "--public-key", key]
    )
    assert result.exit_code == 0, result.output
    assert "Verdict:  valid" in result.output
    assert "signature" in result.output


def test_verify_cert_of_an_unreadable_file_fails(tmp_path: Path) -> None:
    broken = tmp_path / "cert.json"
    broken.write_text("{not json", encoding="utf-8")
    result = CliRunner().invoke(evidence_cmd, ["verify-cert", str(broken)])
    assert result.exit_code == 1
    assert "could not be read" in result.output


def test_verify_cert_json_output_carries_the_level(tmp_path: Path) -> None:
    cert = _certificate(tmp_path / "cert.json", signed=False)
    result = CliRunner().invoke(evidence_cmd, ["verify-cert", str(cert), "--json"])
    payload = json.loads(result.output)
    assert payload["attestation_level"] == "digest_attestation"
    assert payload["verdict"] == "unverified"


# ── scan ───────────────────────────────────────────────────────────────────


def test_scan_reports_findings_and_deletes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from storage.object_metadata import InMemoryObjectMetadataStore

    store = InMemoryObjectMetadataStore()
    monkeypatch.setattr(
        "storage.object_metadata.default_object_metadata_store",
        lambda: store,
    )
    orphan = _zip(tmp_path / "leftover.zip")
    result = CliRunner().invoke(
        evidence_cmd,
        ["scan", str(tmp_path), "--output", str(tmp_path / "scan.json")],
    )
    assert result.exit_code == 1, "findings must exit non-zero"
    assert orphan.is_file(), "the scan must not delete anything"
    report = json.loads((tmp_path / "scan.json").read_text(encoding="utf-8"))
    assert report["by_kind"]["orphan"] == 1
    assert report["clean"] is False


def test_scan_of_a_clean_chain_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from storage.object_metadata import InMemoryObjectMetadataStore

    store = InMemoryObjectMetadataStore()
    monkeypatch.setattr(
        "storage.object_metadata.default_object_metadata_store",
        lambda: store,
    )
    result = CliRunner().invoke(
        evidence_cmd,
        ["scan", str(tmp_path), "--output", str(tmp_path / "scan.json")],
    )
    assert result.exit_code == 0, result.output
    report = json.loads((tmp_path / "scan.json").read_text(encoding="utf-8"))
    assert report["clean"] is True
