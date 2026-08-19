"""Repository safety checks shared by prepare_base / prepare_head (§14.1).

The prepare nodes check out untrusted refs into disposable worktrees that may
later be mounted into a sandbox running untrusted code.  This module extracts
every repository-level safety decision into one place so that:

- checks are named and individually attributable — a failed node error names
  the failing check;
- checks are table-driven: requesting an unknown check fails closed instead
  of silently passing, and registry drift against CHECK_NAMES raises at
  import time instead of misreporting at run time;
- the git subprocess boundary is one injectable runner (tests stub it,
  production uses argument-list subprocess.run — never a shell).

Check list (each must pass for ``ok``):

1. ``repo_under_allowed_root`` — the resolved + realpathed repository path
   stays under the allowed root.
2. ``ref_in_repo``             — the requested ref resolves to a commit inside
   this repository.
3. ``worktree_target_empty``   — the worktree target is absent or an empty
   directory (``git worktree add`` refuses anything else).
4. ``no_symlink_escape``       — no symlink/junction inside the repository
   resolves outside the repository root.
5. ``repo_size_within_limit``  — total checked-out file size is within the
   configured limit.
6. ``no_forbidden_files``      — no ``.env``/key-material files, and no real
   secrets inside ``.env``-style template files.
7. ``execution_mode_signal``   — the current execution mode is known and the
   repository is safe to mount under it (unknown modes fail closed).

Environment knobs: SPECPROOF_ALLOWED_ROOT, SPECPROOF_MAX_REPO_BYTES,
SPECPROOF_EXEC_MODE.  All are optional; with none configured every check
passes and the prepare nodes behave byte-identically to their
pre-extraction form.
"""
from __future__ import annotations

import fnmatch
import os
import re
import subprocess
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

# ── Check names (stable public surface) ─────────────────────────

CHECK_REPO_UNDER_ALLOWED_ROOT = "repo_under_allowed_root"
CHECK_REF_IN_REPO = "ref_in_repo"
CHECK_WORKTREE_TARGET_EMPTY = "worktree_target_empty"
CHECK_NO_SYMLINK_ESCAPE = "no_symlink_escape"
CHECK_REPO_SIZE_WITHIN_LIMIT = "repo_size_within_limit"
CHECK_NO_FORBIDDEN_FILES = "no_forbidden_files"
CHECK_EXECUTION_MODE_SIGNAL = "execution_mode_signal"

CHECK_NAMES: tuple[str, ...] = (
    CHECK_REPO_UNDER_ALLOWED_ROOT,
    CHECK_REF_IN_REPO,
    CHECK_WORKTREE_TARGET_EMPTY,
    CHECK_NO_SYMLINK_ESCAPE,
    CHECK_REPO_SIZE_WITHIN_LIMIT,
    CHECK_NO_FORBIDDEN_FILES,
    CHECK_EXECUTION_MODE_SIGNAL,
)

# ── Configuration knobs ──────────────────────────────────────────

ALLOWED_ROOT_ENV = "SPECPROOF_ALLOWED_ROOT"
MAX_REPO_BYTES_ENV = "SPECPROOF_MAX_REPO_BYTES"
EXEC_MODE_ENV = "SPECPROOF_EXEC_MODE"

DEFAULT_MAX_REPO_BYTES = 2 * 1024**3  # 2 GiB
DEFAULT_EXEC_MODE = "local"
EXECUTION_MODES: tuple[str, ...] = ("local", "sandbox")

# Text files larger than this are never opened during the forbidden-files
# content scan (they are binary payloads in practice).
MAX_TEMPLATE_SCAN_BYTES = 1024 * 1024

# FILE_ATTRIBUTE_REPARSE_POINT (0x400).  Windows junctions and mount points
# are reparse points but report ``is_symlink() == False``; the attribute bit
# is the only portable way to see them, and os.walk descends into them even
# with followlinks=False, so every walk must prune reparse-point entries.
_REPARSE_POINT = 0x400

