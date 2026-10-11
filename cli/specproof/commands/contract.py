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
    CoverageGap,
    candidates_from_constitution,
    compile_candidates,
    coverage_gaps,
    dedupe_candidates,
)
from agent.contracts.parser import parse_requirements  # noqa: E402
from agent.contracts.registry import ContractRegistry  # noqa: E402


def _spec_digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _echo_coverage_gaps(gaps: list[CoverageGap]) -> None:
    """Print the §2.5 coverage report: which requirements nobody verifies.

    Printed on stderr, because it is a finding about the run rather than part
    of the result a caller parses from stdout — and because it must not be
    droppable by a ``> file`` redirect, which is exactly how a coverage hole
    would get lost.
    """
    if not gaps:
        return
    click.echo(
        f"覆盖不足：{len(gaps)} 条需求无法编译为检查（这些需求当前无人验证）",
        err=True,
    )
    for g in gaps:
        click.echo(f"  [UNCOVERED] {g.requirement_ref} — {g.requirement[:120]}", err=True)
        click.echo(f"              建议：{g.suggestion}", err=True)


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
        checker_version = r.get("checker_version") or ""
        checker_note = f" checker={checker_version}" if checker_version else ""
        click.echo(
            f"  [{r['status']}] {r['id']} v{r['version']} "
            f"({r['checker_type']}) spec={r['spec_digest'][:8]}{checker_note}"
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
    # §2.5: computed from the candidate list actually going to the registry, so
    # a requirement dropped by dedupe below is reported too. Printed before the
    # "no candidates" return, because a spec where *nothing* compiles is the
    # case where the gaps are the whole output.
    gaps = coverage_gaps(parsed.requirements, candidates)
    if constitution:
        policy_texts = [
            Path(p).read_text(encoding="utf-8") for p in constitution
        ]
        candidates += candidates_from_constitution(policy_texts)
    candidates = dedupe_candidates(candidates)

    if not candidates:
        click.echo("No contract candidates extracted from the given sources.")
        _echo_coverage_gaps(gaps)
        if gaps:
            # Not a usage error: the spec parsed fine and the answer is "these
            # requirements cannot be verified yet". Exiting 1 lets a caller
            # treat "nothing compilable" as a real result instead of success.
            raise SystemExit(1)
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
    _echo_coverage_gaps(gaps)
    if gaps:
        # Same refusal as the zero-candidate branch, and for the same reason:
        # a spec that compiles *some* requirements still leaves the gapped ones
        # unverified. Reading that run as plain success ("N proposed, ok") hides
        # exactly the requirements §2.5 exists to surface. Exit 1 so a caller
        # or gate treats a partial proposal as a result, not a clean pass.
        raise SystemExit(1)


@contract_cmd.command("approve")
@click.option("--repo", required=True, help="Repository path (registry scope)")
@click.option("--id", "contract_id", required=True, help="Contract id to approve")
@click.option("--by", "approved_by", required=True, help="Approver name (audit trail)")
@click.option("--reason", default="", help="Approval note")
@click.option(
    "--version",
    "version",
    type=int,
    default=None,
    help="Exact contract version to approve (default: newest stored version)",
)
def approve(
    repo: str,
    contract_id: str,
    approved_by: str,
    reason: str,
    version: int | None,
) -> None:
    """Approve an exact contract version (recorded in the audit trail)."""
    del repo  # registry is keyed by contract id; repo kept for CLI symmetry
    registry = ContractRegistry()
    ok = registry.approve(contract_id, approved_by, reason, version)
    if ok:
        target = f"v{version}" if version is not None else "(latest)"
        click.echo(f"APPROVED {contract_id} {target} by {approved_by}")
    else:
        click.echo(
            f"ERROR: cannot approve {contract_id} (not found, wrong status, "
            "or wrong version)",
            err=True,
        )
        raise SystemExit(1)


@contract_cmd.command("reject")
@click.option("--repo", required=True, help="Repository path (registry scope)")
@click.option("--id", "contract_id", required=True, help="Contract id to reject")
@click.option("--by", "approved_by", required=True, help="Rejecter name (audit trail)")
@click.option("--reason", default="", help="Rejection reason")
@click.option(
    "--version",
    "version",
    type=int,
    default=None,
    help="Exact contract version to reject (default: newest stored version)",
)
def reject(
    repo: str,
    contract_id: str,
    approved_by: str,
    reason: str,
    version: int | None,
) -> None:
    """Reject an exact proposed version (stays in the audit trail)."""
    del repo  # registry is keyed by contract id; repo kept for CLI symmetry
    registry = ContractRegistry()
    ok = registry.reject(contract_id, approved_by, reason, version)
    if ok:
        target = f"v{version}" if version is not None else "(latest)"
        click.echo(f"REJECTED {contract_id} {target} by {approved_by}")
    else:
        click.echo(
            f"ERROR: cannot reject {contract_id} (not found, wrong status, "
            "or wrong version)",
            err=True,
        )
        raise SystemExit(1)
