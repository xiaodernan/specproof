
"""specproof verify — Run a verification job (Phase 0 CLI).

Honesty contract (v2):
- VERDICT FAILED    when the pipeline recorded errors
- VERDICT BLOCKED   when BLOCKER findings were confirmed
- VERDICT NEEDS REVIEW when MAJOR/MINOR findings or unverified contracts remain
- VERDICT VERIFIED  only when every contract passed with evidence
- A Merge Certificate is issued only for VERIFIED; otherwise a Rejection
  Notice JSON is written alongside the HTML report.
"""
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

import click


def _load_approved_contracts(
    repo_path: str, spec_text: str, use_registry: bool,
) -> list[dict[str, Any]]:
    """P2: load registry-approved contracts for (repo, spec digest).

    Maps each candidate to its canonical checker family id so the
    deterministic checker registry and the Review Court can consume it.
    When the registry is unused/unavailable the list is empty and the
    pipeline keeps its implicit spec compilation.
    """
    if not use_registry:
        return []
    import hashlib

    from agent.contracts.compiler import family_id_for
    from agent.contracts.registry import ContractRegistry

    digest = hashlib.sha256(spec_text.encode()).hexdigest()[:16]
    registry = ContractRegistry()
    try:
        candidates = registry.get_approved_for_repo(repo_path, digest)
    except Exception as exc:  # noqa: BLE001 — MySQL unavailable
        click.echo(
            f"WARNING: approved-contract registry unavailable ({exc}); "
            "falling back to implicit spec compilation",
            err=True,
        )
        return []
    merged: dict[str, dict[str, Any]] = {}
    for c in candidates:
        family = family_id_for(c.checker_type, c.expected_behavior)
        row = merged.setdefault(family, {
            "id": family,
            "checker_type": c.checker_type,
            "requirement": c.requirement,
            "expected_behavior": c.expected_behavior,
            "approved": True,
            "registry_ids": [],
        })
        row["registry_ids"].append(c.id)
        if c.expected_behavior not in row["expected_behavior"]:
            row["expected_behavior"] += " AND " + c.expected_behavior
    if merged:
        click.echo(
            f"Using {len(merged)} registry-approved contract(s) "
            f"for spec digest {digest}"
        )
    else:
        click.echo(
            f"WARNING: no approved contracts for spec digest {digest}; "
            "candidates will stay unapproved (BLOCKER evidence disabled)",
            err=True,
        )
    return list(merged.values())


def _maybe_sign_document(
    doc_path: Path,
    document: dict[str, Any],
    job_id: str,
    output_path: Path,
) -> None:
    """Sign the document when an Ed25519 key is configured (P5).

    Missing key material is documented, never silent: the unsigned document
    remains the artifact, and a clear message states why it is unsigned.
    """
    import json as _json

    from evidence.signing import SigningError, sign_json_document

    try:
        statement = sign_json_document(document)
    except SigningError as exc:
        click.echo(f"  (unsigned: {exc})")
        return
    signed_path = output_path / f"signed-{job_id[:8]}-{doc_path.stem}.json"
    signed_path.write_text(_json.dumps(statement, indent=2), encoding="utf-8")
    click.echo(f"Signed statement written -> {signed_path}")


def _owner_repo_from_remote(repo_path: Path) -> tuple[str, str] | None:
    """Resolve (owner, repo) from the first GitHub remote URL."""
    import re as _re

    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:  # noqa: BLE001 — best effort resolution
        return None
    if proc.returncode != 0:
        return None
    url = proc.stdout.strip()
    match = _re.search(
        r"(?:github\.com[:/])([^/]+)/([^/]+?)(?:\.git)?$", url
    )
    if not match:
        return None
    return match.group(1), match.group(2)


def _maybe_publish_check_run(
    repo_path: Path,
    head_sha: str,
    verdict: str,
    job_id: str,
    depth: str,
    summary: dict[str, Any],
) -> None:
    """Best-effort GitHub Check Run publication (--publish-check).

    Resolves owner/repo from the git remote and publishes the terminal
    conclusion through the GitHub App. GitHub being unreachable or the App
    credentials being absent must never fail the verification itself.
    """
    from integrations.github_checks import (
        GitHubAppConfigError,
        check_summary_text,
        conclusion_for_verdict,
        github_app_client_from_env,
    )

    owner_repo = _owner_repo_from_remote(repo_path)
    if owner_repo is None:
        click.echo("  (check run skipped: no GitHub remote detected)", err=True)
        return
    owner, repo_name = owner_repo
    try:
        client = github_app_client_from_env()
    except GitHubAppConfigError as exc:
        click.echo(f"  (check run skipped: {exc})", err=True)
        return
    if client is None:
        click.echo(
            "  (check run skipped: GitHub App not configured — set "
            "GITHUB_APP_ID / GITHUB_APP_INSTALLATION_ID / "
            "GITHUB_APP_PRIVATE_KEY)",
            err=True,
        )
        return
    if not head_sha:
        click.echo("  (check run skipped: head commit unavailable)", err=True)
        client.close()
        return
    public_url = os.getenv("SPECPROOF_PUBLIC_URL", "").rstrip("/")
    try:
        run = client.create_check_run(
            owner=owner,
            repo=repo_name,
            head_sha=head_sha,
            title="SpecProof verification",
            summary=f"Verification {job_id[:8]} (depth {depth}).",
            details_url=f"{public_url}/dashboard#job={job_id}" if public_url else "",
        )
        client.update_check_run(
            check_run_id=int(run["id"]),
            owner=owner,
            repo=repo_name,
            conclusion=conclusion_for_verdict(verdict),
            title="SpecProof: " + verdict,
            summary=check_summary_text(verdict, summary),
        )
        click.echo(f"Check Run published for {owner}/{repo_name} (#{run['id']})")
    except Exception as exc:  # noqa: BLE001 — optional integration
        click.echo(f"  (check run publish failed: {exc})", err=True)
    finally:
        client.close()


