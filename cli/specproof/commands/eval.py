
"""specproof eval — Run evaluation across golden cases (v2).

Each case runs the FULL verification pipeline against its own scenario refs
(scenario.json), with the LLM disabled by default so numbers are
reproducible. Findings are matched against ground truth by contract id.
Worktrees created by the pipeline are cleaned up after each case.

Each case record carries duration_ms: whole-pipeline wall clock measured
around the graph invocation. The Phase 0 graph exposes no per-stage
timestamps, so timings are honest at the case level only (SLO stats are
computed by scripts/bench_latency.py).
"""
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import click

from evidence.report import render_eval_report


def _cleanup_worktrees(repo: str, final: dict[str, Any]) -> None:
    from contextlib import suppress

    for key in ("base_workspace", "head_workspace"):
        ws = final.get(key, "")
        if not ws:
            continue
        with suppress(Exception):
            subprocess.run(
                ["git", "-C", repo, "worktree", "remove", "--force", ws],
                capture_output=True, text=True, timeout=60,
            )


@click.command("eval")
@click.option(
    "--cases",
    "cases_dir",
    required=True,
    help="Path to golden-cases directory",
)
@click.option(
    "--repo",
    "repo_path",
    default=None,
    help="Path to demo repo (full-pipeline cases need it)",
)
@click.option("--output", default="docs/eval/eval-report.html", help="Output report path")
@click.option(
    "--llm/--no-llm",
    "use_llm",
    default=False,
    help="Enable LLM-assisted nodes (default: deterministic only)",
)
def eval_cmd(
    cases_dir: str,
    repo_path: str | None,
    output: str,
    use_llm: bool,
) -> None:
    """Evaluate SpecProof against golden cases.

    Runs the full verification pipeline per case using that case's
    scenario.json refs, then compares confirmed findings with the
    ground truth (contract-id matching).
    """
    cases_path = Path(cases_dir)
    if not cases_path.exists():
        click.echo(f"ERROR: Cases directory not found: {cases_path}", err=True)
        raise SystemExit(1)

    if not repo_path:
        click.echo("ERROR: --repo is required for pipeline evaluation", err=True)
        raise SystemExit(1)
    repo_resolved = str(Path(repo_path).resolve())

    case_dirs = sorted(
        d for d in cases_path.iterdir()
        if d.is_dir() and d.name.startswith("case-")
    )

    if not case_dirs:
        click.echo(f"No case directories found in {cases_path}")
        return

    click.echo(f"Running evaluation across {len(case_dirs)} golden cases "
               f"(LLM: {'on' if use_llm else 'off'})...\n")

    from agent.graph import build_phase0_graph
    from agent.state import initial_state

    graph = build_phase0_graph()

    results: list[dict[str, Any]] = []
    detected = 0
    total_should_detect = 0
    false_positives = 0

    for case_dir in case_dirs:
        spec_file = case_dir / "spec.md"
        gt_file = case_dir / "ground-truth.json"
        sc_file = case_dir / "scenario.json"

        if not spec_file.exists():
            click.echo(f"  SKIP {case_dir.name}: no spec.md")
            continue

        gt: dict[str, Any] = {}
        if gt_file.exists():
            gt = json.loads(gt_file.read_text(encoding="utf-8"))
        scenario: dict[str, Any] = {}
        if sc_file.exists():
            scenario = json.loads(sc_file.read_text(encoding="utf-8"))

        base_ref = scenario.get("base_ref", "base")
        head_ref = scenario.get("head_ref", "head-v1")
        should_detect = gt.get("should_detect", False)
        expected_contract = gt.get("expected_contract")
        expected_evidence = gt.get("expected_evidence_type", "UNKNOWN")
        min_findings = gt.get("expected_min_findings", 1)

        if should_detect:
            total_should_detect += 1

        click.echo(
            f"\n=== {case_dir.name} (base={base_ref}, head={head_ref}) ==="
        )

        state = initial_state(
            repo_path=repo_resolved,
            base_ref=base_ref,
            head_ref=head_ref,
            spec_path=str(spec_file),
            depth="FAST",
        )
        state["use_llm"] = use_llm
        state["output_dir"] = str(Path("reports").resolve())
        state["app_dir"] = "demo/spring-backend"

        final: dict[str, Any] = {}
        # Case-level timing: wall clock around the whole pipeline. The graph
        # exposes no per-stage timestamps, so duration_ms is honest at the
        # case level only (see scripts/bench_latency.py).
        started_at = time.perf_counter()
        try:
            final = graph.invoke(state)
        except Exception as exc:  # noqa: BLE001
            click.echo(f"  WARNING: pipeline failed for {case_dir.name}: {exc}")
        duration_ms = max(0, round((time.perf_counter() - started_at) * 1000))

        findings = final.get("confirmed_findings", [])

        matched: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for f in findings:
            fid = f.get("contract_id", "")
            if expected_contract and fid == expected_contract or expected_evidence and (
                expected_evidence in f.get("evidence_type", "")
                or expected_evidence in fid.lower()
            ):
                matched.append(f)
        deduped = []
        for f in matched:
            fid = f.get("id", "")
            if fid not in seen_ids:
                seen_ids.add(fid)
                deduped.append(f)
        matched = deduped

        if should_detect:
            if len(matched) >= min_findings:
                detected += 1
                verdict = "PASS"
            elif matched:
                detected += 1
                verdict = "PARTIAL"
            else:
                verdict = "MISS"
        else:
            # Negative cases must produce ZERO confirmed findings of any
            # kind — not just zero matches against the expected contract
            # (split.json: max_findings = 0).
            if findings:
                false_positives += 1
                verdict = "FALSE_POSITIVE"
            else:
                verdict = "PASS"

        matched_severities = sorted(
            {str(f.get("severity") or "") for f in matched}
        )
        contracts_found = sorted(
            {str(f.get("contract_id") or "") for f in findings}
        )

        results.append({
            "case": case_dir.name,
            "verdict": verdict,
            "should_detect": should_detect,
            "duration_ms": duration_ms,
            "expected_severity": gt.get("expected_severity"),
            "expected_evidence": expected_evidence,
            "matched_findings": len(matched),
            "matched_severities": ", ".join(matched_severities) or "—",
            "contracts_found": ", ".join(contracts_found),
            "expected_contract": expected_contract or "—",
        })
        click.echo(
            f"  [{verdict}] matched {len(matched)} finding(s), "
            f"contracts found: {contracts_found} ({duration_ms} ms)"
        )

        _cleanup_worktrees(repo_resolved, final)

    # ── Summary statistics ──
    precision = (
        detected / (detected + false_positives) * 100
        if (detected + false_positives) > 0 else 100.0
    )
    recall = (
        detected / total_should_detect * 100
        if total_should_detect > 0 else 100.0
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0 else 0.0
    )

    click.echo(f"\n{'=' * 50}")
    click.echo("Evaluation Results")
    click.echo(f"{'=' * 50}")
    click.echo(f"Total cases:        {len(results)}")
    click.echo(f"Should detect:      {total_should_detect}")
    click.echo(f"Detected:           {detected}")
    click.echo(f"False positives:    {false_positives}")
    click.echo(f"Precision:          {precision:.1f}%")
    click.echo(f"Recall:             {recall:.1f}%")
    click.echo(f"F1 Score:           {f1:.1f}%")

    html = render_eval_report(results)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    click.echo(f"\nHTML report written to {out}")

    # Machine-readable sidecar consumed by the specproof baseline command
    # (P6: "model reads the diff" comparison) and CI gates.
    sidecar = out.with_suffix(".results.json")
    sidecar.write_text(
        json.dumps(
            {
                "total_cases": len(results),
                "should_detect": total_should_detect,
                "detected": detected,
                "false_positives": false_positives,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "timing_note": (
                    "Per-case duration_ms is whole-pipeline wall clock measured "
                    "around the graph invocation; the Phase 0 graph exposes no "
                    "per-stage timestamps, so stage-level timings are not available."
                ),
                "cases": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    click.echo(f"Results JSON written to {sidecar}")
