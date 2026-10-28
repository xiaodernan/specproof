"""#498 — the structural-clone ratchet.

A scan of the shipped packages used to find 16 pairs of byte-identical function
bodies; #483–#497 removed or gated most of them. This file is the ratchet: a
**new** copy-pasted body turns it red, and removing a known one turns it red
too until the roster is updated — so the roster stays a claim about the tree
rather than a snapshot of one afternoon.

Why it matters: two copies of one decision are equal until someone edits one.
The pairs that stayed correct in this repo were the ones a test pinned; the
unpinned ones drifted (the env-truthy set drifted into ``MINIO_SECURE=1``
meaning TLS **off**, #474).

The known list is NOT an endorsement. Each entry states why it is still there;
shrinking it is progress.
"""
from __future__ import annotations

import ast
import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: Packages whose modules ship in the product (tests and scripts excluded).
PACKAGES = (
    "agent", "api", "cli", "craft", "evidence", "experiments", "integrations",
    "mcp", "observability", "retrieval", "sandbox", "services", "storage",
)

#: Bodies smaller than this are usually one-line delegations where a shared
#: helper would add more indirection than it removes.
MIN_NODES = 25

Clone = frozenset[tuple[str, str]]  # {(relative path, function name)}

#: Groups that still exist, each with the reason it has not been merged.
KNOWN_CLONES: dict[Clone, str] = {
    frozenset(
        {
            ("storage/agent_jobs.py", "__init__"),
            ("storage/identity.py", "__init__"),
            ("storage/object_metadata.py", "__init__"),
        }
    ): "SQLite store constructor (connect + Row factory + lock + ensure_schema); "
    "merging needs a base class, and a hierarchy for five lines costs more than it saves",
    frozenset(
        {
            ("api/routes/web.py", "_capsule_dirs"),
            ("mcp/tools.py", "_capsule_dirs"),
        }
    ): "cross-layer path resolution, pinned by test_capsule_and_report_paths_agree "
    "(#493); merging needs an owner decision on where the path lives",
    frozenset(
        {
            ("api/routes/web.py", "_eval_report_path"),
            ("mcp/tools.py", "_eval_report_path"),
        }
    ): "same cross-layer decision as _capsule_dirs (#493)",
    frozenset(
        {
            ("craft/adapters/go_adapter.py", "_read_text_or_none"),
            ("craft/adapters/node_adapter.py", "_read_text_or_none"),
        }
    ): "the adapter lane's file reader; #513 merged this pair's sibling "
    "(`_as_text`, three copies) into sandbox.runner.child_output_text, so the "
    "lane has one merge point left here — a shared reader needs the same "
    "cross-package decision and these two files are not on that path yet",
    frozenset(
        {
            ("storage/agent_jobs.py", "connection"),
            ("storage/billing.py", "connection"),
            ("storage/identity.py", "connection"),
            ("storage/mysql.py", "connection"),
            ("storage/object_metadata.py", "connection"),
        }
    ): "two-line contextmanager delegating to unit_of_work(self._connect); a mixin "
    "would add indirection for two lines AND weaken the return type from "
    "Iterator[pymysql.Connection] to Iterator[Any] across five stores — worse than "
    "the duplication it removes",
    frozenset(
        {
            ("craft/tools.py", "__init__"),
            ("mcp/client.py", "__init__"),
        }
    ): "two unrelated classes that happen to share a two-line constructor; "
    "coincidence, not a shared contract",
}


def _shipped_files() -> list[str]:
    out = subprocess.run(
        ("git", "ls-files", "--", *(f"{pkg}/*.py" for pkg in PACKAGES)),
        cwd=ROOT,
        capture_output=True,
        check=True,
        timeout=180,
    )
    files = [line for line in out.stdout.decode("utf-8", "replace").splitlines() if line]
    assert len(files) > 100, f"shipped-file census collapsed: {len(files)} files"
    return files


def _normalised_body(node: ast.AST) -> str:
    """The function's AST with its docstring removed, dumped without positions.

    Docstrings legitimately differ between copies; everything else — statements,
    identifiers, literals — has to match for this to count as a clone.
    """
    body = list(getattr(node, "body", []))
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        node.body = body[1:] or [ast.Pass()]
    return ast.dump(node, annotate_fields=True, include_attributes=False)


def _clones() -> set[Clone]:
    """Every group of byte-identical bodies that spans 2+ distinct files."""
    by_digest: dict[str, set[tuple[str, str]]] = {}
    for rel in _shipped_files():
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if sum(1 for _ in ast.walk(node)) < MIN_NODES:
                continue
            digest = hashlib.sha256(_normalised_body(node).encode()).hexdigest()
            by_digest.setdefault(digest, set()).add((rel, node.name))

    return {
        frozenset(group)
        for group in by_digest.values()
        if len({rel for rel, _ in group}) >= 2
    }


def test_no_new_copy_pasted_function_bodies() -> None:
    found = _clones()
    new = sorted(found - set(KNOWN_CLONES), key=sorted)
    assert not new, (
        "new structurally identical function bodies appeared: "
        + "; ".join(", ".join(f"{rel}::{name}" for rel, name in group) for group in new)
        + ". Share the implementation, or add the pair to KNOWN_CLONES with the reason "
        "it must stay duplicated."
    )


def test_the_known_clone_roster_is_still_true() -> None:
    found = _clones()
    gone = sorted(set(KNOWN_CLONES) - found, key=sorted)
    assert not gone, (
        "these pairs are no longer clones, so the roster is stale: "
        + "; ".join(", ".join(f"{rel}::{name}" for rel, name in group) for group in gone)
        + ". Remove them from KNOWN_CLONES — the roster is a claim about the tree."
    )


def test_every_known_clone_states_a_reason() -> None:
    for group, reason in KNOWN_CLONES.items():
        assert reason.strip(), f"{sorted(group)} has no stated reason"
        assert len({rel for rel, _ in group}) >= 2, f"{sorted(group)} is not cross-file"
