"""specproof eval — Run evaluation across golden cases."""

import json
from pathlib import Path

import click

from evidence.report import render_eval_report


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
    help="Path to demo repo (for full pipeline cases)",
)
@click.option("--base", "base_ref", default="base", help="Base git ref")
@click.option("--head", "head_ref", default="head-v1", help="Head git ref")
@click.option("--output", default="eval-report.html", help="Output report path")
def eval_cmd(
    cases_dir: str,
    repo_path: str | None,
    base_ref: str,
    head_ref: str,
    output: str,
) -> None:
    """Evaluate SpecProof against golden cases.

    Runs contract compilation on each case's spec, and optionally
    the full verification pipeline for repo-based cases.
    Compares results against expected ground truth.
    """
    cases_path = Path(cases_dir)
    if not cases_path.exists():
        click.echo(f"ERROR: Cases directory not found: {cases_path}", err=True)
        raise SystemExit(1)

    case_dirs = sorted(d for d in cases_path.iterdir() if d.is_dir() and d.name.startswith("case-"))

    if not case_dirs:
        click.echo(f"No case directories found in {cases_path}")
        return

    click.echo(f"Running evaluation across {len(case_dirs)} golden cases...\n")

    from agent.nodes.compile_contracts import _parse_requirements

    # Run full pipeline on the demo repo if provided
    graph_findings: list[dict] = []
    graph_contracts: list[dict] = []
    if repo_path:
        click.echo(f"  Running full verification on {repo_path}...")
        try:
            from agent.graph import build_phase0_graph
            from agent.state import initial_state

            graph = build_phase0_graph()
            spec_file = None
            for case_dir in case_dirs:
                sf = case_dir / "spec.md"
                if sf.exists():
                    spec_file = str(sf)
                    break

            if spec_file:
                state = initial_state(
                    repo_path=repo_path,
                    base_ref=base_ref,
                    head_ref=head_ref,
                    spec_path=spec_file,
                    depth="FAST",
                )
                result = graph.invoke(state)  # type: ignore[attr-defined]
                graph_findings = result.get("confirmed_findings", [])
                graph_contracts = result.get("contracts", [])
                click.echo(
                    f"  Pipeline complete: {len(graph_findings)} findings, "
                    f"{len(graph_contracts)} contracts"
                )
        except Exception as exc:
            click.echo(f"  WARNING: Full pipeline failed: {exc}")

    results = []
    detected = 0
    total_should_detect = 0
    false_positives = 0

    for case_dir in case_dirs:
        case_spec = case_dir / "spec.md"
        ground_truth_file = case_dir / "ground-truth.json"

        if not case_spec.exists():
            click.echo(f"  SKIP {case_dir.name}: no spec.md")
            continue

        # Parse ground truth
        gt: dict = {}
        if ground_truth_file.exists():
            gt = json.loads(ground_truth_file.read_text(encoding="utf-8"))

        case_name = case_dir.name
        should_detect = gt.get("should_detect", False)
        expected_severity = gt.get("expected_severity", "UNKNOWN")
        expected_contract = gt.get("expected_contract")
        expected_evidence = gt.get("expected_evidence_type", "UNKNOWN")
        min_findings = gt.get("expected_min_findings", 1)

        if should_detect:
            total_should_detect += 1

        # ── Run contract compilation on case spec ──
        spec_text = case_spec.read_text(encoding="utf-8")
        contracts = _parse_requirements(spec_text)
        contract_types = {c["checker_type"] for c in contracts}

        # ── Cross-check against graph findings ──
        matched_findings = []
        for f in graph_findings:
            fid = f.get("contract_id", "")
            ftype = f.get("type", "")

            # Match by contract ID or evidence type
            matches_contract = expected_contract and fid == expected_contract
            matches_type = expected_evidence and expected_evidence in ftype
            matches_fid = expected_evidence and expected_evidence in fid.lower()
            if matches_contract or matches_type or matches_fid:
                matched_findings.append(f)

        # ── Determine evaluation result ──
        case_detected = len(matched_findings) >= min_findings if should_detect else False
        found_any = len(matched_findings) > 0

        if should_detect and case_detected:
            detected += 1
            verdict_icon = "PASS"
        elif should_detect and found_any:
            detected += 1
            verdict_icon = "PARTIAL"
        elif should_detect and not found_any:
            verdict_icon = "MISS"
        elif not should_detect and found_any:
            false_positives += 1
            verdict_icon = "FALSE_POSITIVE"
        else:
            verdict_icon = "PASS"

        matched_severities = {f.get("severity") for f in matched_findings}

        result = {
            "case": case_name,
            "verdict": verdict_icon,
            "should_detect": should_detect,
            "expected_severity": expected_severity,
            "expected_evidence": expected_evidence,
            "matched_findings": len(matched_findings),
            "matched_severities": (
                ", ".join(sorted(matched_severities)) if matched_severities else "—"  # type: ignore[arg-type]
            ),
            "contracts_found": ", ".join(sorted(contract_types)),
            "expected_contract": expected_contract or "—",
        }
        results.append(result)

        icon = {"PASS": "+", "PARTIAL": "~", "MISS": "!!", "FALSE_POSITIVE": "FP"}[verdict_icon]
        click.echo(
            f"  [{icon}] {case_name}: {verdict_icon} "
            f"(matched {len(matched_findings)} findings, "
            f"contracts: {contract_types})"
        )

    # ── Summary statistics ──
    total_cases = len(results)
    precision = (
        detected / (detected + false_positives) * 100 if (detected + false_positives) > 0 else 100.0
    )
    recall = detected / total_should_detect * 100 if total_should_detect > 0 else 100.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    click.echo(f"\n{'=' * 50}")
    click.echo("Evaluation Results")
    click.echo(f"{'=' * 50}")
    click.echo(f"Total cases:        {total_cases}")
    click.echo(f"Should detect:      {total_should_detect}")
    click.echo(f"Detected:           {detected}")
    click.echo(f"False positives:    {false_positives}")
    click.echo(f"Precision:          {precision:.1f}%")
    click.echo(f"Recall:             {recall:.1f}%")
    click.echo(f"F1 Score:           {f1:.1f}%")

    # Write HTML report
    html = render_eval_report(results)
    Path(output).write_text(html, encoding="utf-8")
    click.echo(f"\nHTML report written to {output}")
