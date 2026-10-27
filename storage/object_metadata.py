"""Object metadata store — locate certificates / capsules / replay reports
by metadata instead of path inference (industrialization §A task 7).

One protocol, three interchangeable backends (same pattern as
storage.agent_jobs):

- ``InMemoryObjectMetadataStore`` — development and tests;
- ``SQLiteObjectMetadataStore`` — file-based fallback, no Docker;
- ``MySQLObjectMetadataStore`` — production (MYSQL_URL or explicit URL,
  single-cursor execute-then-fetch discipline per CLAUDE.md); optional
  and gated on MYSQL_URL in integration tests.

Record shape (ObjectMetadata):
  object_id     uuid4().hex — stable identity, never the path
  kind          certificate | capsule | replay_report
  digests       {"payload_sha256": 64-hex over the payload bytes}
  job_id        owning verification job ("" when unknown)
  contract_ids  related contract ids (exact (contract_id, version) pairs
                are kept by the contract registry / lineage)
  created_at    epoch seconds (injectable clock for deterministic tests)
  path_hint     where the payload lived when recorded (advisory only —
                resolution must fall back to legacy lookup when the
                hint no longer exists)
  object_ref    the OBJECT-STORE coordinate ("bucket/object-name") — where
                the bytes actually live when they were uploaded (P1-7).
                A record carrying only a local path cannot be resolved
                on the machine that holds the bucket: the path is where
                the file WAS, the object ref is where the bytes ARE.
                Empty for file-only records.

Queries: by_job / by_kind / by_digest / by_contract. resolve_object()
tries the store FIRST (object id, digest, path hint); callers fall back
to the legacy path-based lookup for pre-existing artifacts — backward
compatible by design.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, cast

import pymysql

from storage.mysql_url import parse_mysql_url as _parse_mysql_url
from storage.unit_of_work import unit_of_work

ObjectKind = Literal["certificate", "capsule", "replay_report"]

OBJECT_KINDS: tuple[ObjectKind, ...] = ("certificate", "capsule", "replay_report")

_KIND_VALUES: frozenset[str] = frozenset(OBJECT_KINDS)

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_UUID4HEX_RE = re.compile(r"^[0-9a-f]{32}$")


class ObjectMetadataError(RuntimeError):
    """Base error for all object-metadata-store failures."""


class ObjectAlreadyExistsError(ObjectMetadataError):
    """An object with this object_id was already recorded."""


class InvalidObjectKindError(ObjectMetadataError):
    """The kind is not one of certificate | capsule | replay_report."""


class InvalidDigestError(ObjectMetadataError):
    """A stored digest is not a 64-hex sha256 payload digest."""


@dataclass(frozen=True)
class ObjectMetadata:
    """Durable projection of one stored artifact object."""

    object_id: str
    kind: ObjectKind
    digests: dict[str, str]
    job_id: str
    contract_ids: tuple[str, ...]
    created_at: float
    path_hint: str
    #: "bucket/object-name" — the object-store coordinate (P1-7).
    object_ref: str = ""


def new_object_id() -> str:
    """Fresh uuid4 hex identity (32 lowercase hex chars)."""
    return uuid.uuid4().hex


def normalize_payload_digest(value: str) -> str:
    """Normalize a payload digest: strip the sha256: prefix, lowercase."""
    stripped = value.strip().lower()
    if stripped.startswith("sha256:"):
        stripped = stripped[len("sha256:"):]
    return stripped


def normalize_object_ref(value: str) -> str:
    """Normalize an object-store reference: "bucket/object-name".

    A reference is only useful if it names a bucket AND an object, so
    a half-written reference is rejected instead of being stored as
    something that can never resolve. An empty value means "this
    record describes a file, not an object".
    """
    ref = value.strip()
    if not ref:
        return ""
    if ref.startswith("/"):
        raise ObjectMetadataError(
            f"object_ref must not start with '/': {value!r}"
        )
    bucket, sep, name = ref.partition("/")
    if not sep or not bucket or not name:
        raise ObjectMetadataError(
            f"object_ref must be 'bucket/object-name', got {value!r}"
        )
    if name.startswith("/") or name.endswith("/") or "//" in name:
        raise ObjectMetadataError(
            f"object_ref must not contain an empty path segment: {value!r}"
        )
    return f"{bucket}/{name}"


def sha256_hex(data: bytes) -> str:
    """sha256 hex digest of raw payload bytes (no prefix)."""
    return hashlib.sha256(data).hexdigest()


def payload_sha256_of_file(path: str | Path) -> str:
    """sha256 hex digest of a file's bytes (the recorded payload digest)."""
    return sha256_hex(Path(path).read_bytes())


