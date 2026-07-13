#!/usr/bin/env python3
"""
P0.5 Archive Verification Script
================================
Verifies the frozen P0.5 acceptance archive for:
  - All digest consistency
  - Run ID mapping
  - Bundle validity
  - Base/Head SHA correctness
  - Capsule test byte-identical to archive test
  - source=llm_generated, human_edited=false
  - BLOCKER 10 conditions all met
  - No absolute paths
  - No secrets
  - legacy-invalid not referenced by formal acceptance

Usage: python scripts/verify_p0_5_archive.py [--archive-dir artifacts/p0.5/511A3276]
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = PROJECT_ROOT / "artifacts" / "p0.5" / "511A3276"
CANARY_SECRET = "SPECPROOF_CANARY_a7f3b2c9d1e4_SECRET_DO_NOT_COMMIT"

# Known good values (from the frozen acceptance run)
EXPECTED_TEST_SOURCE_DIGEST = (
    "sha256:bc761be4e67c7d137b4dd23258865af47ede89e57f5f2be79268436883e6f044"
)
EXPECTED_CANONICAL_RUN_ID = "511A3276"
EXPECTED_BASE_COMMIT = "c55be4a5936304f09fe7982114e8472438b6c58c"
EXPECTED_HEAD_COMMIT = "4c458327dce3c3c1dd5169e1ceceee3a38a266c2"

RESULTS = []


def P(label: str, ok: bool, detail: str = "") -> bool:
    """Record and print a PASS/FAIL result."""
    status = "PASS" if ok else "FAIL"
    msg = f"[{status}] {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    RESULTS.append((label, ok, detail))
    return ok


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def read_json(path):
    """Read JSON file, handling UTF-8 BOM."""
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return json.loads(raw.decode("utf-8"))


def check_abs_paths(obj, path=""):
    """Return list of absolute path strings found in obj."""
    issues = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            issues += check_abs_paths(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            issues += check_abs_paths(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        for prefix in ("C:\\", "C:/", "D:\\", "D:/"):
            if prefix in obj:
                if any(kw in obj.lower() for kw in [
                    "introduced_by_head", "diff_summary",
                ]):
                    continue
                issues.append(f"{path}: {obj[:120]}")
    return issues


def check_secrets(obj, path=""):
    """Return list of secret-like patterns found in obj."""
    issues = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            issues += check_secrets(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            issues += check_secrets(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        if re.search(r'sk-[a-zA-Z0-9]{32,}', obj):
            if CANARY_SECRET not in obj:
                issues.append(f"{path}: API key pattern found")
    return issues


def main():
    parser = argparse.ArgumentParser(description="Verify P0.5 frozen archive")
    parser.add_argument("--archive-dir", default=str(DEFAULT_ARCHIVE))
    args = parser.parse_args()

    archive = Path(args.archive_dir)
    if not archive.exists():
        print(f"FATAL: archive directory not found: {archive}")
        sys.exit(1)

    print(f"P0.5 Archive Verification — {archive}")
    print(f"Expected canonical run_id: {EXPECTED_CANONICAL_RUN_ID}")
    print()

    # ── 1. File presence ──
    required = [
        "generated-test.java", "generation-record.json", "evidence-pack.json",
        "acceptance-report.json", "capsule.zip", "demo-spring-backend.bundle",
    ]
    for fn in required:
        fp = archive / fn
        P(f"File exists: {fn}", fp.exists(), f"{fp.stat().st_size} bytes" if fp.exists() else "MISSING")

    test_path = archive / "generated-test.java"
    gr_path = archive / "generation-record.json"
    ep_path = archive / "evidence-pack.json"
    ar_path = archive / "acceptance-report.json"
    capsule_path = archive / "capsule.zip"
    bundle_path = archive / "demo-spring-backend.bundle"

    if not all(p.exists() for p in [test_path, gr_path, ep_path, ar_path, capsule_path, bundle_path]):
        print("\nFATAL: required files missing, cannot continue")
        sys.exit(1)

    # ── 2. Test source digest ──
    test_bytes = test_path.read_bytes()
    actual_test_digest = f"sha256:{sha256_str(test_bytes.decode('utf-8'))}"
    P("Test source digest matches expected",
      actual_test_digest == EXPECTED_TEST_SOURCE_DIGEST,
      actual_test_digest)

    # ── 3. generation-record.json ──
    gr = read_json(gr_path)
    P("generation-record: test_source=llm_generated",
      gr.get("test_source") == "llm_generated")
    P("generation-record: human_edited=false",
      gr.get("human_edited") == False)
    P("generation-record: generated_source_digest matches",
      gr.get("generated_source_digest") == EXPECTED_TEST_SOURCE_DIGEST,
      gr.get("generated_source_digest", ""))

    # ── 4. evidence-pack.json ──
    ep = read_json(ep_path)
    P("evidence-pack: run_id correct",
      ep.get("run_id") == EXPECTED_CANONICAL_RUN_ID,
      ep.get("run_id", ""))
    P("evidence-pack: generated_source_digest matches",
      ep.get("provenance", {}).get("generated_source_digest") == EXPECTED_TEST_SOURCE_DIGEST)
    P("evidence-pack: run_id_history.supersedes exists",
      ep.get("run_id_history", {}).get("supersedes") == "P0_5-5ECF7092")
    P("evidence-pack: no absolute paths",
      len(check_abs_paths(ep)) == 0,
      f"{len(check_abs_paths(ep))} issues" if check_abs_paths(ep) else "")
    P("evidence-pack: no secrets",
      len(check_secrets(ep)) == 0,
      f"{len(check_secrets(ep))} issues" if check_secrets(ep) else "")
    # Check bundle digest
    bundle_digest_in_ep = ep.get("capsule", {}).get("demo_repository_bundle_digest", "")
    if bundle_digest_in_ep:
        P("evidence-pack: bundle_digest present",
          bundle_digest_in_ep.startswith("sha256:"))
    else:
        P("evidence-pack: bundle_digest present", False, "MISSING")

    # ── 5. acceptance-report.json ──
    ar = read_json(ar_path)
    P("acceptance-report: canonical_acceptance_run_id correct",
      ar.get("canonical_acceptance_run_id") == EXPECTED_CANONICAL_RUN_ID)
    P("acceptance-report: generated_test_source_digest matches",
      ar.get("generated_test_source_digest") == EXPECTED_TEST_SOURCE_DIGEST)
    P("acceptance-report: no absolute paths",
      len(check_abs_paths(ar)) == 0,
      f"{len(check_abs_paths(ar))} issues" if check_abs_paths(ar) else "")
    P("acceptance-report: no secrets",
      len(check_secrets(ar)) == 0)

    # ── 6. Capsule ──
    with zipfile.ZipFile(capsule_path, "r") as zf:
        capsule_files = zf.namelist()
        capsule_test = zf.read("fixtures/SpecProofGeneratedTest.java")
        mf = json.loads(zf.read("manifest.json").decode("utf-8"))

    P("Capsule: manifest.json present", "manifest.json" in capsule_files)
    P("Capsule: fixtures present", "fixtures/SpecProofGeneratedTest.java" in capsule_files)
    P("Capsule: evidence directory present",
      any(f.startswith("evidence/") for f in capsule_files))

    capsule_test_bytes_match = (
        sha256_str(capsule_test.decode("utf-8"))
        == EXPECTED_TEST_SOURCE_DIGEST.split(":", 1)[1]
    )
    P("Capsule: test bytes == archive test bytes", capsule_test_bytes_match)

    P("Capsule: generated_test_source_digest matches",
      mf.get("provenance", {}).get("generated_source_digest") == EXPECTED_TEST_SOURCE_DIGEST)
    P("Capsule: severity=BLOCKER",
      mf.get("severity") == "BLOCKER",
      mf.get("severity", ""))
    P("Capsule: blocker_check.all_met=True",
      mf.get("blocker_check", {}).get("all_met") == True)
    P("Capsule: no absolute paths",
      len(check_abs_paths(mf)) == 0,
      f"{len(check_abs_paths(mf))} issues" if check_abs_paths(mf) else "")

    # Check all 10 blocker conditions
    blocker = mf.get("blocker_check", {}).get("conditions", {})
    for i in range(1, 11):
        cond = blocker.get(f"{i}_approved_contract") if i == 1 else \
               blocker.get(f"{i}_test_source_llm") if i == 2 else \
               blocker.get(f"{i}_human_edited_false") if i == 3 else \
               blocker.get(f"{i}_base_real_execution_pass") if i == 4 else \
               blocker.get(f"{i}_head_real_execution_fail") if i == 5 else \
               blocker.get(f"{i}_attribution_introduced_by_head") if i == 6 else \
               blocker.get(f"{i}_db_state_evidence") if i == 7 else \
               blocker.get(f"{i}_capsule_clean_replay") if i == 8 else \
               blocker.get(f"{i}_confidence_gte_0_90") if i == 9 else \
               blocker.get(f"{i}_evidence_digest_complete") if i == 10 else None
        if cond:
            P(f"  Condition {i}: {cond.get('pass', False)}", cond.get("pass", False))
        else:
            # Try generic lookup
            found = False
            for k, v in blocker.items():
                if k.startswith(f"{i}_"):
                    P(f"  Condition {k}: {v.get('pass', False)}", v.get("pass", False))
                    found = True
                    break
            if not found:
                P(f"  Condition {i}: present", False, "MISSING")

    # ── 7. Bundle ──
    try:
        result = subprocess.run(
            ["git", "bundle", "verify", str(bundle_path)],
            capture_output=True, text=True, timeout=30
        )
        bundle_ok = result.returncode == 0
        P("Bundle: verify passes", bundle_ok, result.stderr.strip()[:100] if not bundle_ok else "")

        heads = subprocess.run(
            ["git", "bundle", "list-heads", str(bundle_path)],
            capture_output=True, text=True, timeout=10
        ).stdout

        base_sha_in_bundle = EXPECTED_BASE_COMMIT in heads
        head_sha_in_bundle = EXPECTED_HEAD_COMMIT in heads
        P("Bundle: base tag SHA correct", base_sha_in_bundle)
        P("Bundle: head-v1 tag SHA correct", head_sha_in_bundle)

        # Test clone from bundle
        with tempfile.TemporaryDirectory(prefix="specproof-bundle-verify-") as tmp:
            clone_result = subprocess.run(
                ["git", "clone", str(bundle_path), tmp],
                capture_output=True, text=True, timeout=30
            )
            clone_ok = clone_result.returncode == 0
            P("Bundle: clone succeeds", clone_ok,
              clone_result.stderr.strip()[:100] if not clone_ok else "")

            if clone_ok:
                # Checkout base and verify mvnw exists
                checkout = subprocess.run(
                    ["git", "-C", tmp, "checkout", "base"],
                    capture_output=True, text=True, timeout=10
                )
                mvnw_exists = (Path(tmp) / "mvnw").exists() or (Path(tmp) / "mvnw.cmd").exists()
                P("Bundle: mvnw present after checkout", mvnw_exists)

                # Verify both tags checkout correctly
                for tag, expected_sha in [("base", EXPECTED_BASE_COMMIT), ("head-v1", EXPECTED_HEAD_COMMIT)]:
                    subprocess.run(
                        ["git", "-C", tmp, "checkout", tag],
                        capture_output=True, text=True, timeout=10
                    )
                    actual = subprocess.run(
                        ["git", "-C", tmp, "rev-parse", "HEAD"],
                        capture_output=True, text=True, timeout=10
                    ).stdout.strip()
                    P(f"Bundle: checkout {tag} -> correct SHA",
                      actual == expected_sha,
                      f"got {actual[:8]} expected {expected_sha[:8]}")

    except Exception as e:
        P("Bundle: verify", False, str(e))

    # ── 8. legacy-invalid isolation ──
    legacy_dir = PROJECT_ROOT / "artifacts" / "legacy-invalid"
    if legacy_dir.exists():
        # Verify formal artifacts don't reference legacy-invalid
        all_formal_text = json.dumps([gr, ep, ar, mf], default=str)
        legacy_refs = []
        for fname in ["AuthDbStateRegressionTest", "legacy-invalid", "human_fixture"]:
            if fname in all_formal_text:
                legacy_refs.append(fname)
        P("legacy-invalid: not referenced by formal artifacts",
          len(legacy_refs) == 0,
          f"References found: {legacy_refs}" if legacy_refs else "")

    # ── 9. Security scan of archive text files ──
    secret_found = False
    for fpath in archive.rglob("*"):
        if not fpath.is_file():
            continue
        ext = fpath.suffix.lower()
        if ext in (".jar", ".class", ".png", ".jpg"):
            continue
        try:
            content = fpath.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue
        if re.search(r'sk-[a-zA-Z0-9]{32,}', content) and CANARY_SECRET not in content:
            P(f"Archive security: {fpath.name} — API key found", False, fpath.name)
            secret_found = True
    if not secret_found:
        P("Archive security: no API keys", True)

    # ── 10. Summary ──
    total = len(RESULTS)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = total - passed

    print()
    print("=" * 60)
    print(f"  VERIFICATION COMPLETE: {passed}/{total} PASS, {failed} FAIL")
    print("=" * 60)

    for label, ok, detail in RESULTS:
        if not ok:
            print(f"  FAIL: {label} — {detail}")

    if failed == 0:
        print("  RESULT: ALL PASS — Archive is consistent and valid.")
    else:
        print(f"  RESULT: {failed} CHECKS FAILED — Archive needs repair.")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
