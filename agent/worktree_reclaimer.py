"""Crash reclaimer for orphan prepare_* worktrees (§14.1).

prepare_base / prepare_head register every worktree they are about to create
with a sidecar marker file in the worktree root ('tempfile.gettempdir()' by
default).  If the process crashes between marker write and cleanup, the
directory stays on disk — and the marker is the only trustworthy claim of
ownership, because the checked-out content itself is untrusted PR material
and must never influence a removal decision.

Marker convention:

- filename: '.specproof-worktree-<sha256(real worktree path)>.json' — the
  hash makes each marker name unique per worktree, and because markers live
  OUTSIDE the checkout (in the worker-owned temp root), untrusted repository
  content cannot fabricate or tamper with them;
- content: a JSON object with 'kind == "specproof-worktree"',
  'version == 1' and string fields 'job_id', 'repo_path' and
  'worktree_path'.

'reclaim_orphans(allowed_root, job_id)' scans the allowed root for marker
files and removes every worktree whose marker matches the convention and —
when 'job_id' is given — the job.  Everything else (foreign jobs, foreign
kinds, unreadable markers, paths outside the allowed root) is left untouched
and reported.  The worker calls it at the start of a *fresh* job: resume
paths skip it because their worktrees are live checkpoint state, not orphans.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from agent.repo_safety import GitRunner, default_git_runner

# ── Marker convention ────────────────────────────────────────────

WORKTREE_MARKER_PREFIX = ".specproof-worktree-"
MARKER_SUFFIX = ".json"
MARKER_KIND = "specproof-worktree"
MARKER_VERSION = 1

_MARKER_FIELDS: tuple[str, ...] = ("job_id", "repo_path", "worktree_path")


def marker_filename(worktree: str | os.PathLike[str]) -> str:
    """Derive the sidecar marker filename from the real worktree path."""
    key = os.path.realpath(
        os.fspath(Path(worktree).resolve(strict=False))
    ).encode("utf-8")
    digest = hashlib.sha256(key).hexdigest()
    return WORKTREE_MARKER_PREFIX + digest + MARKER_SUFFIX


def write_worktree_marker(
    worktree: str | os.PathLike[str],
    *,
    repo_path: str | os.PathLike[str],
    job_id: str,
    root: str | os.PathLike[str] | None = None,
) -> Path:
    """Register a worktree with a sidecar marker; return the marker path.

    Called by the prepare nodes *before* 'git worktree add' so that a crash
    at any later point leaves a reclaimable claim behind.
    """
    worktree_path = Path(worktree)
    root_path = Path(root) if root is not None else Path(tempfile.gettempdir())
    data = {
        "kind": MARKER_KIND,
        "version": MARKER_VERSION,
        "job_id": str(job_id),
        "repo_path": os.path.realpath(
            os.fspath(Path(repo_path).resolve(strict=False))
        ),
        "worktree_path": os.path.realpath(
            os.fspath(worktree_path.resolve(strict=False))
        ),
        "created_at": datetime.now(UTC).isoformat(),
    }
    marker = root_path / marker_filename(worktree_path)
    marker.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    return marker


# ── Data model ───────────────────────────────────────────────────


@dataclass
class ReclaimResult:
    """Outcome of one reclamation sweep."""

    reclaimed: int = 0
    left_foreign: int = 0
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _parse_marker(path: Path) -> dict[str, str] | None:
    """Parse and validate a marker file; None when it is not ours."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("kind") != MARKER_KIND:
        return None
    if data.get("version") != MARKER_VERSION:
        return None
    parsed: dict[str, str] = {}
    for key in _MARKER_FIELDS:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            return None
        parsed[key] = value
    return parsed


# ── Reclamation ──────────────────────────────────────────────────


