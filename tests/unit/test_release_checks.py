"""RELEASE tier tests — reproducibility + capsule integrity gates (unit)."""

import json
import zipfile

from agent.nodes.run_release_checks import run_release_checks_node


def _capsule(tmp_path, digest_ok: bool) -> str:
    import hashlib

    manifest = {"finding_id": "X", "severity": "MAJOR"}
    canonical = json.dumps(
        manifest, sort_keys=True, separators=(",", ":")
    ).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    if digest_ok:
        manifest["manifest_digest"] = "sha256:" + digest
    path = tmp_path / "capsule-X.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("finding.json", "{}")
    return str(path)


def test_release_skipped_for_fast():
    state = {"depth": "FAST"}
    out = run_release_checks_node(state)
    assert out["release_results"] == {}
    assert "not requested" in out["release_note"]


def test_capsule_integrity_gate(tmp_path):
    good = _capsule(tmp_path, digest_ok=True)
    state = {
        "depth": "RELEASE",
        "capsules": [good],
        "generated_tests_path": "",
        "head_workspace": "",
        "app_dir": "",
        "diff_results": [],
        "output_dir": str(tmp_path),
    }
    out = run_release_checks_node(state)
    gates = out["release_results"]["gates"]
    assert gates["capsule_integrity"][0]["digest_ok"] is True
    # Reproducibility gate fails honestly when no test exists.
    assert gates["reproducibility"]["passed"] is False


def test_tampered_capsule_fails_gate(tmp_path):
    bad = _capsule(tmp_path, digest_ok=False)
    state = {
        "depth": "RELEASE",
        "capsules": [bad],
        "generated_tests_path": "",
        "head_workspace": "",
        "app_dir": "",
        "diff_results": [],
        "output_dir": str(tmp_path),
    }
    out = run_release_checks_node(state)
    assert out["release_results"]["passed"] is False
    assert out["release_results"]["gates"]["capsule_integrity"][0]["digest_ok"] is False