def new_metadata(
    kind: ObjectKind,
    digests: Mapping[str, str],
    *,
    job_id: str = "",
    contract_ids: Iterable[str] = (),
    path_hint: str = "",
    object_ref: str = "",
    object_id: str | None = None,
    now: Callable[[], float] | None = None,
) -> ObjectMetadata:
    """Validated constructor used by artifact writers."""
    if kind not in _KIND_VALUES:
        raise InvalidObjectKindError(
            f"unknown object kind {kind!r}; expected one of {OBJECT_KINDS}"
        )
    normalized: dict[str, str] = {}
    for key, value in digests.items():
        normalized[key] = normalize_payload_digest(value)
    payload = normalized.get("payload_sha256", "")
    if not _HEX64_RE.fullmatch(payload):
        raise InvalidDigestError(
            "ObjectMetadata requires a payload_sha256 digest (64-hex sha256)"
        )
    oid = object_id or new_object_id()
    if not _UUID4HEX_RE.fullmatch(oid):
        raise ObjectMetadataError(
            f"object_id must be uuid4().hex (32 hex chars), got {oid!r}"
        )
    clock = now if now is not None else time.time
    return ObjectMetadata(
        object_id=oid,
        kind=kind,
        digests=normalized,
        job_id=job_id,
        contract_ids=tuple(dict.fromkeys(str(c) for c in contract_ids if c)),
        created_at=clock(),
        path_hint=path_hint,
        object_ref=normalize_object_ref(object_ref),
    )


class ObjectMetadataStore(Protocol):
    """Single source of truth for artifact metadata semantics."""

    def record(self, metadata: ObjectMetadata) -> ObjectMetadata:
        """Store one object record. Raises ObjectAlreadyExistsError on a
        duplicate object_id — records are append-only."""
        ...

    def get(self, object_id: str) -> ObjectMetadata | None:
        """The record with this exact object_id, or None."""
        ...

    def by_job(self, job_id: str) -> list[ObjectMetadata]:
        """All records for a verification job, newest first."""
        ...

    def by_kind(self, kind: ObjectKind) -> list[ObjectMetadata]:
        """All records of one kind, newest first."""
        ...

    def by_digest(self, digest: str) -> list[ObjectMetadata]:
        """All records whose payload_sha256 equals the normalized digest."""
        ...

    def by_contract(self, contract_id: str) -> list[ObjectMetadata]:
        """All records related to a contract id, newest first."""
        ...

    def list(self, limit: int = 1000) -> list[ObjectMetadata]:
        """Records newest first (bounded scan for path-hint resolution)."""
        ...

    def ensure_schema(self) -> None:
        """Create tables when they do not exist (idempotent)."""
        ...

    def close(self) -> None:
        """Release backend resources."""
        ...


def _same_file(left: str, right: str) -> bool:
    """True when two path spellings name the same file.

    A record may spell its path absolutely while the reference spells
    it relative - the same file, two spellings. Comparing the strings
    would call them different files, and the lookup would then land on
    an OLDER record for the same file, whose digest describes bytes
    that are long gone. The digest check would then report a mismatch
    for a file that is perfectly intact (a false alarm trains people
    to ignore the real ones).
    """
    try:
        return Path(left).resolve() == Path(right).resolve()
    except OSError:  # pragma: no cover - resolve() is total on CPython
        return False


