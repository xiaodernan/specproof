"""Cache integrity verification for sandbox dependency caches (backlog #7).

Threat model: the dependency cache the sandbox mounts — MAVEN_USER_HOME
(/home/maven/.m2) or a venv — is writable, shared state. A poisoned entry
(a swapped jar, tampered version metadata) would be silently consumed by
the next build, turning the cache into a supply-chain attack on the
verification pipeline itself.

Defense: compare the cache contents against a digest manifest recorded at
seed time and enforce a fail-closed policy on the next execution:

- every manifest entry must exist and hash to the expected sha256;
- an absent entry is an integrity failure, never silently trusted;
- oversized entries are flagged instead of hashed (a hostile giant file
  must not OOM the verifier);
- on mismatch the verdict is FAIL (refuse to execute) or REBUILD (delete
  the poisoned entries so the caller can re-seed), never "use".

Manifest format (JSON, produced by the seed step):
    {"rel/path/in/cache": "<64-hex sha256>", ...}

Docker-mode note (honest gap): the runner cannot read a docker NAMED
volume from the host, so the pre-run check applies to host-accessible
cache directories (local/development mode and host-seeded caches).
Verifying the in-container volume requires a verification step inside
the sandbox — a documented follow-up, see docs/operations/THREAT_TESTING.md.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

# Entries larger than this are reported as mismatches instead of being
# read into memory and hashed (fail-closed, and the verifier itself must
# not become an OOM vector). Configurable for tests.
MAX_ENTRY_BYTES = 512 * 1024 * 1024


class CacheManifestError(ValueError):
    """The digest manifest is missing, unreadable or malformed."""


@dataclass(frozen=True)
class DigestMismatch:
    """One manifest entry whose cached bytes do not hash to the expected digest."""

    rel_path: str
    expected: str
    actual: str


@dataclass(frozen=True)
class CacheCheck:
    """Outcome of enforcing cache integrity before an execution."""

    ok: bool
    verdict: str  # "use" | "fail" | "rebuild"
    mismatches: tuple[DigestMismatch, ...] = ()
    removed: tuple[str, ...] = ()
    note: str = ""


def sha256_hex(data: bytes) -> str:
    """Hex sha256 of raw artifact bytes (same shape as craft.schemas.Artifact)."""
    return hashlib.sha256(data).hexdigest()


def load_manifest(path: str | Path) -> dict[str, str]:
    """Load a digest manifest; malformed content raises CacheManifestError.

    Fail-closed: a manifest that cannot be read or validated is an error,
    never a silent "nothing to verify".
    """
    raw_path = Path(path)
    try:
        text = raw_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CacheManifestError(f"缓存清单不可读 {raw_path}: {exc}") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CacheManifestError(f"缓存清单不是合法 JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise CacheManifestError("缓存清单必须是 JSON 对象 {rel_path: sha256}")
    manifest: dict[str, str] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise CacheManifestError("缓存清单的键与值必须都是字符串")
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise CacheManifestError(f"缓存清单条目 {key!r} 的摘要不是 64 位 hex sha256")
        manifest[key] = value
    return manifest


def _resolve_entry(root: Path, rel_path: str) -> Path:
    """Resolve a manifest entry inside the cache root; reject escapes."""
    raw = Path(rel_path)
    if raw.is_absolute() or ".." in raw.parts:
        raise CacheManifestError(f"缓存清单条目路径逃逸: {rel_path!r}")
    candidate = (root / raw).resolve()
    if not candidate.is_relative_to(root):
        raise CacheManifestError(f"缓存清单条目路径逃逸: {rel_path!r}")
    return candidate


def verify_cache_dir(
    root: str | Path,
    manifest: Mapping[str, str],
    *,
    max_entry_bytes: int = MAX_ENTRY_BYTES,
) -> list[DigestMismatch]:
    """Compare every manifest entry against the cached bytes.

    A poisoned artifact (content swapped after seeding) hashes differently;
    an entry missing from the cache or oversized is also a mismatch — an
    incomplete cache is an integrity failure, never silently trusted.
    """
    cache_root = Path(root).resolve()
    mismatches: list[DigestMismatch] = []
    for rel_path, expected in manifest.items():
        entry = _resolve_entry(cache_root, rel_path)
        try:
            size = entry.stat().st_size
        except OSError:
            mismatches.append(DigestMismatch(rel_path, expected, "<absent>"))
            continue
        if size > max_entry_bytes:
            mismatches.append(DigestMismatch(rel_path, expected, f"<oversized:{size}>"))
            continue
        try:
            data = entry.read_bytes()
        except OSError:
            mismatches.append(DigestMismatch(rel_path, expected, "<unreadable>"))
            continue
        actual = sha256_hex(data)
        if actual != expected:
            mismatches.append(DigestMismatch(rel_path, expected, actual))
    return mismatches


def _remove_poisoned(
    root: Path, mismatches: list[DigestMismatch],
) -> tuple[list[str], str | None]:
    """Delete poisoned entries (inside the root only); report the first failure."""
    removed: list[str] = []
    for mismatch in mismatches:
        if mismatch.actual in ("<absent>",):
            continue  # nothing to delete; the caller must re-seed it
        entry = _resolve_entry(root, mismatch.rel_path)
        try:
            if entry.is_file():
                entry.unlink()
            elif entry.exists():
                entry.rmdir()
            removed.append(mismatch.rel_path)
        except OSError as exc:
            return removed, f"删除投毒条目失败 {mismatch.rel_path}: {exc}"
    return removed, None


def enforce_cache_integrity(
    cache_dir: str | Path,
    manifest: str | Mapping[str, str],
    *,
    on_poison: str = "fail",
) -> CacheCheck:
    """Verify the cache and return the enforcement verdict.

    - clean cache           -> verdict "use"
    - poison, on_poison=fail    -> verdict "fail" (caller must NOT execute)
    - poison, on_poison=rebuild -> poisoned entries deleted, verdict "rebuild"
      (the caller re-seeds — the sandbox itself has --network none — and
      may then execute)
    Unknown policies and malformed manifests fail closed with verdict "fail".
    """
    if on_poison not in ("fail", "rebuild"):
        raise ValueError(f"非法投毒策略 {on_poison!r} (允许: fail | rebuild)")
    root = Path(cache_dir)
    try:
        entries: Mapping[str, str] = (
            load_manifest(manifest) if isinstance(manifest, (str, os.PathLike)) else manifest
        )
        mismatches = verify_cache_dir(root, entries)
    except CacheManifestError as exc:
        return CacheCheck(ok=False, verdict="fail", note=f"缓存校验失败: {exc}")
    if not mismatches:
        return CacheCheck(
            ok=True,
            verdict="use",
            note=f"缓存完整性通过: 校验 {len(entries)} 个条目",
        )
    if on_poison == "rebuild":
        removed, failure = _remove_poisoned(root.resolve(), mismatches)
        if failure is not None:
            return CacheCheck(
                ok=False,
                verdict="fail",
                mismatches=tuple(mismatches),
                removed=tuple(removed),
                note=f"缓存投毒检测到但重建失败: {failure}",
            )
        detail = ", ".join(
            f"{m.rel_path} (期望 {m.expected[:8]}…, 实际 {m.actual[:8]}…)"
            for m in mismatches
        )
        return CacheCheck(
            ok=True,
            verdict="rebuild",
            mismatches=tuple(mismatches),
            removed=tuple(removed),
            note=f"缓存投毒检测到 {len(mismatches)} 个条目, 已删除重建: {detail}",
        )
    detail = ", ".join(
        f"{m.rel_path} (期望 {m.expected[:8]}…, 实际 {m.actual[:8]}…)"
        for m in mismatches
    )
    return CacheCheck(
        ok=False,
        verdict="fail",
        mismatches=tuple(mismatches),
        note=f"缓存投毒检测到 {len(mismatches)} 个条目, 拒绝执行 (fail-closed): {detail}",
    )


__all__ = [
    "MAX_ENTRY_BYTES",
    "CacheCheck",
    "CacheManifestError",
    "DigestMismatch",
    "enforce_cache_integrity",
    "load_manifest",
    "sha256_hex",
    "verify_cache_dir",
]
