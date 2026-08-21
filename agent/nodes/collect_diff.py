
"""collect_diff node — analyze git diff between base and head.

§14.1 three scopes: file-level (audit), symbol-level (retrieval/checkers)
and semantic candidates (dynamic experiment + mutation budget). Changes in
unparseable languages or binary files are kept as unresolved_changes —
never silently dropped. Errors are recorded in state["errors"] (which the
graph's error guard routes on) instead of being disguised as
changed-symbol data.
"""
import re
import subprocess
from typing import Any

from agent.state import Phase0State

#: Changed lines hinting at semantics that dynamic experiments and mutation
#: testing should budget for (messaging / cache / data / security+tx).
_SEMANTIC_HINTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("messaging", re.compile(
        r"convertAndSend\(|rabbitTemplate|publish\(",
    )),
    ("cache", re.compile(
        r"redisTemplate|opsForValue|@Cache|evict|cacheManager",
    )),
    ("data", re.compile(
        r"\.save\(|\.saveAndFlush\(|\.delete\(|@Query|existsBy|Repository",
    )),
    ("security_tx", re.compile(
        r"@PreAuthorize|@Transactional|@Version|SecurityContext|@Secured",
    )),
)


class _GitDiffError(RuntimeError):
    """git diff failed; the caller records it in state errors."""


def _git(
    repo_path: str, *args: str, timeout: int = 30,
) -> str:
    proc = subprocess.run(
        ["git", "-C", repo_path, *args],
        capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise _GitDiffError(proc.stderr.strip()[:300] or "git exited non-zero")
    return proc.stdout


def _is_binary_change(repo_path: str, base_ref: str, head_ref: str, f: str) -> bool:
    """numstat '-' in both columns marks a binary file change."""
    try:
        numstat = _git(
            repo_path, "diff", "--numstat", base_ref, head_ref, "--", f,
        )
    except _GitDiffError:
        return False
    for line in numstat.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "-" and parts[1] == "-":
            return True
    return False


def collect_diff_node(state: Phase0State) -> dict[str, Any]:
    """Collect and analyze the git diff between base and head."""
    repo_path = state.get("repo_path", "")
    base_ref = state.get("base_ref", "base")
    head_ref = state.get("head_ref", "head-v1")
    errors: list[str] = list(state.get("errors", []))

    changed_symbols: list[str] = []
    changed_files: list[str] = []
    semantic_candidates: list[dict[str, Any]] = []
    unresolved_changes: list[dict[str, Any]] = []
    diff_by_file: dict[str, str] = {}

    try:
        name_only = _git(repo_path, "diff", "--name-only", base_ref, head_ref)
    except _GitDiffError as exc:
        errors.append(f"git diff failed: {exc}")
        return {"changed_symbols": [], "errors": errors}

    changed_files = [
        f.strip() for f in name_only.splitlines() if f.strip()
    ]

    java_files = [f for f in changed_files if f.endswith(".java")]
    for jf in java_files:
        try:
            diff_text = _git(repo_path, "diff", base_ref, head_ref, "--", jf)
        except _GitDiffError as exc:
            errors.append(f"git diff for {jf} failed: {exc}")
            continue
        diff_by_file[jf] = diff_text

        sym_re = re.compile(
            r"[-+]\s*(@\w+.*|public\s+\w+\s+\w+\(|private\s+\w+\s+\w+\()"
        )
        removed = sym_re.findall(
            "\n".join(line for line in diff_text.splitlines() if line.startswith("-"))
        )
        added = sym_re.findall(
            "\n".join(line for line in diff_text.splitlines() if line.startswith("+"))
        )

        for sym in removed:
            changed_symbols.append(f"REMOVED: {sym.strip()} in {jf}")
        for sym in added:
            changed_symbols.append(f"ADDED: {sym.strip()} in {jf}")

        annotations_removed = re.findall(
            r"-\s*(@PreAuthorize|@Transactional|@Secured|@RolesAllowed)\([^)]*\)",
            diff_text,
        )
        for ann in annotations_removed:
            changed_symbols.append(f"ANNOTATION_REMOVED: {ann} in {jf}")

        # ── Semantic candidate scope (§14.1) ──
        touched_lines = "\n".join(
            line[1:] for line in diff_text.splitlines()
            if line[:1] in ("-", "+") and len(line) > 1
        )
        counts = {
            kind: len(pattern.findall(touched_lines))
            for kind, pattern in _SEMANTIC_HINTS
        }
        hints = [kind for kind, count in counts.items() if count > 0]
        if hints:
            semantic_candidates.append({
                "file": jf,
                "hints": hints,
                "hint_counts": {kind: counts[kind] for kind in hints},
            })

    # ── Unresolved changes: never silently dropped (§14.1) ──
    for f in changed_files:
        if f.endswith(".java"):
            continue
        if _is_binary_change(repo_path, base_ref, head_ref, f):
            reason = "binary change — no parser registered"
        else:
            ext = f.rsplit(".", 1)[-1] if "." in f else "(no extension)"
            reason = (
                f"language '{ext}' — no static adapter registered "
                "(Java/Maven is the only supported target)"
            )
        unresolved_changes.append({"file": f, "reason": reason})

    if not changed_symbols and not changed_files:
        changed_symbols = ["No changes detected between base and head"]

    return {
        "changed_symbols": changed_symbols,
        "changed_files": changed_files,
        "semantic_candidates": semantic_candidates,
        "unresolved_changes": unresolved_changes,
        "diff_by_file": diff_by_file,
    }