def reclaim_orphans(
    allowed_root: str | os.PathLike[str],
    job_id: str | None = None,
    *,
    git_runner: GitRunner | None = None,
) -> ReclaimResult:
    """Reclaim orphan worktrees claimed by sidecar markers.

    Args:
        allowed_root: directory holding the sidecar markers (the worktree
                      root; 'tempfile.gettempdir()' by default upstream).
        job_id:       when given, only markers with this job_id are reclaimed;
                      None (maintenance sweep) reclaims every valid marker.
        git_runner:   optional git subprocess runner (tests inject stubs).

    Returns:
        ReclaimResult with counts and per-item messages.  Foreign markers
        (other jobs / kinds) and markers that fail validation are never
        removed.
    """
    result = ReclaimResult()
    runner = git_runner or default_git_runner
    root = Path(allowed_root)
    try:
        root_real = root.resolve(strict=False)
    except OSError as exc:
        result.failures.append(
            f"cannot resolve allowed root {allowed_root}: {exc}"
        )
        return result
    if not root_real.is_dir():
        result.failures.append(f"allowed root is not a directory: {root_real}")
        return result
    try:
        entries = list(root_real.iterdir())
    except OSError as exc:
        result.failures.append(f"cannot list allowed root {root_real}: {exc}")
        return result
    for entry in entries:
        if not entry.name.startswith(WORKTREE_MARKER_PREFIX):
            continue
        if not entry.name.endswith(MARKER_SUFFIX):
            continue
        if not entry.is_file():
            continue
        data = _parse_marker(entry)
        if data is None:
            result.warnings.append(
                f"unrecognized marker {entry.name}; left untouched"
            )
            continue
        if job_id is not None and data["job_id"] != job_id:
            result.left_foreign += 1
            continue
        _reclaim_one(entry, data, root_real, runner, result)
    return result


def _reclaim_one(
    marker: Path,
    data: dict[str, str],
    root_real: Path,
    runner: GitRunner,
    result: ReclaimResult,
) -> None:
    """Reclaim a single marker-claimed worktree, conservatively."""
    worktree = Path(data["worktree_path"])
    try:
        worktree_real = Path(
            os.path.realpath(os.fspath(worktree.resolve(strict=False)))
        )
    except OSError as exc:
        result.failures.append(
            f"marker {marker.name}: cannot resolve worktree path: {exc}"
        )
        return
    # The marker must name the worktree its filename encodes, and the
    # worktree must live under the allowed root — a marker can never reach
    # outside the root it was found in.
    if marker.name != marker_filename(worktree_real):
        result.warnings.append(
            f"marker {marker.name}: filename does not match worktree path; "
            "left untouched"
        )
        return
    if worktree_real != root_real and not worktree_real.is_relative_to(root_real):
        result.failures.append(
            f"marker {marker.name}: worktree {worktree_real} is outside the "
            "allowed root; left untouched"
        )
        return
    if not worktree_real.exists():
        result.warnings.append(
            f"marker {marker.name}: worktree already gone; "
            "removing stale marker"
        )
        _unlink_marker(marker, result)
        result.reclaimed += 1
        return

    repo = data["repo_path"]
    removed = False
    proc = _run_git(
        runner,
        ["-C", repo, "worktree", "remove", "--force", str(worktree_real)],
        marker,
        result,
    )
    if proc is not None and proc.returncode == 0:
        removed = True
    else:
        # The worktree may never have been registered (crash mid-add).
        # Prune stale registrations, then take the directory only when it is
        # empty — a non-empty unregistered directory is never deleted.
        _run_git(runner, ["-C", repo, "worktree", "prune"], marker, result)
        if _is_empty_dir(worktree_real):
            try:
                worktree_real.rmdir()
                removed = True
            except OSError as exc:
                result.warnings.append(
                    f"marker {marker.name}: could not remove empty directory "
                    f"{worktree_real}: {exc}"
                )
    if removed:
        _unlink_marker(marker, result)
        result.reclaimed += 1
    else:
        result.failures.append(
            f"could not remove worktree {worktree_real} "
            f"(marker {marker.name} kept for retry)"
        )


def _run_git(
    runner: GitRunner,
    argv: Sequence[str],
    marker: Path,
    result: ReclaimResult,
) -> subprocess.CompletedProcess[str] | None:
    """Run one git command through the injected runner, failing safely."""
    try:
        return runner(argv)
    except Exception as exc:  # noqa: BLE001 — record and move on
        result.failures.append(
            f"marker {marker.name}: git runner failed for "
            f"{' '.join(argv)}: {exc}"
        )
        return None


def _is_empty_dir(path: Path) -> bool:
    """True when path exists, is a directory, and has no entries."""
    try:
        return path.is_dir() and next(path.iterdir(), None) is None
    except OSError:
        return False


def _unlink_marker(marker: Path, result: ReclaimResult) -> None:
    """Remove a marker file, recording failure instead of raising."""
    try:
        marker.unlink()
    except OSError as exc:
        result.warnings.append(
            f"could not remove marker {marker.name}: {exc}"
        )


__all__ = [
    "MARKER_KIND",
    "MARKER_SUFFIX",
    "MARKER_VERSION",
    "WORKTREE_MARKER_PREFIX",
    "ReclaimResult",
    "marker_filename",
    "reclaim_orphans",
    "write_worktree_marker",
]
