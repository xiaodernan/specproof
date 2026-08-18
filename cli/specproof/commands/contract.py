"""specproof contract — human approval workflow for Contract candidates.

Proposed contracts are PROPOSALS extracted from the spec and repository
constitution; they only become enforceable after an explicit approve.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import click

# Ensure the project root is on sys.path
_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from agent.contracts.compiler import (  # noqa: E402
    candidates_from_constitution,
    compile_candidates,
    dedupe_candidates,
)
from agent.contracts.parser import parse_requirements  # noqa: E402
from agent.contracts.registry import ContractRegistry  # noqa: E402


def _spec_digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@click.group("contract")
def contract_cmd() -> None:
    """Propose, approve and list verification contracts."""


@contract_cmd.command("list")
@click.option("--repo", required=True, help="Repository path (registry scope)")
@click.option("--status", default=None, help="Filter: PROPOSED/APPROVED/REJECTED/REVOKED")
def list_contracts(repo: str, status: str | None) -> None:
    """List contracts in the registry for a repository."""
    repo_path = str(Path(repo).resolve())
    registry = ContractRegistry()
    rows = registry.list_contracts(repo_path, status)
    if not rows:
        click.echo(f"No contracts registered for {repo_path}")
        return
    click.echo(f"Contracts for {repo_path} ({len(rows)}):")
    for r in rows:
        click.echo(
            f"  [{r['status']}] {r['id']} v{r['version']} "
            f"({r['checker_type']}) spec={r['spec_digest'][:8]}"
        )
        click.echo(f"       {str(r['expected_behavior'])[:160]}")


@contract_cmd.command("propose")
@click.option("--repo", required=True, help="Repository path (registry scope)")
@click.option("--spec", "spec_path", required=True, help="Requirement spec file")
@click.option("--constitution", multiple=True, help="Policy files (README/ADR); repeatable")
def propose(repo: str, spec_path: str, constitution: tuple[str, ...]) -> None:
    """Parse the spec (and optional policy files) into PROPOSED candidates."""
    repo_path = str(Path(repo).resolve())
    spec_file = Path(spec_path)
    if not spec_file.exists():
        click.echo(f"ERROR: spec file not found: {spec_file}", err=True)
        raise SystemExit(1)
    spec_text = spec_file.read_text(encoding="utf-8")

    parsed = parse_requirements(spec_text)
    candidates = compile_candidates(parsed.requirements)
    if constitution:
        policy_texts = [
            Path(p).read_text(encoding="utf-8") for p in constitution
        ]
        candidates += candidates_from_constitution(policy_texts)
    candidates = dedupe_candidates(candidates)

    if not candidates:
        click.echo("No contract candidates extracted from the given sources.")
        return

    registry = ContractRegistry()
    written = registry.upsert_candidates(
        repo_path, _spec_digest(spec_text), candidates
    )
    click.echo(
        f"Proposed {written} contract candidate(s) for {repo_path} "
        f"(spec digest {_spec_digest(spec_text)}). "
        "Review and approve them before verification."
    )
    for c in candidates:
        click.echo(f"  [PROPOSED] {c.id} ({c.checker_type}) — {c.expected_behavior[:120]}")


@contract_cmd.command("approve")
@click.option("--repo", required=True, help="Repository path (registry scope)")
@click.option("--id", "contract_id", required=True, help="Contract id to approve")
@click.option("--by", "approved_by", required=True, help="Approver name (audit trail)")
@click.option("--reason", default="", help="Approval note")
def approve(repo: str, contract_id: str, approved_by: str, reason: str) -> None:
    """Approve a proposed contract (recorded in the audit trail)."""
    del repo  # registry is keyed by contract id; repo kept for CLI symmetry
    registry = ContractRegistry()
    ok = registry.approve(contract_id, approved_by, reason)
    if ok:
        click.echo(f"APPROVED {contract_id} by {approved_by}")
    else:
        click.echo(f"ERROR: cannot approve {contract_id} (not found or wrong status)", err=True)
        raise SystemExit(1)


@contract_cmd.command("reject")
@click.option("--repo", required=True, help="Repository path (registry scope)")
@click.option("--id", "contract_id", required=True, help="Contract id to reject")
@click.option("--by", "approved_by", required=True, help="Rejecter name (audit trail)")
@click.option("--reason", default="", help="Rejection reason")
def reject(repo: str, contract_id: str, approved_by: str, reason: str) -> None:
    """Reject a proposed contract (stays in the audit trail)."""
    del repo  # registry is keyed by contract id; repo kept for CLI symmetry
    registry = ContractRegistry()
    ok = registry.reject(contract_id, approved_by, reason)
    if ok:
        click.echo(f"REJECTED {contract_id} by {approved_by}")
    else:
        click.echo(f"ERROR: cannot reject {contract_id} (not found or wrong status)", err=True)
        raise SystemExit(1)
