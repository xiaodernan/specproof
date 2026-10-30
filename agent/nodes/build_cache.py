"""Shared base build-target cache for differential execution (P6).

Every golden case runs against the same base_ref, so the base compile
output is identical across cases. The first base run populates
<output_dir>/.base-build-cache/<sha>/ with target/classes and
target/test-classes; later cases seed the fresh base worktree from it and
skip the main compile (-Dmaven.main.skip=true), so the per-case base run
only compiles the injected test and executes surefire.

Head worktrees are seeded the same way (before generate_counterexamples
compiles the generated test): unchanged sources are re-dated into the past
so Maven's incremental compilation only rebuilds the PR's changed files —
plus every file that textually mentions a changed top-level type (a
conservative linkage-safety superset: Java linkage must name the type it
uses). Changed files keep their checkout mtime (now), so they win the
staleness check and are recompiled. If Maven's staleness logic ever
disagrees, the failure mode is a full recompile — correct, just slower;
the cache can never serve stale changed classes.

Cache safety: only the compiled class trees are cached. surefire reports
and the file-based H2 database under target/ are deliberately excluded —
evidence and DB state must be produced fresh by each case's own run.
Resource outputs inside the class trees ride along in the cache but are not
restored: the resources phase regenerates them from the case's own sources
and must own the files it writes (see `_drop_regenerated_resources`).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from agent.state import Phase0State

_EPOCH = 946684800  # 2000-01-01T00:00:00Z — older than any cached class file
_CACHE_SUBDIR = ".base-build-cache"


def base_build_cache_dir(state: Phase0State) -> Path | None:
    """Cache directory keyed by the base ref's commit sha (None if unknown)."""
    repo_path = state.get("repo_path", "")
    base_ref = state.get("base_ref", "base")
    output_dir = state.get("output_dir", "reports")
    if not repo_path:
        return None
    try:
        proc = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", base_ref],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        sha = proc.stdout.strip()
        if proc.returncode != 0 or not sha:
            return None
    except Exception:  # noqa: BLE001 — no base sha means no cache dir; the caller builds uncached
        return None
    return Path(output_dir) / _CACHE_SUBDIR / sha


def _copy_class_trees(src: Path, dst: Path) -> bool:
    """Copy classes/ and test-classes/ from src into dst."""
    try:
        for sub in ("classes", "test-classes"):
            source = src / sub
            if source.is_dir():
                shutil.copytree(source, dst / sub, dirs_exist_ok=True)
        return True
    except OSError:
        return False


def _widen_for_the_sandbox(root: Path) -> None:
    """Make a restored class tree writable by the sandbox workload (#534).

    The cache is written by THIS process's uid (the CI runner is 1001) while
    the workload runs as SANDBOX_USER (1000) and a bind mount carries the
    host mode. copytree() preserves the cache's 0644/0755 modes, so without
    this a restored 0644 file made Maven die with `FileNotFoundException:
    ... (Permission denied)` when it opened the file for writing.

    Modes are not ownership: a rewrite that also copies file attributes
    (maven-resources-plugin's COPY_ATTRIBUTES chmod/utime) still fails with
    EPERM. That class of file is handled by
    `_drop_regenerated_resources` instead.
    """
    for path in (root, *root.rglob("*")):
        try:
            os.chmod(path, 0o777 if path.is_dir() else 0o666)
        except OSError:
            continue


def _drop_regenerated_resources(target: Path, app_dir: str) -> None:
    """Remove restored files that Maven's resources phases are about to rewrite.

    Widening the modes is not enough for these: maven-resources-plugin
    copies with COPY_ATTRIBUTES, which chmod()s and utime()s the
    destination — both return EPERM when the file belongs to the runner's
    uid (measured: `FileSystemException: ... Operation not permitted` even
    on a 0666 file). Resources are derived from src/*/resources on every
    run, so the restored copies are redundant; dropping them lets the
    sandbox uid create them fresh, which is what makes the copy succeed.

    Standard Maven layout only. A resource directory configured elsewhere in
    the POM keeps its restored file and the run fails loudly (NOT_RUN)
    rather than silently testing against the restored copy.
    """
    for sub, source_root in (
        ("classes", "src/main/resources"),
        ("test-classes", "src/test/resources"),
    ):
        root = Path(app_dir) / source_root
        if not root.is_dir():
            continue
        for source in root.rglob("*"):
            if not source.is_file():
                continue
            candidate = target / sub / source.relative_to(root)
            try:
                candidate.unlink()
            except OSError:
                continue