def _payload_digest_if_readable(path: str) -> str:
    """The file's payload digest, or "" when the file cannot be read."""
    try:
        return payload_sha256_of_file(path)
    except OSError:
        return ""


def resolve_object(
    store: ObjectMetadataStore, reference: str,
) -> ObjectMetadata | None:
    """Resolve a reference through the metadata store FIRST.

    Accepted references:
      - object_id (32-hex uuid4);
      - payload digest (64-hex, optionally sha256:-prefixed);
      - a path - matched against recorded path_hint (exact, then the
        same file spelled differently, then suffix match so absolute
        recorded hints resolve from relative cwd).

    A path resolves to the record that describes the bytes that are
    there NOW: the same path is written again by every run, so the
    store holds one record per version, and the digest is what tells
    the versions apart. When no recorded version matches the bytes on
    disk, the NEWEST record for that path is returned, so the caller
    can report the truth ("this file is not the one we recorded").

    Returns None when the store has no record — callers then fall back to
    the legacy path-based lookup, which keeps pre-existing artifacts
    (created before this store existed) fully supported.
    """
    ref = reference.strip()
    if not ref:
        return None
    if _UUID4HEX_RE.fullmatch(ref):
        return store.get(ref)
    digest = normalize_payload_digest(ref)
    if _HEX64_RE.fullmatch(digest):
        matches = store.by_digest(digest)
        return matches[0] if matches else None
    # The object-store coordinate ("bucket/object-name", P1-7): the
    # reference the bucket actually understands, and the only one a
    # different machine can resolve.
    for record in store.list():
        if record.object_ref and record.object_ref == ref:
            return record
    normalized_path = str(Path(ref))
    records = store.list()
    # A path resolves to the record that describes the bytes that are
    # there NOW. The same path is written again by every run, so the
    # store holds one record per version; picking the first spelling
    # that matches made the digest check compare the current file
    # against a record for bytes that no longer exist.
    actual = _payload_digest_if_readable(ref)
    wanted_name = Path(normalized_path).name

    def _describes(record: ObjectMetadata) -> bool:
        if not actual:
            return False
        return normalize_payload_digest(
            record.digests.get("payload_sha256", "")
        ) == actual

    # Candidates, newest first (store.list() is newest-first): the
    # same file spelled exactly as the reference, or spelled
    # differently (absolute vs relative).
    candidates: list[ObjectMetadata] = []
    for record in records:
        hint = record.path_hint
        if not hint:
            continue
        if hint in (ref, normalized_path):
            candidates.append(record)
            continue
        if wanted_name and not hint.replace("\\", "/").endswith(
            "/" + wanted_name
        ):
            continue
        if _same_file(hint, ref):
            candidates.append(record)
    for record in candidates:
        if _describes(record):
            return record
    if candidates:
        # No recorded version describes the bytes on disk: the NEWEST
        # record for that path, so the caller can say the truth
        # ("this file is not the one we recorded").
        return candidates[0]
    # Suffix match: a recorded hint that ends with the reference (the
    # pre-store artifacts live under paths the caller knows partially).
    for record in records:
        hint = record.path_hint.replace("\\", "/")
        wanted = normalized_path.replace("\\", "/")
        if hint and (hint.endswith("/" + wanted) or hint == wanted):
            return record
    return None


