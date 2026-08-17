"""specproof verify — Run a verification job (Phase 0 CLI).

Honesty contract (v2):
- VERDICT FAILED    when the pipeline recorded errors
- VERDICT BLOCKED   when BLOCKER findings were confirmed
- VERDICT NEEDS REVIEW when MAJOR/MINOR findings or unverified contracts remain
- VERDICT VERIFIED  only when every contract passed with evidence
- A Merge Certificate is issued only for VERIFIED; otherwise a Rejection
  Notice JSON is written alongside the HTML report.
"""

import subprocess
import uuid
from pathlib import Path

import click


@click.command("verify")
@click.option("--repo", required=True, help="Path to repository")
@click.option(
    "--base", "base_ref", required=True, help="Base ref (branch/tag/commit)"
)
@click.option(
    "--head", "head_ref", required=True, help="Head ref (branch/tag/commit)"
)
@click.option("--spec", "spec_path", required=True, help="Path to requirement spec")
@click.option(
    "--depth",
    type=click.Choice(["FAST"]),
    default="FAST",
    help="Verification depth (Phase 0 supports FAST only)",
)
@click.option(
    "--output-dir", default="./reports", help="Output directory for reports"
)
@click.option(
    "--app-dir", "app_dir", default="",
    help="Subdirectory inside the repo that holds pom.xml (empty = repo root)"
)
def verify(
    repo: str,
    base_ref: str,
    head_ref: str,
    spec_path: str,
    depth: str,
    output_dir: str,
    app_dir: str,
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
        click.echo(
            f"ERROR: Repository path does not exist: {repo_path}", err=True
        )
        raise SystemExit(1)

    spec_file = Path(spec_path).resolve()
    if not spec_file.exists():
        click.echo(
            f"ERROR: Spec file does not exist: {spec_file}", err=True
        )
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
    state["output_dir"] = str(output_path)
    state["app_dir"] = app_dir

    click.echo("\nRunning verification pipeline...")
    final_state = graph.invoke(state)

    # ── Results ──
    report_path = final_state.get("report_path", "")
    findings = final_state.get("confirmed_findings", [])
    contracts = final_state.get("contracts", [])
    contract_results = final_state.get("contract_results", [])
    matrix = final_state.get("matrix", {})
    capsules = final_state.get("capsules", [])
    errors = final_state.get("errors", [])

    results_by_contract = {
        r.get("contract_id"): r for r in contract_results
    }
    merged_contracts = []
    for c in contracts:
        merged = dict(c)
        res = results_by_contract.get(c.get("id"), {})
        merged["result"] = res.get("result", "UNVERIFIED")
        merged["evidence_ref"] = res.get("evidence_ref")
        merged_contracts.append(merged)

    # ── Summary ──
    click.echo(f"\n{'=' * 60}")
    click.echo("VERIFICATION COMPLETE")
    click.echo(f"{'=' * 60}")

    if errors:
        click.echo(f"\nErrors ({len(errors)}):")
        for err in errors:
            click.echo(f"  ! {err}")

    if contracts:
        click.echo(f"\nContracts compiled: {len(contracts)}")
        for c in merged_contracts:
            cid = c.get("id", "?")
            ctype = c.get("checker_type", "?")
            status = c.get("result", "UNVERIFIED")
            icon = "+" if status == "PASS" else "!" if status == "FAIL" else "?"
            click.echo(f"  [{icon}] {cid} ({ctype}) -> {status}")
    else:
        click.echo("\nNo contracts compiled.")

    if findings:
        blocker_count = sum(
            1 for f in findings if f.get("severity") == "BLOCKER"
        )
        major_count = sum(
            1 for f in findings if f.get("severity") == "MAJOR"
        )
        minor_count = sum(
            1 for f in findings if f.get("severity") == "MINOR"
        )
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
            click.echo(
                f"  [{sev}] {cid} (confidence: {conf:.0%}, "
                f"evidence: {evidence})"
            )
            click.echo(f"       {desc}")
    else:
        click.echo("\nNo findings confirmed.")

    if matrix:
        passed = matrix.get("passed", 0)
        failed = matrix.get("failed", 0)
        unverified = matrix.get("unverified", 0)
        total = len(matrix.get("rows", []))
        click.echo(
            f"\nMatrix: {total} rows | "
            f"+{passed} passed | "
            f"-{failed} failed | "
            f"?{unverified} unverified"
        )

    if capsules:
        click.echo(f"\nBug Capsules: {len(capsules)} generated")
        for cap in capsules:
            click.echo(f"  {cap}")

    # ── Honest verdict ──
    blocker_count = sum(
        1 for f in findings if f.get("severity") == "BLOCKER"
    )
    if errors:
        verdict = "FAILED"
    elif blocker_count > 0:
        verdict = "BLOCKED"
    elif findings:
        verdict = "NEEDS REVIEW"
    elif matrix.get("unverified", 0) > 0 or not contracts:
        verdict = "NEEDS REVIEW (verification incomplete)"
    else:
        verdict = "VERIFIED"

    click.echo(f"\n{'─' * 60}")
    click.echo(f"VERDICT: {verdict}")
    click.echo(f"{'─' * 60}")

    if report_path:
        click.echo(f"\nHTML Report: {report_path}")

    # ── Certificate / Rejection Notice ──
    from evidence.certificate import build_rejection_notice, issue_certificate

    head_sha = ""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", head_ref],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode == 0:
            head_sha = proc.stdout.strip()
    except Exception:
        head_sha = ""

    requirement_text = Path(spec_file).read_text(encoding="utf-8")
    evidence_digests = [
        f.get("evidence_digest") for f in findings
        if f.get("evidence_digest")
    ]

    if verdict == "VERIFIED":
        certificate = issue_certificate(
            repository=str(repo_path),
            commit_sha=head_sha,
            requirements_text=requirement_text,
            contracts=merged_contracts,
            evidence_digests=evidence_digests,
        )
        if certificate is not None:
            cert_path = output_path / f"merge-certificate-{job_id[:8]}.json"
            cert_path.write_text(certificate.to_json(), encoding="utf-8")
            click.echo(f"Merge Certificate: ISSUED -> {cert_path}")
        else:
            click.echo("Merge Certificate: NOT ISSUED (no fully verified contracts)")
    else:
        reasons = [
            f.get("description", "") for f in findings[:5]
        ] or errors[:5] or ["contracts unverified"]
        notice = build_rejection_notice(
            repository=str(repo_path),
            commit_sha=head_sha,
            requirements_text=requirement_text,
            contracts=merged_contracts,
            reasons=reasons,
        )
        notice_path = output_path / f"rejection-notice-{job_id[:8]}.json"
        notice_path.write_text(notice.to_json(), encoding="utf-8")
        click.echo(f"Rejection Notice written -> {notice_path}")
