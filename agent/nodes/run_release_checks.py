"""run_release_checks node — RELEASE tier (P5).

RELEASE = FAST + DEEP experiments + release gates:
  1. Reproducibility: the generated counterexample test is re-run on HEAD;
     the verdict must match the differential's recorded verdict (same exit
     polarity). A flip means the evidence is non-reproducible → the gate
     fails honestly.
  2. Capsule integrity: every capsule zip is opened and its manifest digest
     is recomputed and compared (evidence_digest chain).
  3. Certificate path: the caller (verify CLI) signs when VERIFIED.

Results land in state["release_results"] + release-report.json.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

from agent.state import Phase0State


def run_release_checks_node(state: Phase0State) -> dict[str, Any]:
    if state.get("depth", "FAST") != "RELEASE":
        return {"release_results": {}, "release_note": "RELEASE tier not requested"}

    results: dict[str, Any] = {"gates": {}, "passed": True}

    # Gate 1: reproducibility of the differential verdict.
    generated = state.get("generated_tests_path", "")
    head_ws = state.get("head_workspace", "")
    app_dir = state.get("app_dir", "")
    if generated and head_ws:
        app = str(Path(head_ws) / app_dir) if app_dir else head_ws
        from agent.nodes.run_deep_experiments import _run_test_via_sandbox

        rerun = _run_test_via_sandbox(app, generated)
        rerun_pass = rerun.get("exit_code") == 0
        first_pass = None
        for dr in state.get("diff_results", []):
            if dr.get("evidence_type") in ("base_pass_head_fail", "differential_execution"):
                first_pass = dr.get("head_exit_code") == 0
                break
        reproducible = first_pass is None or first_pass == rerun_pass
        results["gates"]["reproducibility"] = {
            "passed": reproducible,
            "first_head_pass": first_pass,
            "rerun_head_pass": rerun_pass,
            "rerun_mode": rerun.get("mode"),
            "error": rerun.get("error", ""),
        }
        results["passed"] = results["passed"] and reproducible
    else:
        results["gates"]["reproducibility"] = {
            "passed": False, "note": "no generated test to re-run",
        }
        results["passed"] = False

    # Gate 2: capsule integrity (manifest digest chain).
    capsule_results: list[dict[str, Any]] = []
    for capsule_path in state.get("capsules", []):
        try:
            with zipfile.ZipFile(capsule_path, "r") as zf:
                manifest = json.loads(zf.read("manifest.json"))
            stored = str(manifest.pop("manifest_digest", ""))
            canonical = json.dumps(
                manifest, sort_keys=True, separators=(",", ":")
            )
            computed = hashlib.sha256(canonical.encode()).hexdigest()
            ok = stored == "sha256:" + computed
            capsule_results.append({
                "capsule": str(capsule_path),
                "digest_ok": ok,
            })
            if not ok:
                results["passed"] = False
        except Exception as exc:  # noqa: BLE001
            capsule_results.append({"capsule": str(capsule_path), "error": str(exc)[:200]})
            results["passed"] = False
    results["gates"]["capsule_integrity"] = capsule_results

    out_dir = Path(state.get("output_dir", "reports"))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "release-report.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )
    return {
        "release_results": results,
        "release_note": (
            "RELEASE gates: " + ("PASSED" if results["passed"] else "FAILED")
        ),
    }