def default_object_metadata_store() -> ObjectMetadataStore:
    """Process-wide default backend for CLI wiring.

    - SPECPROOF_OBJECT_METADATA_BACKEND=memory → in-memory (tests);
    - SPECPROOF_OBJECT_METADATA_DB=<path> → SQLite at that path;
    - otherwise SQLite at ~/.specproof/object-metadata.sqlite3 (stable
      across separate CLI invocations — a verify in one process and a
      replay in another share the same store).

    MySQL is deliberately NOT the implicit default: construct
    MySQLObjectMetadataStore explicitly (or MYSQL_URL + that class), the
    same discipline as storage.agent_jobs.
    """
    backend = os.getenv("SPECPROOF_OBJECT_METADATA_BACKEND", "")
    if backend == "memory":
        return InMemoryObjectMetadataStore()
    db_path = os.getenv("SPECPROOF_OBJECT_METADATA_DB", "")
    if db_path:
        return SQLiteObjectMetadataStore(db_path)
    home = Path.home() / ".specproof"
    home.mkdir(parents=True, exist_ok=True)
    return SQLiteObjectMetadataStore(home / "object-metadata.sqlite3")




def record_file_object(
    store: ObjectMetadataStore,
    kind: ObjectKind,
    path: str | Path,
    *,
    job_id: str = "",
    contract_ids: Iterable[str] = (),
) -> ObjectMetadata:
    """Record an on-disk artifact: the payload digest comes from the file.

    path_hint is stored as the resolved absolute path; resolution later
    falls back to legacy path-based lookup when the hint is gone.
    """
    resolved = Path(path).resolve()
    return store.record(new_metadata(
        kind,
        {"payload_sha256": payload_sha256_of_file(resolved)},
        job_id=job_id,
        contract_ids=contract_ids,
        path_hint=str(resolved),
    ))


def record_file_object_best_effort(
    kind: ObjectKind,
    path: str | Path,
    *,
    job_id: str = "",
    contract_ids: Iterable[str] = (),
) -> ObjectMetadata | None:
    """Record through the default store, never raising.

    Artifact writing must never break because the metadata store is
    unavailable (same honesty contract as the MySQL audit path): the
    failure is logged, the artifact stays intact, and legacy path-based
    lookup keeps working for it.
    """
    import logging

    try:
        store = default_object_metadata_store()
        return record_file_object(
            store, kind, path, job_id=job_id, contract_ids=contract_ids,
        )
    except Exception as exc:  # noqa: BLE001 — metadata is best effort
        logging.getLogger(__name__).warning(
            "object metadata record failed for %s: %s", path, exc,
        )
        return None


# ── Shared SQL (portable: ? placeholders, no MySQL-only DDL) ─────────────


_SCHEMA_SQL = (
    "CREATE TABLE IF NOT EXISTS object_metadata ("
    "object_id VARCHAR(32) PRIMARY KEY, "
    "kind VARCHAR(32) NOT NULL, "
    "payload_sha256 VARCHAR(64) NOT NULL DEFAULT '', "
    "digests_json TEXT NOT NULL, "
    "job_id VARCHAR(128) NOT NULL DEFAULT '', "
    "contract_ids_json TEXT NOT NULL DEFAULT '[]', "
    "created_at REAL NOT NULL, "
    "path_hint TEXT NOT NULL DEFAULT '', "
    "object_ref VARCHAR(255) NOT NULL DEFAULT '')"
)

_CONTRACTS_SCHEMA_SQL = (
    "CREATE TABLE IF NOT EXISTS object_contracts ("
    "object_id VARCHAR(32) NOT NULL, "
    "contract_id VARCHAR(128) NOT NULL, "
    "PRIMARY KEY (object_id, contract_id))"
)

#: MySQL refuses a DEFAULT on a TEXT/BLOB/JSON column, so the
#: production DDL is its own: the same columns, typed VARCHAR.
#: Reusing the SQLite DDL here is what made ensure_schema() fail on
#: MySQL — the table was never created and the backend was dead.
_MYSQL_SCHEMA_SQL = (
    "CREATE TABLE IF NOT EXISTS object_metadata ("
    "object_id VARCHAR(32) PRIMARY KEY, "
    "kind VARCHAR(32) NOT NULL, "
    "payload_sha256 VARCHAR(64) NOT NULL DEFAULT '', "
    "digests_json VARCHAR(4096) NOT NULL, "
    "job_id VARCHAR(128) NOT NULL DEFAULT '', "
    "contract_ids_json VARCHAR(4096) NOT NULL, "
    "created_at DOUBLE NOT NULL, "
    "path_hint VARCHAR(1024) NOT NULL DEFAULT '', "
    "object_ref VARCHAR(255) NOT NULL DEFAULT '')"
)

