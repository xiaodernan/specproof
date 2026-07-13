"""specproof verify — Run a verification job (Phase 0 CLI)."""

import uuid
from pathlib import Path

import click


@click.command("verify")
@click.option("--repo", required=True, help="Path to repository")
@click.option("--base", "base_ref", required=True, help="Base ref (branch/tag/commit)")
@click.option("--head", "head_ref", required=True, help="Head ref (branch/tag/commit)")
@click.option("--spec", "spec_path", required=True, help="Path to requirement spec")
@click.option(
    "--depth",
    type=click.Choice(["FAST"]),
    default="FAST",
    help="Verification depth (Phase 0 supports FAST only)",
)
@click.option("--output-dir", default="./reports", help="Output directory for reports")
def verify(
    repo: str,
    base_ref: str,
    head_ref: str,
    spec_path: str,
    depth: str,
    output_dir: str,
) -> None:
    """Run a verification job on a PR / branch pair.

    Compiles requirements into contracts, runs differential execution,
    and produces a Requirement-to-Evidence Matrix with HTML report.
    """
    job_id = str(uuid.uuid4())
    click.echo(f"Job ID: {job_id}")
    click.echo(f"Repository: {repo}")
    click.echo(f"Base: {base_ref}  ->  Head: {head_ref}")
    click.echo(f"Spec: {spec_path}")
    click.echo(f"Depth: {depth}")

    repo_path = Path(repo).resolve()
    if not repo_path.exists():
        click.echo(f"ERROR: Repository path does not exist: {repo_path}", err=True)
        raise SystemExit(1)

    spec_file = Path(spec_path).resolve()
    if not spec_file.exists():
        click.echo(f"ERROR: Spec file does not exist: {spec_file}", err=True)
        raise SystemExit(1)

    output_path = Path(output_dir).resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    from agent.graph import build_phase0_graph
    from agent.state import initial_state

    graph = build_phase0_graph()
    state = initial_state(
        repo_path=str(repo_path),
        base_ref=base_ref,
        head_ref=head_ref,
        spec_path=str(spec_file),
        depth=depth,
    )

    click.echo("\nRunning verification pipeline...")
    final_state = graph.invoke(state)  # type: ignore[attr-defined]

    # ── Results ──
    report_path = final_state.get("report_path", "")
    findings = final_state.get("confirmed_findings", [])
    contracts = final_state.get("contracts", [])
    matrix = final_state.get("matrix", {})
    capsules = final_state.get("capsules", [])
    errors = final_state.get("errors", [])

    # ── Summary ──
    click.echo(f"\n{'=' * 60}")
    click.echo("VERIFICATION COMPLETE")
    click.echo(f"{'=' * 60}")

    # Errors
    if errors:
        click.echo(f"\nErrors ({len(errors)}):")
        for err in errors:
            click.echo(f"  ! {err}")

    # Contracts
    if contracts:
        click.echo(f"\nContracts compiled: {len(contracts)}")
        for c in contracts:
            cid = c.get("id", "?")
            ctype = c.get("checker_type", "?")
            status = c.get("result", "UNVERIFIED")
            icon = "+" if status == "PASS" else "!" if status == "FAIL" else "?"
            click.echo(f"  [{icon}] {cid} ({ctype}) -> {status}")

    # Findings
    if findings:
        blocker_count = sum(1 for f in findings if f.get("severity") == "BLOCKER")
        major_count = sum(1 for f in findings if f.get("severity") == "MAJOR")
        minor_count = sum(1 for f in findings if f.get("severity") == "MINOR")
        click.echo(
            f"\nFindings: {len(findings)} total "
            f"({blocker_count} BLOCKER, {major_count} MAJOR, "
            f"{minor_count} MINOR)"
        )
        for f in findings:
            sev = f.get("severity", "?")
            cid = f.get("contract_id", "")
            desc = f.get("description", "")
            conf = f.get("confidence", 0)
            evidence = f.get("evidence_type", "")
            click.echo(f"  [{sev}] {cid} (confidence: {conf:.0%}, evidence: {evidence})")
            click.echo(f"       {desc}")
    else:
        click.echo("\nNo findings detected.")

    # Matrix summary
    if matrix:
        passed = matrix.get("passed", 0)
        failed = matrix.get("failed", 0)
        total = len(matrix.get("rows", []))
        click.echo(f"\nMatrix: {total} rows | +{passed} passed | -{failed} failed")

    # Capsules
    if capsules:
        click.echo(f"\nBug Capsules: {len(capsules)} generated")
        for cap in capsules:
            click.echo(f"  {cap}")

    # Verdict
    if findings:
        blocker_count = sum(1 for f in findings if f.get("severity") == "BLOCKER")
        verdict = "BLOCKED" if blocker_count > 0 else "NEEDS REVIEW"
    else:
        verdict = "VERIFIED"

    click.echo(f"\n{'─' * 60}")
    click.echo(f"VERDICT: {verdict}")
    click.echo(f"{'─' * 60}")

    if report_path:
        click.echo(f"\nHTML Report: {report_path}")

    if final_state.get("certificate"):
        click.echo("Merge Certificate: ISSUED")