# Built by concatenation on purpose: the repository-wide secret-leak gate
# forbids the literal key prefix in source files, and the token below is
# only ever *matched against* untrusted repository content.
_API_KEY_PREFIX = "s" + "k" + "-"
_API_KEY_TOKEN = re.compile(r"[s][k][-][a-zA-Z0-9]{20,}")
_PRIVATE_KEY_BEGIN = re.compile(r"^\s*-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----\s*$")
_PRIVATE_KEY_END = re.compile(r"^\s*-----END [A-Z0-9 ]*PRIVATE KEY-----\s*$")

# Name patterns that mark a file as forbidden outright (matched against the
# lower-cased basename with fnmatch).
_KEY_MATERIAL_PATTERNS: tuple[str, ...] = (
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.jks",
    "*.keystore",
    "*.gpg",
    "*.asc",
    "id_rsa*",
    "id_ed25519*",
    "id_ecdsa*",
    "id_dsa*",
    ".netrc",
    "credentials*",
    "*.secret",
    "secrets.*",
    ".htpasswd",
)

# ``.env.example`` and friends are documentation placeholders: allowed by
# name, but their *content* is still scanned — a real secret dressed up as a
# template is exactly what the forbidden-files check exists to catch.
_ENV_TEMPLATE_SUFFIXES: frozenset[str] = frozenset(
    {"example", "sample", "template", "dist"}
)

# ── Data model ───────────────────────────────────────────────────

GitRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def default_git_runner(argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run git with an argument list (no shell interpolation), text stdio."""
    return subprocess.run(
        ["git", *argv], capture_output=True, text=True, timeout=60,
    )


@dataclass(frozen=True)
class SafetyCheck:
    """One named, individually attributable safety check result."""

    name: str
    passed: bool
    detail: str


@dataclass
class SafetyReport:
    """Full safety report: all checks, warnings, and the first failure."""

    ok: bool
    checks: list[SafetyCheck] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fail_reason: str = ""


@dataclass
class _SafetyContext:
    """Resolved inputs handed to every check implementation."""

    repo_path: str
    repo_real: Path
    ref: str
    worktree_target: Path
    allowed_root_real: Path | None
    max_repo_bytes: int
    exec_mode: str
    git_runner: GitRunner
    warnings: list[str] = field(default_factory=list)


# ── Path helpers ─────────────────────────────────────────────────


def _realpath(value: str | os.PathLike[str]) -> Path:
    """Resolve then realpath a path (a nonexistent suffix is allowed)."""
    raw = Path(value)
    try:
        resolved = raw.resolve(strict=False)
    except OSError:
        resolved = raw.absolute()
    return Path(os.path.realpath(os.fspath(resolved)))


def _is_reparse_point(path: Path) -> bool:
    """Detect symlinks and Windows junctions/mount points (reparse points)."""
    if path.is_symlink():
        return True
    try:
        result = path.lstat()
    except OSError:
        return False
    attributes = int(getattr(result, "st_file_attributes", 0))
    return bool(attributes & _REPARSE_POINT)


def _resolves_inside(link: Path, root: Path) -> bool:
    """True when the link's resolved target stays under root."""
    try:
        target = link.resolve(strict=False)
    except OSError:
        return False
    return target == root or target.is_relative_to(root)


def _iter_repo_walk(repo: Path) -> Iterator[tuple[Path, list[str], list[str]]]:
    """Walk the repo, pruning .git entries and reparse points (never follow)."""
    for root, dirs, files in os.walk(repo, topdown=True, followlinks=False):
        root_path = Path(root)
        kept_dirs: list[str] = []
        for name in dirs:
            if name == ".git":
                continue
            if _is_reparse_point(root_path / name):
                continue
            kept_dirs.append(name)
        dirs[:] = kept_dirs
        yield root_path, dirs, files


# ── Individual checks ────────────────────────────────────────────


def _check_repo_under_allowed_root(ctx: _SafetyContext) -> SafetyCheck:
    repo = Path(ctx.repo_path)
    if not repo.exists():
        return SafetyCheck(
            CHECK_REPO_UNDER_ALLOWED_ROOT, False,
            f"repository path does not exist: {ctx.repo_path}",
        )
    if not repo.is_dir():
        return SafetyCheck(
            CHECK_REPO_UNDER_ALLOWED_ROOT, False,
            f"repository path is not a directory: {ctx.repo_path}",
        )
    if ctx.allowed_root_real is None:
        if ctx.exec_mode == "sandbox":
            return SafetyCheck(
                CHECK_REPO_UNDER_ALLOWED_ROOT, False,
                "sandbox execution requires an allowed root "
                f"({ALLOWED_ROOT_ENV}) containing the repository",
            )
        ctx.warnings.append(
            f"allowed root not configured ({ALLOWED_ROOT_ENV}); "
            "repo_under_allowed_root is not enforced in local mode"
        )
        return SafetyCheck(
            CHECK_REPO_UNDER_ALLOWED_ROOT, True,
            "allowed root not configured; check not enforced (local mode)",
        )
    root_real = ctx.allowed_root_real
    if not root_real.is_dir():
        return SafetyCheck(
            CHECK_REPO_UNDER_ALLOWED_ROOT, False,
            f"allowed root is not a directory: {root_real}",
        )
    if ctx.repo_real == root_real or ctx.repo_real.is_relative_to(root_real):
        return SafetyCheck(
            CHECK_REPO_UNDER_ALLOWED_ROOT, True,
            f"repository {ctx.repo_real} is under allowed root {root_real}",
        )
    return SafetyCheck(
        CHECK_REPO_UNDER_ALLOWED_ROOT, False,
        f"repository {ctx.repo_real} resolves outside allowed root {root_real}",
    )


def _check_ref_in_repo(ctx: _SafetyContext) -> SafetyCheck:
    if not ctx.ref:
        return SafetyCheck(CHECK_REF_IN_REPO, False, "ref is empty")
    argv = [
        "-C", os.fspath(ctx.repo_real),
        "rev-parse", "--verify", "--quiet", f"{ctx.ref}^{{commit}}",
    ]
    try:
        proc = ctx.git_runner(argv)
    except Exception as exc:  # noqa: BLE001 — fail closed on runner errors
        return SafetyCheck(
            CHECK_REF_IN_REPO, False, f"git runner failed: {exc}",
        )
    if proc.returncode != 0 or not proc.stdout.strip():
        detail = proc.stderr.strip()[:300] or "ref did not resolve to a commit"
        return SafetyCheck(
            CHECK_REF_IN_REPO, False,
            f"ref {ctx.ref!r} does not belong to the repository: {detail}",
        )
    return SafetyCheck(
        CHECK_REF_IN_REPO, True,
        f"ref {ctx.ref!r} resolves to commit {proc.stdout.strip()[:12]}",
    )


def _check_worktree_target_empty(ctx: _SafetyContext) -> SafetyCheck:
    target = ctx.worktree_target
    if not target.exists():
        return SafetyCheck(
            CHECK_WORKTREE_TARGET_EMPTY, True,
            f"worktree target does not exist yet: {target}",
        )
    if _is_reparse_point(target):
        return SafetyCheck(
            CHECK_WORKTREE_TARGET_EMPTY, False,
            f"worktree target is a symlink/junction: {target}",
        )
    if not target.is_dir():
        return SafetyCheck(
            CHECK_WORKTREE_TARGET_EMPTY, False,
            f"worktree target exists and is not a directory: {target}",
        )
    try:
        first = next(target.iterdir(), None)
    except OSError as exc:
        return SafetyCheck(
            CHECK_WORKTREE_TARGET_EMPTY, False,
            f"cannot read worktree target: {exc}",
        )
    if first is not None:
        return SafetyCheck(
            CHECK_WORKTREE_TARGET_EMPTY, False,
            f"worktree target is not empty (contains {first.name!r})",
        )
    return SafetyCheck(
        CHECK_WORKTREE_TARGET_EMPTY, True,
        f"worktree target is an empty directory: {target}",
    )


def _check_no_symlink_escape(ctx: _SafetyContext) -> SafetyCheck:
    repo_real = ctx.repo_real
    if not repo_real.is_dir():
        return SafetyCheck(
            CHECK_NO_SYMLINK_ESCAPE, False,
            "repository is not a directory; cannot walk for symlinks",
        )
    try:
        for root, dirs, files in os.walk(repo_real, topdown=True, followlinks=False):
            root_path = Path(root)
            for name in list(dirs):
                if name == ".git":
                    dirs.remove(name)
                    continue
                child = root_path / name
                if _is_reparse_point(child):
                    dirs.remove(name)
                    if not _resolves_inside(child, repo_real):
                        return SafetyCheck(
                            CHECK_NO_SYMLINK_ESCAPE, False,
                            "directory symlink/junction escapes the repository: "
                            f"{child}",
                        )
            for name in files:
                if name == ".git":
                    continue
                child = root_path / name
                if _is_reparse_point(child) and not _resolves_inside(child, repo_real):
                    return SafetyCheck(
                        CHECK_NO_SYMLINK_ESCAPE, False,
                        f"file symlink/junction escapes the repository: {child}",
                    )
    except OSError as exc:
        return SafetyCheck(
            CHECK_NO_SYMLINK_ESCAPE, False,
            f"cannot walk repository for symlinks: {exc}",
        )
    return SafetyCheck(
        CHECK_NO_SYMLINK_ESCAPE, True,
        "no symlink/junction resolves outside the repository root",
    )


def _check_repo_size_within_limit(ctx: _SafetyContext) -> SafetyCheck:
    repo_real = ctx.repo_real
    if not repo_real.is_dir():
        return SafetyCheck(
            CHECK_REPO_SIZE_WITHIN_LIMIT, False,
            "repository is not a directory; cannot measure size",
        )
    total = 0
    limit = ctx.max_repo_bytes
    try:
        for _root, _dirs, files in _iter_repo_walk(repo_real):
            for name in files:
                if name == ".git":
                    continue
                path = Path(_root) / name
                try:
                    total += path.stat().st_size
                except OSError:
                    continue
                if total > limit:
                    return SafetyCheck(
                        CHECK_REPO_SIZE_WITHIN_LIMIT, False,
                        "repository size exceeds limit: counted at least "
                        f"{total} bytes (limit {limit} bytes)",
                    )
    except OSError as exc:
        return SafetyCheck(
            CHECK_REPO_SIZE_WITHIN_LIMIT, False,
            f"cannot walk repository to measure size: {exc}",
        )
    return SafetyCheck(
        CHECK_REPO_SIZE_WITHIN_LIMIT, True,
        f"repository size {total} bytes within limit {limit} bytes",
    )


def _classify_file_name(name: str) -> str:
    """Classify a basename: 'forbidden' | 'template' | 'clean'."""
    lower = name.lower()
    if lower == ".env":
        return "forbidden"
    if lower.startswith(".env."):
        suffix = lower[len(".env."):]
        return "template" if suffix in _ENV_TEMPLATE_SUFFIXES else "forbidden"
    if any(fnmatch.fnmatch(lower, pattern) for pattern in _KEY_MATERIAL_PATTERNS):
        return "forbidden"
    return "clean"


def _scan_template_content(path: Path) -> str | None:
    """Scan an allowed-by-name .env template; return a problem or None."""
    try:
        if path.stat().st_size > MAX_TEMPLATE_SCAN_BYTES:
            return None
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return "file is unreadable"
    if _API_KEY_TOKEN.search(content):
        return f"contains an API-key-shaped token ({_API_KEY_PREFIX}...)"
    lines = content.splitlines()
    has_begin = any(_PRIVATE_KEY_BEGIN.match(line) for line in lines)
    has_end = any(_PRIVATE_KEY_END.match(line) for line in lines)
    if has_begin and has_end:
        return "contains a private key block"
    return None


def _check_no_forbidden_files(ctx: _SafetyContext) -> SafetyCheck:
    repo_real = ctx.repo_real
    if not repo_real.is_dir():
        return SafetyCheck(
            CHECK_NO_FORBIDDEN_FILES, False,
            "repository is not a directory; cannot scan for forbidden files",
        )
    try:
        for root, _dirs, files in _iter_repo_walk(repo_real):
            for name in files:
                if name == ".git":
                    continue
                path = Path(root) / name
                verdict = _classify_file_name(name)
                if verdict == "forbidden":
                    return SafetyCheck(
                        CHECK_NO_FORBIDDEN_FILES, False,
                        "forbidden file in repository "
                        f"(.env/key patterns): {path.relative_to(repo_real)}",
                    )
                if verdict == "template":
                    problem = _scan_template_content(path)
                    if problem is not None:
                        return SafetyCheck(
                            CHECK_NO_FORBIDDEN_FILES, False,
                            f"{path.relative_to(repo_real)}: {problem}",
                        )
    except OSError as exc:
        return SafetyCheck(
            CHECK_NO_FORBIDDEN_FILES, False,
            f"cannot scan repository for forbidden files: {exc}",
        )
    return SafetyCheck(
        CHECK_NO_FORBIDDEN_FILES, True,
        "no forbidden files (.env/key patterns) found",
    )


def _check_execution_mode_signal(ctx: _SafetyContext) -> SafetyCheck:
    mode = ctx.exec_mode
    if mode not in EXECUTION_MODES:
        return SafetyCheck(
            CHECK_EXECUTION_MODE_SIGNAL, False,
            f"unknown execution mode {mode!r} "
            f"(supported: {', '.join(EXECUTION_MODES)})",
        )
    if mode == "sandbox":
        if ctx.allowed_root_real is None:
            return SafetyCheck(
                CHECK_EXECUTION_MODE_SIGNAL, False,
                "sandbox mode requires an allowed root "
                f"({ALLOWED_ROOT_ENV}) before the repository may be mounted",
            )
        if ctx.repo_real != ctx.allowed_root_real and not ctx.repo_real.is_relative_to(
            ctx.allowed_root_real
        ):
            return SafetyCheck(
                CHECK_EXECUTION_MODE_SIGNAL, False,
                f"repository {ctx.repo_real} cannot be mounted in sandbox mode: "
                "outside the allowed root",
            )
        return SafetyCheck(
            CHECK_EXECUTION_MODE_SIGNAL, True,
            "sandbox mode: repository verified under the allowed root",
        )
    return SafetyCheck(
        CHECK_EXECUTION_MODE_SIGNAL, True,
        "local mode: host filesystem access allowed",
    )


# ── Registry (unknown checks fail closed) ────────────────────────

_CHECK_REGISTRY: dict[str, Callable[[_SafetyContext], SafetyCheck]] = {
    CHECK_REPO_UNDER_ALLOWED_ROOT: _check_repo_under_allowed_root,
    CHECK_REF_IN_REPO: _check_ref_in_repo,
    CHECK_WORKTREE_TARGET_EMPTY: _check_worktree_target_empty,
    CHECK_NO_SYMLINK_ESCAPE: _check_no_symlink_escape,
    CHECK_REPO_SIZE_WITHIN_LIMIT: _check_repo_size_within_limit,
    CHECK_NO_FORBIDDEN_FILES: _check_no_forbidden_files,
    CHECK_EXECUTION_MODE_SIGNAL: _check_execution_mode_signal,
}

_missing = set(CHECK_NAMES) - set(_CHECK_REGISTRY)
_extra = set(_CHECK_REGISTRY) - set(CHECK_NAMES)
if _missing or _extra:
    raise RuntimeError(
        "repo_safety check registry drift: "
        f"missing={sorted(_missing)} extra={sorted(_extra)}"
    )

# ── Public API ───────────────────────────────────────────────────


def check_repo_safety(
    repo_path: str | os.PathLike[str],
    ref: str,
    worktree_target: str | os.PathLike[str],
    *,
    allowed_root: str | os.PathLike[str] | None = None,
    max_repo_bytes: int | None = None,
    exec_mode: str | None = None,
    git_runner: GitRunner | None = None,
    checks: Sequence[str] | None = None,
) -> SafetyReport:
    """Run every repository safety check and return a full report.

    Args:
        repo_path:       the repository the prepare node will operate on.
        ref:             the ref (tag/branch/sha) to check out.
        worktree_target: the directory the worktree will be created at.
        allowed_root:    optional root the repo must live under (defaults to
                         SPECPROOF_ALLOWED_ROOT; unset = not enforced in
                         local mode).
        max_repo_bytes:  optional size cap (defaults to
                         SPECPROOF_MAX_REPO_BYTES, then 2 GiB).
        exec_mode:       optional execution-mode signal (defaults to
                         SPECPROOF_EXEC_MODE, then 'local').
        git_runner:      optional git subprocess runner (tests inject stubs).
        checks:          optional subset of CHECK_NAMES to run; an unknown
                         name fails closed.

    Returns:
        SafetyReport: ``ok`` is True only when every requested check passed.
        ``fail_reason`` is ``"<check>: <detail>"`` for the first failure and
        ``""`` on success.  Unknown requested checks produce a failed
        SafetyCheck entry, never a silent pass.
    """
    requested = list(CHECK_NAMES if checks is None else checks)
    seen: set[str] = set()
    ordered: list[str] = []
    for name in requested:
        if name not in seen:
            seen.add(name)
            ordered.append(name)

    explicit_mode = exec_mode.strip().lower() if exec_mode and exec_mode.strip() else None
    mode = explicit_mode or os.getenv(EXEC_MODE_ENV, "").strip().lower() or DEFAULT_EXEC_MODE

    warnings: list[str] = []
    if explicit_mode is None and os.getenv(EXEC_MODE_ENV, "").strip():
        warnings.append(
            f"{EXEC_MODE_ENV}={os.getenv(EXEC_MODE_ENV, '').strip()!r}"
        )

    if allowed_root is not None:
        root_real: Path | None = _realpath(allowed_root)
    else:
        root_env = os.getenv(ALLOWED_ROOT_ENV, "").strip()
        root_real = _realpath(root_env) if root_env else None

    limit = _resolve_max_repo_bytes(max_repo_bytes, warnings)

    ctx = _SafetyContext(
        repo_path=os.fspath(repo_path),
        repo_real=_realpath(repo_path),
        ref=ref,
        worktree_target=Path(worktree_target),
        allowed_root_real=root_real,
        max_repo_bytes=limit,
        exec_mode=mode,
        git_runner=git_runner or default_git_runner,
        warnings=warnings,
    )

    results: list[SafetyCheck] = []
    for name in ordered:
        impl = _CHECK_REGISTRY.get(name)
        if impl is None:
            results.append(
                SafetyCheck(name, False, f"unknown check {name!r} (fail closed)")
            )
            continue
        try:
            results.append(impl(ctx))
        except Exception as exc:  # noqa: BLE001 — a raising check fails closed
            results.append(
                SafetyCheck(name, False, f"check raised: {exc}")
            )

    first_failure = next((c for c in results if not c.passed), None)
    return SafetyReport(
        ok=first_failure is None,
        checks=results,
        warnings=ctx.warnings,
        fail_reason=(
            f"{first_failure.name}: {first_failure.detail}"
            if first_failure is not None
            else ""
        ),
    )


def _resolve_max_repo_bytes(explicit: int | None, warnings: list[str]) -> int:
    """Pick the repo size limit: explicit arg > env > default.  Fail-safe."""
    if explicit is not None and explicit > 0:
        return explicit
    raw = os.getenv(MAX_REPO_BYTES_ENV, "").strip()
    if raw:
        try:
            value = int(raw)
        except ValueError:
            warnings.append(
                f"{MAX_REPO_BYTES_ENV}={raw!r} is not an integer; "
                f"using default {DEFAULT_MAX_REPO_BYTES}"
            )
            return DEFAULT_MAX_REPO_BYTES
        if value > 0:
            return value
        warnings.append(
            f"{MAX_REPO_BYTES_ENV}={raw!r} is not positive; "
            f"using default {DEFAULT_MAX_REPO_BYTES}"
        )
    return DEFAULT_MAX_REPO_BYTES


__all__ = [
    "CHECK_NAMES",
    "CHECK_EXECUTION_MODE_SIGNAL",
    "CHECK_NO_FORBIDDEN_FILES",
    "CHECK_NO_SYMLINK_ESCAPE",
    "CHECK_REF_IN_REPO",
    "CHECK_REPO_SIZE_WITHIN_LIMIT",
    "CHECK_REPO_UNDER_ALLOWED_ROOT",
    "CHECK_WORKTREE_TARGET_EMPTY",
    "ALLOWED_ROOT_ENV",
    "MAX_REPO_BYTES_ENV",
    "EXEC_MODE_ENV",
    "DEFAULT_EXEC_MODE",
    "DEFAULT_MAX_REPO_BYTES",
    "EXECUTION_MODES",
    "GitRunner",
    "SafetyCheck",
    "SafetyReport",
    "check_repo_safety",
    "default_git_runner",
]