_MYSQL_CONTRACTS_SCHEMA_SQL = (
    "CREATE TABLE IF NOT EXISTS object_contracts ("
    "object_id VARCHAR(32) NOT NULL, "
    "contract_id VARCHAR(128) NOT NULL, "
    "PRIMARY KEY (object_id, contract_id))"
)

_INSERT_SQL = (
    "INSERT INTO object_metadata "
    "(object_id, kind, payload_sha256, digests_json, job_id, "
    "contract_ids_json, created_at, path_hint, object_ref) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_INSERT_CONTRACT_SQL = (
    "INSERT INTO object_contracts (object_id, contract_id) VALUES (?, ?)"
)

_SELECT_BY_ID_SQL = (
    "SELECT object_id, kind, digests_json, job_id, contract_ids_json, "
    "created_at, path_hint, object_ref FROM object_metadata WHERE object_id = ?"
)

_SELECT_BY_JOB_SQL = (
    "SELECT object_id, kind, digests_json, job_id, contract_ids_json, "
    "created_at, path_hint, object_ref FROM object_metadata WHERE job_id = ? "
    "ORDER BY created_at DESC, object_id"
)

_SELECT_BY_KIND_SQL = (
    "SELECT object_id, kind, digests_json, job_id, contract_ids_json, "
    "created_at, path_hint, object_ref FROM object_metadata WHERE kind = ? "
    "ORDER BY created_at DESC, object_id"
)

_SELECT_BY_DIGEST_SQL = (
    "SELECT object_id, kind, digests_json, job_id, contract_ids_json, "
    "created_at, path_hint, object_ref FROM object_metadata WHERE payload_sha256 = ? "
    "ORDER BY created_at DESC, object_id"
)

_SELECT_BY_CONTRACT_SQL = (
    "SELECT m.object_id, m.kind, m.digests_json, m.job_id, "
    "m.contract_ids_json, m.created_at, m.path_hint, m.object_ref "
    "FROM object_metadata m "
    "JOIN object_contracts c ON c.object_id = m.object_id "
    "WHERE c.contract_id = ? "
    "ORDER BY m.created_at DESC, m.object_id"
)

_SELECT_ALL_SQL = (
    "SELECT object_id, kind, digests_json, job_id, contract_ids_json, "
    "created_at, path_hint, object_ref FROM object_metadata "
    "ORDER BY created_at DESC, object_id LIMIT ?"
)


def _migrate_object_ref_sqlite(conn: Any) -> None:
    """Add object_ref to a store created before P1-7.

    CREATE TABLE IF NOT EXISTS never touches an existing table,
    so a store written by an older build would keep working until
    the first SELECT that names the new column — and then fail
    with a column error that looks like corruption. The column
    is added here instead, with the same default the schema
    declares.
    """
    columns = {row[1] for row in conn.execute(
        "PRAGMA table_info(object_metadata)"
    )}
    if "object_ref" not in columns:
        conn.execute(
            "ALTER TABLE object_metadata ADD COLUMN object_ref "
            "VARCHAR(255) NOT NULL DEFAULT ''"
        )


def _migrate_object_ref_mysql(cursor: Any) -> None:
    """Add object_ref to a MySQL table created before P1-7."""
    cursor.execute(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = DATABASE() "
        "AND table_name = 'object_metadata' "
        "AND column_name = 'object_ref'"
    )
    row = cursor.fetchone()
    present = int(row["COUNT(*)"] if isinstance(row, dict) else row[0])
    if not present:
        cursor.execute(
            "ALTER TABLE object_metadata ADD COLUMN object_ref "
            "VARCHAR(255) NOT NULL DEFAULT ''"
        )