def restore_base_build(cache_dir: Path, app_dir: str) -> bool:
    """Seed a worktree with the cached compiled classes.

    Returns True when the cache was applied. The caller may then run Maven
    with -Dmaven.main.skip=true ONLY for the base worktree (base sources
    never change between cases, so the cached main classes are exactly the
    classes this ref builds).
    """
    target = Path(app_dir) / "target"
    if not (cache_dir / "classes").is_dir():
        return False
    target.mkdir(parents=True, exist_ok=True)
    if not _copy_class_trees(cache_dir, target):
        return False
    _drop_regenerated_resources(target, app_dir)
    for sub in ("classes", "test-classes"):
        tree = target / sub
        if tree.is_dir():
            _widen_for_the_sandbox(tree)
    return True


def save_base_build(cache_dir: Path, app_dir: str) -> bool:
    """Persist the base compile output (idempotent: first success wins)."""
    if (cache_dir / "classes").is_dir():
        return False
    target = Path(app_dir) / "target"
    if not (target / "classes").is_dir():
        return False
    cache_dir.mkdir(parents=True, exist_ok=True)
    return _copy_class_trees(target, cache_dir)


def seed_head_build(
    cache_dir: Path, app_dir: str, changed_rel_paths: list[str],
) -> bool:
    """Seed a head worktree from the base cache and re-date unchanged
    sources into the past (see module docstring). Returns True when the
    cache was applied; Maven is then expected to recompile only the
    changed files, their direct dependents and the generated test."""
    if not restore_base_build(cache_dir, app_dir):
        return False
    _re_date_unchanged_sources(app_dir, changed_rel_paths)
    return True


def freeze_unchanged_sources(app_dir: str, changed_rel_paths: list[str]) -> None:
    """Re-date unchanged sources into the past (public wrapper).

    For the BASE worktree the changed set is empty (base sources never
    change between cases), so EVERY source is re-dated and only the
    injected generated test — written afterwards with a fresh mtime —
    is recompiled under -Dmaven.main.skip=true.
    """
    _re_date_unchanged_sources(app_dir, changed_rel_paths)


def head_changed_paths(state: Phase0State) -> list[str]:
    """Paths changed between base and head, relative to the app directory."""
    repo_path = state.get("repo_path", "")
    base_ref = state.get("base_ref", "base")
    head_ref = state.get("head_ref", "head-v1")
    app_dir = state.get("app_dir", "")
    if not repo_path:
        return []
    try:
        proc = subprocess.run(
            ["git", "-C", repo_path, "diff", "--name-only", base_ref, head_ref],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if proc.returncode != 0:
            return []
        paths = [p.strip() for p in proc.stdout.splitlines() if p.strip()]
    except Exception:
        return []
    prefix = app_dir.strip("/") + "/" if app_dir else ""
    if not prefix:
        return paths
    return [
        p[len(prefix):] for p in paths if p.startswith(prefix)
    ]


def _re_date_unchanged_sources(app_dir: str, changed_rel_paths: list[str]) -> None:
    """Set unchanged source mtimes into the past; changed (and mentioning)
    files keep their checkout mtime so Maven's staleness check recompiles
    exactly the affected set."""
    changed = {p.replace("\\", "/") for p in changed_rel_paths}
    changed |= _files_mentioning_changed_types(app_dir, changed)
    for root_name in ("src/main/java", "src/test/java"):
        root = Path(app_dir) / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*.java"):
            rel = path.relative_to(Path(app_dir)).as_posix()
            if rel in changed:
                continue
            os.utime(path, (_EPOCH, _EPOCH))


def _files_mentioning_changed_types(app_dir: str, changed: set[str]) -> set[str]:
    """Every java file that textually mentions a changed top-level type.

    Java linkage must name the type it uses, so textual mention is a
    complete, conservative superset of direct dependents. Over-recompiling
    is safe; under-recompiling is what this guard prevents.
    """
    mentioned: set[str] = set()
    names = {
        Path(rel).stem
        for rel in changed
        if rel.endswith(".java") and "/src/main/java/" in rel
    }
    if not names:
        return mentioned
    patterns = [re.compile(r"\b" + re.escape(name) + r"\b") for name in names]
    for root_name in ("src/main/java", "src/test/java"):
        root = Path(app_dir) / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*.java"):
            rel = path.relative_to(Path(app_dir)).as_posix()
            if rel in changed:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if any(pattern.search(content) for pattern in patterns):
                mentioned.add(rel)
    return mentioned
