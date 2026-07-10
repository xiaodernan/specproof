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
    click.echo(f"Base: {base_ref}  →  Head: {head_ref}")
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

    graph = build_phase0_graph()
    initial_state = {
        "repo_path": str(repo_path),
        "base_ref": base_ref,
        "head_ref": head_ref,
        "spec_path": str(spec_file),
        "depth": depth,
        "errors": [],
    }

    click.echo("Running verification graph...")
    final_state = graph.invoke(initial_state)

    report_path = final_state.get("report_path", "")
    findings = final_state.get("confirmed_findings", [])

    if report_path:
        click.echo(f"\nHTML Report: {report_path}")

    if findings:
        blocker_count = sum(1 for f in findings if f.get("severity") == "BLOCKER")
        major_count = sum(1 for f in findings if f.get("severity") == "MAJOR")
        click.echo(
            f"\nFindings: {len(findings)} total "
            f"({blocker_count} BLOCKER, {major_count} MAJOR)"
        )
        for f in findings:
            click.echo(f"  [{f.get('severity')}] {f.get('contract_id')}: {f.get('summary', '')}")
    else:
        click.echo("\nNo findings. All contracts passed.")

    if final_state.get("certificate"):
        click.echo("\nMerge Certificate issued.")
    else:
        click.echo("\nMerge BLOCKED — not all critical contracts verified.")