def _to_mysql(sql: str) -> str:
    """Translate the shared ? placeholder SQL to PyMySQL %s."""
    return sql.replace("?", "%s")


def _validate_kind(kind: str) -> ObjectKind:
    if kind not in _KIND_VALUES:
        raise InvalidObjectKindError(
            f"unknown object kind {kind!r}; expected one of {OBJECT_KINDS}"
        )
    return cast(ObjectKind, kind)


def _row_to_metadata(row: Any) -> ObjectMetadata:
    import json

    digests_raw = cast(str, row["digests_json"])
    contract_ids_raw = cast(str, row["contract_ids_json"] or "[]")
    digests = json.loads(digests_raw) if isinstance(digests_raw, str) else dict(digests_raw)
    contract_ids = (
        json.loads(contract_ids_raw)
        if isinstance(contract_ids_raw, str)
        else list(contract_ids_raw)
    )
    return ObjectMetadata(
        object_id=cast(str, row["object_id"]),
        kind=_validate_kind(cast(str, row["kind"])),
        digests={str(k): str(v) for k, v in digests.items()},
        job_id=cast(str, row["job_id"] or ""),
        contract_ids=tuple(str(c) for c in contract_ids),
        created_at=float(row["created_at"]),
        path_hint=cast(str, row["path_hint"] or ""),
        object_ref=cast(str, row["object_ref"] or ""),
    )


# ── In-memory backend ─────────────────────────────────────────────────────


class InMemoryObjectMetadataStore:
    """Thread-safe in-memory backend — development and tests."""

    def __init__(self, *, now_fn: Callable[[], float] | None = None) -> None:
        self._now_fn = now_fn if now_fn is not None else time.time
        self._lock = threading.RLock()
        self._records: dict[str, ObjectMetadata] = {}
        self._contracts: dict[str, set[str]] = {}

    def ensure_schema(self) -> None:
        return None

    def close(self) -> None:
        return None

    def record(self, metadata: ObjectMetadata) -> ObjectMetadata:
        with self._lock:
            if metadata.object_id in self._records:
                raise ObjectAlreadyExistsError(
                    f"object {metadata.object_id!r} already recorded"
                )
            self._records[metadata.object_id] = metadata
            for contract_id in metadata.contract_ids:
                self._contracts.setdefault(contract_id, set()).add(metadata.object_id)
        return metadata

    def get(self, object_id: str) -> ObjectMetadata | None:
        with self._lock:
            return self._records.get(object_id)

    def by_job(self, job_id: str) -> list[ObjectMetadata]:
        with self._lock:
            rows = [r for r in self._records.values() if r.job_id == job_id]
        return sorted(rows, key=lambda r: r.created_at, reverse=True)

    def by_kind(self, kind: ObjectKind) -> list[ObjectMetadata]:
        _validate_kind(kind)
        with self._lock:
            rows = [r for r in self._records.values() if r.kind == kind]
        return sorted(rows, key=lambda r: r.created_at, reverse=True)

    def by_digest(self, digest: str) -> list[ObjectMetadata]:
        wanted = normalize_payload_digest(digest)
        with self._lock:
            rows = [
                r for r in self._records.values()
                if normalize_payload_digest(r.digests.get("payload_sha256", "")) == wanted
            ]
        return sorted(rows, key=lambda r: r.created_at, reverse=True)

    def by_contract(self, contract_id: str) -> list[ObjectMetadata]:
        with self._lock:
            ids = set(self._contracts.get(contract_id, ()))
            rows = [self._records[oid] for oid in ids if oid in self._records]
        return sorted(rows, key=lambda r: r.created_at, reverse=True)

    def list(self, limit: int = 1000) -> list[ObjectMetadata]:
        with self._lock:
            rows = list(self._records.values())
        return sorted(rows, key=lambda r: r.created_at, reverse=True)[:limit]


# ── SQLite backend ────────────────────────────────────────────────────────


