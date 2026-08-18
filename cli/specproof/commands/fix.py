"""specproof fix / approve — P5 fix proposal and approval flow (spec 6.2).

    specproof fix ...            propose deterministic fixes for findings
    specproof approve FIX_ID ... apply + verify an approved fix, optionally
                                 publish the fix PR through the GitHub App

Honesty rules:

- Proposals come only from agent.fixes (mechanical restorations of Base
  behavior); every other finding is listed as skipped with a reason.
- approve applies the fix to a fresh Head worktree and requires a passing
  Maven compile before it reports success. No compile project -> no
  approval: the fix is marked "applied_unverified" and the exit code is 1.
- GitHub publishing (--github) is best-effort: without a pushable remote or
  App credentials the PR payload is written to disk instead, and the
  approval itself still succeeds. Publishing never fabricates success.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from agent.fixes import (
    FixProposal,
    apply_fix,
    propose_fixes,
    render_fix_summary,
)


def _run(
    cmd: list[str], cwd: Path, timeout: int = 600
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout
    )


def _load_findings(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise click.ClickException(f"cannot read findings file: {exc}") from exc
    if isinstance(data, dict):
        findings = data.get("findings", [])
    elif isinstance(data, list):
        findings = data
    else:
        raise click.ClickException("findings file must be a JSON list or object")
    return [f for f in findings if isinstance(f, dict)]


def _materialize_worktrees(
    repo: Path, base_ref: str, head_ref: str
) -> tuple[Path, Path]:
    """Check out Base and Head into detached worktrees (like prepare_*)."""
    tmp = Path(tempfile.mkdtemp(prefix="specproof-fix-"))
    base_dir = tmp / "base"
    head_dir = tmp / "head"
    for target, ref in ((base_dir, base_ref), (head_dir, head_ref)):
        proc = _run(
            [ "git", "-C", str(repo), "worktree", "add", "--detach",
              str(target), ref ],
            repo,
            timeout=180,
        )
        if proc.returncode != 0:
            raise click.ClickException(
                f"failed to check out '{ref}': {proc.stderr.strip()[:300]}"
            )
    return base_dir, head_dir


def _cleanup_worktrees(repo: Path, base_dir: Path, head_dir: Path) -> None:
    for target in (base_dir, head_dir):
        if target.exists():
            _run(
                ["git", "-C", str(repo), "worktree", "remove", "--force",
                 str(target)],
                repo,
                timeout=120,
            )
    _run(["git", "-C", str(repo), "worktree", "prune"], repo, timeout=60)


def _find_maven_project(root: Path, app_dir: str) -> tuple[Path, str] | None:
    """Locate (project_dir, wrapper_name) for the Maven compile check."""
    candidates = [root / app_dir] if app_dir else []
    candidates.append(root)
    for cand in candidates:
        if not (cand / "pom.xml").is_file():
            continue
        if (cand / "mvnw.cmd").is_file():
            return cand, "mvnw.cmd"
        if (cand / "mvnw").is_file():
            return cand, "mvnw"
    return None


def _compile_verify(root: Path, app_dir: str) -> tuple[bool, str]:
    """Maven compile as the fix verification gate (EXIT=0 required)."""
    located = _find_maven_project(root, app_dir)
    if located is None:
        return False, "no Maven project (pom.xml + mvnw) found — cannot verify"
    project, wrapper = located
    proc = _run(
        [str(project / wrapper), "-q", "-f", "pom.xml", "compile"],
        project,
        timeout=900,
    )
    if proc.returncode == 0:
        return True, "mvnw compile EXIT=0"
    return False, f"mvnw compile EXIT={proc.returncode}: " + (
        proc.stderr.strip()[-400:] or proc.stdout.strip()[-400:]
    )


def _write_requests_file(
    output_dir: Path,
    proposals: list[FixProposal],
    skipped: list[dict[str, Any]],
    repo: Path,
    base_ref: str,
    head_ref: str,
) -> Path:
    payload: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "github_context": {
            "repo_path": str(repo.resolve()),
            "base_ref": base_ref,
            "head_ref": head_ref,
        },
        "proposals": [p.to_dict() for p in proposals],
        "skipped": skipped,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "fix-requests.json"
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


@click.command("fix")
@click.option("--repo", default=".", type=click.Path(exists=True, file_okay=False),
              help="Path to the git repository")
@click.option("--base", "base_ref", default="base", show_default=True)
@click.option("--head", "head_ref", default="HEAD", show_default=True)
@click.option("--findings", required=True,
              type=click.Path(exists=True, dir_okay=False),
              help="JSON file with the verification's findings "
                   "(list, or object with a 'findings' key)")
@click.option("--app-dir", default="", show_default=True,
              help="Subdirectory of the Maven app (compile verification)")
@click.option("--output-dir", default="fixes", show_default=True)
@click.option("--apply", is_flag=True,
              help="Apply every proposed fix to the Head worktree and record "
                   "the compile verification result")
def fix_cmd(
    repo: str,
    base_ref: str,
    head_ref: str,
    findings: str,
    app_dir: str,
    output_dir: str,
    apply: bool,
) -> None:
    """Propose deterministic fixes for confirmed findings."""
    repo_path = Path(repo).resolve()
    findings_list = _load_findings(Path(findings))
    if not findings_list:
        click.echo("No findings in the input file — nothing to fix.")
        return

    click.echo(f"Analyzing {len(findings_list)} finding(s) ...")
    base_dir, head_dir = _materialize_worktrees(repo_path, base_ref, head_ref)
    try:
        proposals, skipped = propose_fixes(findings_list, base_dir, head_dir)
        statuses: dict[str, str] = {}
        if apply and proposals:
            for proposal in proposals:
                ok = apply_fix(proposal, head_dir)
                statuses[proposal.fix_id] = "applied" if ok else "anchor_drift_rejected"
            verify_ok, verify_note = _compile_verify(head_dir, app_dir)
            statuses["__verify__"] = (
                "verified" if verify_ok else "failed: " + verify_note
            )
        click.echo(render_fix_summary(proposals, skipped))
        if apply and proposals:
            click.echo("")
            click.echo("Application result:")
            for fix_id, status in statuses.items():
                click.echo(f"  {fix_id}: {status}")
        requests_path = _write_requests_file(
            Path(output_dir), proposals, skipped, repo_path, base_ref, head_ref
        )
        if apply and proposals:
            data = json.loads(requests_path.read_text(encoding="utf-8"))
            for entry in data["proposals"]:
                entry["status"] = statuses.get(entry["fix_id"], "proposed")
            requests_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        click.echo(f"Fix requests written to: {requests_path}")
    finally:
        _cleanup_worktrees(repo_path, base_dir, head_dir)


_PATCH_FENCE = "```diff"


def _load_requests(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise click.ClickException(f"cannot read fix requests file: {exc}") from exc
    if not isinstance(data, dict):
        raise click.ClickException("fix requests file must be a JSON object")
    return data


def _write_pr_payload(
    output_dir: Path,
    fix: dict[str, Any],
    repo: str,
    base_branch: str,
    head_branch: str,
) -> Path:
    payload = {
        "repo": repo,
        "base_branch": base_branch,
        "head_branch": head_branch,
        "title": f"SpecProof fix {fix['fix_id']}: {fix['rationale']}",
        "body": (
            f"Deterministic fix for finding {fix['finding_id']} "
            f"({fix['contract_id']}) proposed and verified by SpecProof.\n\n"
            + _PATCH_FENCE + "\n" + fix["patch"] + "\n```"
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"fix-pr-{fix['fix_id'].lower()}.json"
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


@click.command("approve")
@click.argument("fix_id")
@click.option("--requests", "requests_path", default="fixes/fix-requests.json",
              type=click.Path(exists=True, dir_okay=False))
@click.option("--repo", default=".", type=click.Path(exists=True, file_okay=False),
              help="Path to the git repository (defaults to github_context)")
@click.option("--app-dir", default="", show_default=True)
@click.option("--github", is_flag=True,
              help="After a successful verification, push the fix branch and "
                   "open the fix PR via the GitHub App (best-effort)")
@click.option("--remote", default="origin", show_default=True)
def approve_cmd(
    fix_id: str,
    requests_path: str,
    repo: str,
    app_dir: str,
    github: bool,
    remote: str,
) -> None:
    """Apply + verify FIX_ID, then optionally publish the fix PR."""
    fix_requests = _load_requests(Path(requests_path))
    proposals = [
        p for p in fix_requests.get("proposals", [])
        if isinstance(p, dict) and p.get("fix_id") == fix_id
    ]
    if len(proposals) != 1:
        click.echo(f"ERROR: fix request {fix_id} not found", err=True)
        raise SystemExit(2)
    fix = proposals[0]
    context = fix_requests.get("github_context", {}) or {}
    repo_path = Path(repo).resolve()
    base_ref = context.get("base_ref", "base")
    head_ref = context.get("head_ref", "HEAD")

    base_dir, head_dir = _materialize_worktrees(repo_path, base_ref, head_ref)
    try:
        proposal = FixProposal(**{
            key: fix[key]
            for key in (
                "fix_id", "finding_id", "contract_id", "path", "action",
                "anchor_line", "head_context", "base_lines", "head_lines",
                "rationale", "patch",
            )
        })
        applied = apply_fix(proposal, head_dir)
        if not applied:
            click.echo(
                "ERROR: fix anchor drifted — Head file changed since the "
                "proposal was built; NOT applied",
                err=True,
            )
            raise SystemExit(1)
        verify_ok, verify_note = _compile_verify(head_dir, app_dir)
        if not verify_ok:
            click.echo(
                f"ERROR: fix applied but verification FAILED: {verify_note}",
                err=True,
            )
            click.echo(
                "The fix is recorded as applied_unverified and was NOT approved.",
                err=True,
            )
            fix_requests["proposals"] = [
                {**p, "status": (
                    "applied_unverified"
                    if p.get("fix_id") == fix_id else p.get("status", "proposed")
                )}
                for p in fix_requests.get("proposals", [])
            ]
            Path(requests_path).write_text(
                json.dumps(fix_requests, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            raise SystemExit(1)
        click.echo(f"Fix {fix_id} applied and verified ({verify_note}).")

        fix_requests["proposals"] = [
            {**p, "status": (
                "approved" if p.get("fix_id") == fix_id
                else p.get("status", "proposed")
            )}
            for p in fix_requests.get("proposals", [])
        ]
        Path(requests_path).write_text(
            json.dumps(fix_requests, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        if not github:
            click.echo("Approval complete. Use --github to publish the fix PR.")
            return

        branch = f"specproof-fix/{fix_id.lower()}"
        commit_proc = _run(
            [
                "git", "-C", str(head_dir), "-c",
                "user.name=SpecProof", "-c",
                "user.email=specproof@localhost",
                "commit", "-a", "-m",
                f"specproof: {fix['rationale']} ({fix_id})",
            ],
            head_dir,
            timeout=120,
        )
        pushed = False
        if commit_proc.returncode == 0:
            checkout = _run(
                ["git", "-C", str(head_dir), "checkout", "-b", branch],
                head_dir,
                timeout=60,
            )
            if checkout.returncode == 0:
                push_proc = _run(
                    ["git", "-C", str(head_dir), "push", remote, branch],
                    head_dir,
                    timeout=300,
                )
                pushed = push_proc.returncode == 0
                if not pushed:
                    click.echo(
                        "WARNING: git push failed — fix PR payload written "
                        "to disk instead. Push the branch manually, then use "
                        "the payload to open the PR.",
                        err=True,
                    )
        else:
            click.echo(
                "WARNING: could not commit the fix (git identity / worktree "
                "issue) — fix PR payload written to disk instead.",
                err=True,
            )

        output_dir = Path(requests_path).resolve().parent
        if pushed:
            from integrations.github_checks import (
                GitHubAppConfigError,
                github_app_client_from_env,
            )

            try:
                client = github_app_client_from_env()
            except GitHubAppConfigError as exc:
                client = None
                click.echo(
                    f"GitHub App misconfigured: {exc} — payload written "
                    "to disk.",
                    err=True,
                )
            if client is not None:
                with client:
                    run_info = client.create_fix_pr(
                        owner=context.get("owner", ""),
                        repo=context.get("repo", ""),
                        base_branch=base_ref,
                        head_branch=branch,
                        title=f"SpecProof fix {fix['fix_id']}: {fix['rationale']}",
                        body=(
                            "Deterministic fix for finding "
                            f"{fix['finding_id']} ({fix['contract_id']}) "
                            "proposed and verified by SpecProof.\n\n"
                            + _PATCH_FENCE + "\n" + fix["patch"] + "\n```"
                        ),
                    )
                    click.echo(f"Fix PR opened: {run_info.get('html_url', '?')}")
                    return
            payload = _write_pr_payload(
                output_dir, fix, str(repo_path), base_ref, branch
            )
            click.echo(f"Fix PR payload written to: {payload}")
            return
        payload = _write_pr_payload(
            output_dir, fix, str(repo_path), base_ref, branch
        )
        click.echo(f"Fix PR payload written to: {payload}")
    finally:
        _cleanup_worktrees(repo_path, base_dir, head_dir)