def _cleanup_worktrees(repo: str, final: dict[str, Any]) -> None:
    """Remove temporary Base/Head worktrees created by the pipeline."""
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
    type=click.Choice(["FAST", "DEEP", "RELEASE"]),
    default="FAST",
    help="Verification depth: FAST (static+differential), DEEP "
    "(+ mutation campaign + full-stack state deltas), RELEASE "
    "(DEEP + reproducibility + capsule integrity gates + signing)",
)
@click.option(
    "--output-dir", default="./reports", help="Output directory for reports"
)
@click.option(
    "--app-dir", "app_dir", default="",
    help="Subdirectory inside the repo that holds pom.xml (empty = repo root)"
)
@click.option(
    "--llm/--no-llm",
    "use_llm",
    default=True,
    help="Enable/disable LLM-assisted nodes (default: enabled; falls back to "
    "deterministic checks when no API key is configured)",
)
@click.option(
    "--keep-worktrees",
    is_flag=True,
    default=False,
    help="Do not remove the temporary Base/Head worktrees after the run "
    "(debugging only)",
)
@click.option(
    "--use-approved-contracts",
    is_flag=True,
    default=False,
    help="Use contracts approved in the registry (specproof contract approve) "
    "instead of implicit spec compilation; unapproved candidates do not count "
    "toward BLOCKER evidence",
)
@click.option(
    "--publish-check",
    is_flag=True,
    default=False,
    help="Publish the verdict as a GitHub Check Run (specproof/verify) using "
    "GitHub App credentials from the environment; skipped with a warning "
    "when not configured (best-effort, never fails the run)",
)
def verify(
    repo: str,
    base_ref: str,
    head_ref: str,
    spec_path: str,
    depth: str,
    output_dir: str,
    app_dir: str,
    use_llm: bool,
    keep_worktrees: bool,
    use_approved_contracts: bool,
    publish_check: bool,
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
    state["use_llm"] = use_llm
    state["require_approved_contracts"] = use_approved_contracts
    state["approved_contracts"] = (
        _load_approved_contracts(
            str(repo_path), spec_file.read_text(encoding="utf-8"),
            use_approved_contracts,
        )
    )

    click.echo("\nRunning verification pipeline...")
    final_state: dict[str, Any] = {}
    try:
        final_state = graph.invoke(state)
    finally:
        # Never leak worktrees on the user's repository (debugging flag opts out).
        if not keep_worktrees:
            _cleanup_worktrees(str(repo_path), final_state)

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

    # ── Persist summary when MySQL is available (dashboard) ──
    try:
        from agent.worker import _state_summary
        from storage.mysql import MySQLStore

        MySQLStore().save_job_summary(job_id, _state_summary(final_state, verdict))
        click.echo("Job summary persisted to MySQL.")
    except Exception:
        # Local CLI runs may have no database — the artifacts remain intact.
        pass

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

    # Contract lineage (GRAND_PLAN_V2 §18.1): attach the evidence-chain
    # root hash to the certificate when publish_report produced one.
    lineage_extension = None
    if final_state.get("lineage_root"):
        lineage_extension = {
            "lineage_root": str(final_state.get("lineage_root")),
            "lineage_nodes": int(final_state.get("lineage_nodes", 0)),
            "lineage_edges": int(final_state.get("lineage_edges", 0)),
        }

    if verdict == "VERIFIED":
        certificate = issue_certificate(
            repository=str(repo_path),
            commit_sha=head_sha,
            requirements_text=requirement_text,
            contracts=merged_contracts,
            evidence_digests=evidence_digests,
            extension=lineage_extension,
        )
        if certificate is not None:
            cert_path = output_path / f"merge-certificate-{job_id[:8]}.json"
            cert_path.write_text(certificate.to_json(), encoding="utf-8")
            click.echo(f"Merge Certificate: ISSUED -> {cert_path}")
            _maybe_sign_document(cert_path, certificate.to_dict(), job_id, output_path)
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
        _maybe_sign_document(notice_path, notice.to_dict(), job_id, output_path)

    # ── GitHub Check Run publication (RELEASE / --publish-check) ──
    if publish_check:
        from agent.worker import _state_summary

        _maybe_publish_check_run(
            repo_path=repo_path,
            head_sha=head_sha,
            verdict=verdict,
            job_id=job_id,
            depth=depth,
            summary=_state_summary(final_state, verdict),
        )