class SQLiteObjectMetadataStore:
    """File-based SQLite backend (dev fallback; unit tests run it, no Docker).

    One connection per store instance, serialized by a lock;
    check_same_thread=False plus the lock keeps concurrent threads safe.
    The schema is created in __init__.
    """

    def __init__(
        self, path: str | Path, *, now_fn: Callable[[], float] | None = None,
    ) -> None:
        self._now_fn = now_fn if now_fn is not None else time.time
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(_SCHEMA_SQL)
            self._conn.execute(_CONTRACTS_SCHEMA_SQL)
            _migrate_object_ref_sqlite(self._conn)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def record(self, metadata: ObjectMetadata) -> ObjectMetadata:
        import json

        with self._lock, self._conn:
            try:
                self._conn.execute(
                    _INSERT_SQL,
                    (
                        metadata.object_id,
                        metadata.kind,
                        metadata.digests.get("payload_sha256", ""),
                        json.dumps(metadata.digests, sort_keys=True),
                        metadata.job_id,
                        json.dumps(list(metadata.contract_ids)),
                        metadata.created_at,
                        metadata.path_hint,
                        metadata.object_ref,
                    ),
                )
                for contract_id in metadata.contract_ids:
                    self._conn.execute(
                        _INSERT_CONTRACT_SQL, (metadata.object_id, contract_id),
                    )
            except sqlite3.IntegrityError as exc:
                raise ObjectAlreadyExistsError(
                    f"object {metadata.object_id!r} already recorded"
                ) from exc
        return metadata

    def get(self, object_id: str) -> ObjectMetadata | None:
        with self._lock:
            row = self._conn.execute(_SELECT_BY_ID_SQL, (object_id,)).fetchone()
        return None if row is None else _row_to_metadata(row)

    def by_job(self, job_id: str) -> list[ObjectMetadata]:
        with self._lock:
            rows = self._conn.execute(_SELECT_BY_JOB_SQL, (job_id,)).fetchall()
        return [_row_to_metadata(row) for row in rows]

    def by_kind(self, kind: ObjectKind) -> list[ObjectMetadata]:
        _validate_kind(kind)
        with self._lock:
            rows = self._conn.execute(_SELECT_BY_KIND_SQL, (kind,)).fetchall()
        return [_row_to_metadata(row) for row in rows]

    def by_digest(self, digest: str) -> list[ObjectMetadata]:
        wanted = normalize_payload_digest(digest)
        with self._lock:
            rows = self._conn.execute(_SELECT_BY_DIGEST_SQL, (wanted,)).fetchall()
        return [_row_to_metadata(row) for row in rows]

    def by_contract(self, contract_id: str) -> list[ObjectMetadata]:
        with self._lock:
            rows = self._conn.execute(
                _SELECT_BY_CONTRACT_SQL, (contract_id,),
            ).fetchall()
        return [_row_to_metadata(row) for row in rows]

    def list(self, limit: int = 1000) -> list[ObjectMetadata]:
        with self._lock:
            rows = self._conn.execute(_SELECT_ALL_SQL, (limit,)).fetchall()
        return [_row_to_metadata(row) for row in rows]


# ── MySQL backend ─────────────────────────────────────────────────────────


class MySQLObjectMetadataStore:
    """Production MySQL backend (PyMySQL + DictCursor).

    One connection per operation via the connection() context manager;
    every statement uses a single cursor execute-then-fetch (CLAUDE.md
    MySQL discipline). Call ensure_schema() explicitly before first use.
    Constructed explicitly (url argument or MYSQL_URL) — never the
    implicit default.
    """

    def __init__(
        self, url: str | None = None, *, now_fn: Callable[[], float] | None = None,
    ) -> None:
        resolved = url or os.getenv("MYSQL_URL")
        if not resolved:
            raise ValueError(
                "MySQLObjectMetadataStore needs a mysql:// URL (argument or MYSQL_URL)"
            )
        self._connect_kwargs = _parse_mysql_url(resolved)
        self._now_fn = now_fn if now_fn is not None else time.time

    def _connect(self) -> pymysql.Connection:
        return pymysql.connect(**self._connect_kwargs)

    @contextmanager
    def connection(self) -> Iterator[pymysql.Connection]:
        with unit_of_work(self._connect) as conn:
            yield conn

    def close(self) -> None:
        """No-op: each operation opens and closes its own connection."""

    def ensure_schema(self) -> None:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_MYSQL_SCHEMA_SQL)
            cur.execute(_MYSQL_CONTRACTS_SCHEMA_SQL)
            _migrate_object_ref_mysql(cur)

    def record(self, metadata: ObjectMetadata) -> ObjectMetadata:
        import json

        try:
            with self.connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    _to_mysql(_INSERT_SQL),
                    (
                        metadata.object_id,
                        metadata.kind,
                        metadata.digests.get("payload_sha256", ""),
                        json.dumps(metadata.digests, sort_keys=True),
                        metadata.job_id,
                        json.dumps(list(metadata.contract_ids)),
                        metadata.created_at,
                        metadata.path_hint,
                        metadata.object_ref,
                    ),
                )
                for contract_id in metadata.contract_ids:
                    cur.execute(
                        _to_mysql(_INSERT_CONTRACT_SQL),
                        (metadata.object_id, contract_id),
                    )
        except Exception as exc:
            if _is_duplicate_key(exc):
                raise ObjectAlreadyExistsError(
                    f"object {metadata.object_id!r} already recorded"
                ) from exc
            raise
        return metadata

    def get(self, object_id: str) -> ObjectMetadata | None:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_SELECT_BY_ID_SQL), (object_id,))
            row = cur.fetchone()
        return None if row is None else _row_to_metadata(row)

    def by_job(self, job_id: str) -> list[ObjectMetadata]:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_SELECT_BY_JOB_SQL), (job_id,))
            rows = cur.fetchall()
        return [_row_to_metadata(row) for row in rows]

    def by_kind(self, kind: ObjectKind) -> list[ObjectMetadata]:
        _validate_kind(kind)
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_SELECT_BY_KIND_SQL), (kind,))
            rows = cur.fetchall()
        return [_row_to_metadata(row) for row in rows]

    def by_digest(self, digest: str) -> list[ObjectMetadata]:
        wanted = normalize_payload_digest(digest)
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_SELECT_BY_DIGEST_SQL), (wanted,))
            rows = cur.fetchall()
        return [_row_to_metadata(row) for row in rows]

    def by_contract(self, contract_id: str) -> list[ObjectMetadata]:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_SELECT_BY_CONTRACT_SQL), (contract_id,))
            rows = cur.fetchall()
        return [_row_to_metadata(row) for row in rows]

    def list(self, limit: int = 1000) -> list[ObjectMetadata]:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_SELECT_ALL_SQL), (limit,))
            rows = cur.fetchall()
        return [_row_to_metadata(row) for row in rows]


def _is_duplicate_key(exc: Exception) -> bool:
    """Best-effort duplicate-key detection (no driver-specific imports)."""
    first = exc.args[0] if exc.args else ""
    if first == 1062:
        return True
    text = str(first)
    return "UNIQUE constraint failed" in text or "Duplicate entry" in text


__all__ = [
    "OBJECT_KINDS",
    "InMemoryObjectMetadataStore",
    "InvalidDigestError",
    "InvalidObjectKindError",
    "MySQLObjectMetadataStore",
    "ObjectAlreadyExistsError",
    "ObjectMetadata",
    "ObjectMetadataError",
    "ObjectMetadataStore",
    "SQLiteObjectMetadataStore",
    "default_object_metadata_store",
    "new_metadata",
    "normalize_object_ref",
    "new_object_id",
    "normalize_payload_digest",
    "payload_sha256_of_file",
    "record_file_object",
    "record_file_object_best_effort",
    "resolve_object",
    "sha256_hex",
]
