"""Multi-tenant identity store — tenants, users, scoped API tokens.

Industrialization phase 1 (docs/architecture/MULTI_TENANT_DESIGN.md §3). One
protocol, three interchangeable backends, mirroring storage/agent_jobs.py:

* InMemoryIdentityStore — development and tests;
* SqliteIdentityStore — file-based fallback used by unit tests (no Docker);
* MySqlIdentityStore — production (PyMySQL + DictCursor, single-cursor
  execute-then-fetch discipline per CLAUDE.md).

Both SQL backends share one portable statement set ('?' placeholders,
translated to '%s' for PyMySQL). Every statement is fully static — all
values travel through placeholders, never through SQL text (bandit B608).
Timestamps are epoch seconds (float) with an injectable now_fn clock.

The production MySQL DDL is created by infra/mysql/migrations/
0005_tenant_identity.sql; MySqlIdentityStore.ensure_schema() emits the same
idempotent DDL (CREATE TABLE IF NOT EXISTS with inline indexes) so both
paths converge on one schema. The SQLite backend owns a DDL variant because
SQLite has no inline-INDEX syntax and does support CREATE INDEX IF NOT
EXISTS.

Token secrets never reach this layer: callers store the HMAC-SHA256 token
hash and the bcrypt secret hash produced by api/identity/tokens.py.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import unquote, urlsplit

import pymysql
from pymysql.cursors import DictCursor

#: The four roles of the RBAC matrix (docs/architecture/MULTI_TENANT_DESIGN.md §2).
ROLE_VALUES: tuple[str, ...] = ("admin", "operator", "viewer", "auditor")
ROLE_SET: frozenset[str] = frozenset(ROLE_VALUES)

USER_STATUS_VALUES: frozenset[str] = frozenset({"active", "disabled"})
TENANT_STATUS_VALUES: frozenset[str] = frozenset({"active", "suspended"})


class IdentityStoreError(RuntimeError):
    """Base error for every identity-store failure."""


class DuplicateUserError(IdentityStoreError):
    """A user with this (tenant, email) or oidc_sub already exists."""


class UserNotFoundError(IdentityStoreError):
    """The referenced user id does not exist."""


class DuplicateTenantError(IdentityStoreError):
    """A tenant with this id already exists."""


@dataclass(frozen=True)
class Tenant:
    id: str
    name: str
    plan_id: str
    status: str
    created_at: float


@dataclass(frozen=True)
class User:
    id: str
    tenant_id: str
    email: str
    oidc_sub: str | None
    role: str
    status: str
    created_at: float


@dataclass(frozen=True)
class ApiTokenRow:
    id: str
    user_id: str
    name: str
    token_hash: str
    secret_hash: str
    scopes: str
    expires_at: float | None
    last_used_at: float | None
    created_at: float


class IdentityStore(Protocol):
    """Single source of truth for tenant/user/token semantics."""

    def ensure_schema(self) -> None: ...
    def close(self) -> None: ...

    def create_tenant(self, name: str, plan_id: str = "free") -> Tenant: ...
    def get_tenant(self, tenant_id: str) -> Tenant | None: ...
    def list_tenants(self) -> list[Tenant]: ...

    def create_user(
        self,
        tenant_id: str,
        email: str,
        role: str = "viewer",
        status: str = "active",
        oidc_sub: str | None = None,
    ) -> User: ...
    def get_user(self, user_id: str) -> User | None: ...
    def get_user_by_email(self, tenant_id: str, email: str) -> User | None: ...
    def get_user_by_oidc_sub(self, oidc_sub: str) -> User | None: ...
    def list_users(self, tenant_id: str) -> list[User]: ...
    def update_user(
        self, user_id: str, *, role: str | None = None, status: str | None = None
    ) -> User: ...

    def create_api_token(
        self,
        user_id: str,
        name: str,
        token_hash: str,
        secret_hash: str,
        scopes: str = "",
        expires_at: float | None = None,
        token_id: str | None = None,
    ) -> ApiTokenRow: ...
    def get_token_by_hash(self, token_hash: str) -> ApiTokenRow | None: ...
    def touch_token_last_used(self, token_id: str, now: float) -> None: ...
    def revoke_token(self, token_id: str) -> bool: ...
    def list_tokens(self, user_id: str) -> list[ApiTokenRow]: ...


# ── Shared portable SQL (the hub the SQL backends read) ────────────────────────
# Fully static statements; all values travel through placeholders. Role and
# status literals inside these statements are kept in sync with ROLE_SET /
# USER_STATUS_VALUES / TENANT_STATUS_VALUES by the consistency test in
# tests/unit/test_identity_store.py.


_SCHEMA_SQLITE: str = (
    "CREATE TABLE IF NOT EXISTS tenants ("
    "id VARCHAR(36) PRIMARY KEY, "
    "name VARCHAR(255) NOT NULL, "
    "plan_id VARCHAR(64) NOT NULL DEFAULT 'free', "
    "status VARCHAR(32) NOT NULL DEFAULT 'active', "
    "created_at DOUBLE NOT NULL)"
    ";"
    "CREATE TABLE IF NOT EXISTS users ("
    "id VARCHAR(36) PRIMARY KEY, "
    "tenant_id VARCHAR(36) NOT NULL, "
    "email VARCHAR(255) NOT NULL, "
    "oidc_sub VARCHAR(255), "
    "role VARCHAR(32) NOT NULL DEFAULT 'viewer', "
    "status VARCHAR(32) NOT NULL DEFAULT 'active', "
    "created_at DOUBLE NOT NULL, "
    "UNIQUE (tenant_id, email), "
    "UNIQUE (oidc_sub))"
    ";"
    "CREATE TABLE IF NOT EXISTS api_tokens ("
    "id VARCHAR(36) PRIMARY KEY, "
    "user_id VARCHAR(36) NOT NULL, "
    "name VARCHAR(128) NOT NULL, "
    "token_hash CHAR(64) NOT NULL UNIQUE, "
    "secret_hash VARCHAR(128) NOT NULL, "
    "scopes VARCHAR(1024) NOT NULL DEFAULT '', "
    "expires_at DOUBLE, "
    "last_used_at DOUBLE, "
    "created_at DOUBLE NOT NULL)"
    ";"
    "CREATE INDEX IF NOT EXISTS idx_users_tenant ON users (tenant_id)"
    ";"
    "CREATE INDEX IF NOT EXISTS idx_tokens_user ON api_tokens (user_id)"
)

# MySQL has no CREATE INDEX IF NOT EXISTS; indexes live inline in CREATE
# TABLE so ensure_schema() stays idempotent against the migration-created
# production schema (infra/mysql/migrations/0005_tenant_identity.sql).
_SCHEMA_MYSQL: str = (
    "CREATE TABLE IF NOT EXISTS tenants ("
    "id VARCHAR(36) PRIMARY KEY, "
    "name VARCHAR(255) NOT NULL, "
    "plan_id VARCHAR(64) NOT NULL DEFAULT 'free', "
    "status VARCHAR(32) NOT NULL DEFAULT 'active', "
    "created_at DOUBLE NOT NULL"
    ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    ";"
    "CREATE TABLE IF NOT EXISTS users ("
    "id VARCHAR(36) PRIMARY KEY, "
    "tenant_id VARCHAR(36) NOT NULL, "
    "email VARCHAR(255) NOT NULL, "
    "oidc_sub VARCHAR(255), "
    "role VARCHAR(32) NOT NULL DEFAULT 'viewer', "
    "status VARCHAR(32) NOT NULL DEFAULT 'active', "
    "created_at DOUBLE NOT NULL, "
    "UNIQUE KEY uq_users_tenant_email (tenant_id, email), "
    "UNIQUE KEY uq_users_oidc_sub (oidc_sub), "
    "INDEX idx_users_tenant (tenant_id)"
    ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    ";"
    "CREATE TABLE IF NOT EXISTS api_tokens ("
    "id VARCHAR(36) PRIMARY KEY, "
    "user_id VARCHAR(36) NOT NULL, "
    "name VARCHAR(128) NOT NULL, "
    "token_hash CHAR(64) NOT NULL, "
    "secret_hash VARCHAR(128) NOT NULL, "
    "scopes VARCHAR(1024) NOT NULL DEFAULT '', "
    "expires_at DOUBLE, "
    "last_used_at DOUBLE, "
    "created_at DOUBLE NOT NULL, "
    "UNIQUE KEY uq_tokens_hash (token_hash), "
    "INDEX idx_tokens_user (user_id)"
    ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
)

_INSERT_TENANT_SQL: str = (
    "INSERT INTO tenants (id, name, plan_id, status, created_at) "
    "VALUES (?, ?, ?, 'active', ?)"
)
_SELECT_TENANT_SQL: str = "SELECT * FROM tenants WHERE id = ?"
_LIST_TENANTS_SQL: str = "SELECT * FROM tenants ORDER BY created_at, id"

_INSERT_USER_SQL: str = (
    "INSERT INTO users (id, tenant_id, email, oidc_sub, role, status, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)
_SELECT_USER_SQL: str = "SELECT * FROM users WHERE id = ?"
_SELECT_USER_BY_EMAIL_SQL: str = (
    "SELECT * FROM users WHERE tenant_id = ? AND email = ?"
)
_SELECT_USER_BY_OIDC_SUB_SQL: str = "SELECT * FROM users WHERE oidc_sub = ?"
_LIST_USERS_SQL: str = "SELECT * FROM users WHERE tenant_id = ? ORDER BY created_at, id"
_UPDATE_USER_SQL: str = (
    "UPDATE users SET role = COALESCE(?, role), status = COALESCE(?, status) "
    "WHERE id = ?"
)

_INSERT_TOKEN_SQL: str = (
    "INSERT INTO api_tokens "
    "(id, user_id, name, token_hash, secret_hash, scopes, expires_at, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)
_SELECT_TOKEN_BY_HASH_SQL: str = "SELECT * FROM api_tokens WHERE token_hash = ?"
_TOUCH_TOKEN_SQL: str = "UPDATE api_tokens SET last_used_at = ? WHERE id = ?"
_DELETE_TOKEN_SQL: str = "DELETE FROM api_tokens WHERE id = ?"
_LIST_TOKENS_SQL: str = (
    "SELECT * FROM api_tokens WHERE user_id = ? ORDER BY created_at, id"
)


def _to_mysql(sql: str) -> str:
    """Translate the shared '?' placeholder SQL to PyMySQL's '%s'."""
    return sql.replace("?", "%s")


# ── Shared helpers ────────────────────────────────────────────────────────────


def _validate_role(role: str) -> str:
    if role not in ROLE_SET:
        raise ValueError(f"unknown role {role!r}; expected one of {ROLE_VALUES}")
    return role


def _validate_user_status(status: str) -> str:
    if status not in USER_STATUS_VALUES:
        raise ValueError(f"unknown user status {status!r}")
    return status


def _validate_tenant_status(status: str) -> str:
    if status not in TENANT_STATUS_VALUES:
        raise ValueError(f"unknown tenant status {status!r}")
    return status


def _row_to_tenant(row: Any) -> Tenant:
    return Tenant(
        id=cast(str, row["id"]),
        name=cast(str, row["name"]),
        plan_id=cast(str, row["plan_id"]),
        status=cast(str, row["status"]),
        created_at=float(row["created_at"]),
    )


def _row_to_user(row: Any) -> User:
    return User(
        id=cast(str, row["id"]),
        tenant_id=cast(str, row["tenant_id"]),
        email=cast(str, row["email"]),
        oidc_sub=cast(str | None, row["oidc_sub"]),
        role=cast(str, row["role"]),
        status=cast(str, row["status"]),
        created_at=float(row["created_at"]),
    )


def _row_to_token(row: Any) -> ApiTokenRow:
    return ApiTokenRow(
        id=cast(str, row["id"]),
        user_id=cast(str, row["user_id"]),
        name=cast(str, row["name"]),
        token_hash=cast(str, row["token_hash"]),
        secret_hash=cast(str, row["secret_hash"]),
        scopes=cast(str, row["scopes"]),
        expires_at=cast(float | None, row["expires_at"]),
        last_used_at=cast(float | None, row["last_used_at"]),
        created_at=float(row["created_at"]),
    )


def _parse_mysql_url(url: str) -> dict[str, Any]:
    parsed = urlsplit(url)
    if parsed.scheme not in ("mysql", "mysql+pymysql"):
        raise ValueError(f"expected a mysql:// URL, got scheme {parsed.scheme!r}")
    if parsed.hostname is None:
        raise ValueError("MySQL URL must include a host")
    database = (parsed.path or "/").lstrip("/")
    return {
        "host": parsed.hostname,
        "port": parsed.port or 3306,
        "user": unquote(parsed.username) if parsed.username is not None else "",
        "password": unquote(parsed.password) if parsed.password is not None else "",
        "database": database or "specproof",
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "autocommit": False,
    }


# ── In-memory backend ─────────────────────────────────────────────────────────


class InMemoryIdentityStore:
    """Thread-safe in-memory backend — development and tests."""

    def __init__(self, *, now_fn: Callable[[], float] | None = None) -> None:
        self._now_fn = now_fn if now_fn is not None else time.time
        self._lock = threading.RLock()
        self._tenants: dict[str, Tenant] = {}
        self._users: dict[str, User] = {}
        self._tokens: dict[str, ApiTokenRow] = {}

    def ensure_schema(self) -> None:
        """No-op: the in-memory dicts need no schema."""

    def close(self) -> None:
        """No-op: nothing to release."""

    def create_tenant(self, name: str, plan_id: str = "free") -> Tenant:
        import uuid

        tenant = Tenant(
            id=str(uuid.uuid4()), name=name, plan_id=plan_id,
            status="active", created_at=self._now_fn(),
        )
        with self._lock:
            self._tenants[tenant.id] = tenant
        return tenant

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        with self._lock:
            return self._tenants.get(tenant_id)

    def list_tenants(self) -> list[Tenant]:
        with self._lock:
            return sorted(self._tenants.values(), key=lambda t: (t.created_at, t.id))

    def create_user(
        self,
        tenant_id: str,
        email: str,
        role: str = "viewer",
        status: str = "active",
        oidc_sub: str | None = None,
    ) -> User:
        import uuid

        role = _validate_role(role)
        status = _validate_user_status(status)
        user = User(
            id=str(uuid.uuid4()), tenant_id=tenant_id, email=email,
            oidc_sub=oidc_sub, role=role, status=status, created_at=self._now_fn(),
        )
        with self._lock:
            for existing in self._users.values():
                if existing.tenant_id == tenant_id and existing.email == email:
                    raise DuplicateUserError(
                        f"user with email {email!r} already exists in tenant {tenant_id}"
                    )
                if oidc_sub is not None and existing.oidc_sub == oidc_sub:
                    raise DuplicateUserError(f"user with oidc_sub {oidc_sub!r} exists")
            self._users[user.id] = user
        return user

    def get_user(self, user_id: str) -> User | None:
        with self._lock:
            return self._users.get(user_id)

    def get_user_by_email(self, tenant_id: str, email: str) -> User | None:
        with self._lock:
            for user in self._users.values():
                if user.tenant_id == tenant_id and user.email == email:
                    return user
        return None

    def get_user_by_oidc_sub(self, oidc_sub: str) -> User | None:
        with self._lock:
            for user in self._users.values():
                if user.oidc_sub == oidc_sub:
                    return user
        return None

    def list_users(self, tenant_id: str) -> list[User]:
        with self._lock:
            return sorted(
                (u for u in self._users.values() if u.tenant_id == tenant_id),
                key=lambda u: (u.created_at, u.id),
            )

    def update_user(
        self, user_id: str, *, role: str | None = None, status: str | None = None
    ) -> User:
        with self._lock:
            user = self._users.get(user_id)
            if user is None:
                raise UserNotFoundError(f"user {user_id!r} not found")
            updated = User(
                id=user.id,
                tenant_id=user.tenant_id,
                email=user.email,
                oidc_sub=user.oidc_sub,
                role=_validate_role(role) if role is not None else user.role,
                status=_validate_user_status(status) if status is not None else user.status,
                created_at=user.created_at,
            )
            self._users[user_id] = updated
            return updated

    def create_api_token(
        self,
        user_id: str,
        name: str,
        token_hash: str,
        secret_hash: str,
        scopes: str = "",
        expires_at: float | None = None,
        token_id: str | None = None,
    ) -> ApiTokenRow:
        import uuid

        if self.get_user(user_id) is None:
            raise UserNotFoundError(f"user {user_id!r} not found")
        row = ApiTokenRow(
            id=token_id or str(uuid.uuid4()), user_id=user_id, name=name,
            token_hash=token_hash, secret_hash=secret_hash, scopes=scopes,
            expires_at=expires_at, last_used_at=None, created_at=self._now_fn(),
        )
        with self._lock:
            self._tokens[row.id] = row
        return row

    def get_token_by_hash(self, token_hash: str) -> ApiTokenRow | None:
        with self._lock:
            for row in self._tokens.values():
                if row.token_hash == token_hash:
                    return row
        return None

    def touch_token_last_used(self, token_id: str, now: float) -> None:
        with self._lock:
            row = self._tokens.get(token_id)
            if row is None:
                return
            self._tokens[token_id] = ApiTokenRow(
                id=row.id, user_id=row.user_id, name=row.name,
                token_hash=row.token_hash, secret_hash=row.secret_hash,
                scopes=row.scopes, expires_at=row.expires_at,
                last_used_at=now, created_at=row.created_at,
            )

    def revoke_token(self, token_id: str) -> bool:
        with self._lock:
            return self._tokens.pop(token_id, None) is not None

    def list_tokens(self, user_id: str) -> list[ApiTokenRow]:
        with self._lock:
            return sorted(
                (t for t in self._tokens.values() if t.user_id == user_id),
                key=lambda t: (t.created_at, t.id),
            )


# ── SQLite backend ────────────────────────────────────────────────────────────


class SqliteIdentityStore:
    """File-based SQLite backend (tests and dev; no Docker required).

    One connection per store instance, serialized by a lock;
    check_same_thread=False plus the lock keeps concurrent threads safe.
    The schema is created in __init__.
    """

    def __init__(
        self, path: str | Path, *, now_fn: Callable[[], float] | None = None
    ) -> None:
        self._now_fn = now_fn if now_fn is not None else time.time
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA_SQLITE)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def create_tenant(self, name: str, plan_id: str = "free") -> Tenant:
        import uuid

        tenant_id = str(uuid.uuid4())
        with self._lock, self._conn:
            self._conn.execute(
                _INSERT_TENANT_SQL, (tenant_id, name, plan_id, self._now_fn())
            )
        tenant = self.get_tenant(tenant_id)
        if tenant is None:
            raise IdentityStoreError("tenant insert did not persist")
        return tenant

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        with self._lock:
            row = self._conn.execute(_SELECT_TENANT_SQL, (tenant_id,)).fetchone()
        return None if row is None else _row_to_tenant(row)

    def list_tenants(self) -> list[Tenant]:
        with self._lock:
            rows = self._conn.execute(_LIST_TENANTS_SQL).fetchall()
        return [_row_to_tenant(row) for row in rows]

    def create_user(
        self,
        tenant_id: str,
        email: str,
        role: str = "viewer",
        status: str = "active",
        oidc_sub: str | None = None,
    ) -> User:
        import uuid

        role = _validate_role(role)
        status = _validate_user_status(status)
        user_id = str(uuid.uuid4())
        with self._lock, self._conn:
            try:
                self._conn.execute(
                    _INSERT_USER_SQL,
                    (user_id, tenant_id, email, oidc_sub, role, status, self._now_fn()),
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateUserError(
                    f"user (tenant {tenant_id}, email {email!r}, oidc_sub "
                    f"{oidc_sub!r}) already exists"
                ) from exc
        user = self.get_user(user_id)
        if user is None:
            raise IdentityStoreError("user insert did not persist")
        return user

    def get_user(self, user_id: str) -> User | None:
        with self._lock:
            row = self._conn.execute(_SELECT_USER_SQL, (user_id,)).fetchone()
        return None if row is None else _row_to_user(row)

    def get_user_by_email(self, tenant_id: str, email: str) -> User | None:
        with self._lock:
            row = self._conn.execute(
                _SELECT_USER_BY_EMAIL_SQL, (tenant_id, email)
            ).fetchone()
        return None if row is None else _row_to_user(row)

    def get_user_by_oidc_sub(self, oidc_sub: str) -> User | None:
        with self._lock:
            row = self._conn.execute(
                _SELECT_USER_BY_OIDC_SUB_SQL, (oidc_sub,)
            ).fetchone()
        return None if row is None else _row_to_user(row)

    def list_users(self, tenant_id: str) -> list[User]:
        with self._lock:
            rows = self._conn.execute(_LIST_USERS_SQL, (tenant_id,)).fetchall()
        return [_row_to_user(row) for row in rows]

    def update_user(
        self, user_id: str, *, role: str | None = None, status: str | None = None
    ) -> User:
        if role is not None:
            role = _validate_role(role)
        if status is not None:
            status = _validate_user_status(status)
        with self._lock, self._conn:
            self._conn.execute(_UPDATE_USER_SQL, (role, status, user_id))
        user = self.get_user(user_id)
        if user is None:
            raise UserNotFoundError(f"user {user_id!r} not found")
        return user

    def create_api_token(
        self,
        user_id: str,
        name: str,
        token_hash: str,
        secret_hash: str,
        scopes: str = "",
        expires_at: float | None = None,
        token_id: str | None = None,
    ) -> ApiTokenRow:
        import uuid

        if self.get_user(user_id) is None:
            raise UserNotFoundError(f"user {user_id!r} not found")
        token_id = token_id or str(uuid.uuid4())
        with self._lock, self._conn:
            self._conn.execute(
                _INSERT_TOKEN_SQL,
                (token_id, user_id, name, token_hash, secret_hash, scopes,
                 expires_at, self._now_fn()),
            )
        row = self.get_token_by_hash(token_hash)
        if row is None:
            raise IdentityStoreError("token insert did not persist")
        return row

    def get_token_by_hash(self, token_hash: str) -> ApiTokenRow | None:
        with self._lock:
            row = self._conn.execute(
                _SELECT_TOKEN_BY_HASH_SQL, (token_hash,)
            ).fetchone()
        return None if row is None else _row_to_token(row)

    def touch_token_last_used(self, token_id: str, now: float) -> None:
        with self._lock, self._conn:
            self._conn.execute(_TOUCH_TOKEN_SQL, (now, token_id))

    def revoke_token(self, token_id: str) -> bool:
        with self._lock, self._conn:
            affected = self._conn.execute(_DELETE_TOKEN_SQL, (token_id,)).rowcount
        return bool(affected)

    def list_tokens(self, user_id: str) -> list[ApiTokenRow]:
        with self._lock:
            rows = self._conn.execute(_LIST_TOKENS_SQL, (user_id,)).fetchall()
        return [_row_to_token(row) for row in rows]


# ── MySQL backend ─────────────────────────────────────────────────────────────


class MySqlIdentityStore:
    """Production MySQL backend (PyMySQL + DictCursor).

    One connection per operation via the connection() context manager, which
    commits on success and rolls back on error; every statement uses a
    single cursor execute-then-fetch (CLAUDE.md MySQL discipline).
    """

    def __init__(
        self, url: str | None = None, *, now_fn: Callable[[], float] | None = None
    ) -> None:
        import os

        resolved = url or os.getenv("MYSQL_URL")
        if not resolved:
            raise ValueError("MySqlIdentityStore needs a mysql:// URL (argument or MYSQL_URL)")
        self._connect_kwargs = _parse_mysql_url(resolved)
        self._now_fn = now_fn if now_fn is not None else time.time

    def _connect(self) -> pymysql.Connection:
        return pymysql.connect(**self._connect_kwargs)

    @contextmanager
    def connection(self) -> Iterator[pymysql.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def close(self) -> None:
        """No-op: each operation opens and closes its own connection."""

    def ensure_schema(self) -> None:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_SCHEMA_MYSQL)

    def create_tenant(self, name: str, plan_id: str = "free") -> Tenant:
        import uuid

        tenant_id = str(uuid.uuid4())
        with self.connection() as conn:
            conn.cursor().execute(
                _to_mysql(_INSERT_TENANT_SQL),
                (tenant_id, name, plan_id, self._now_fn()),
            )
        tenant = self.get_tenant(tenant_id)
        if tenant is None:
            raise IdentityStoreError("tenant insert did not persist")
        return tenant

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_SELECT_TENANT_SQL), (tenant_id,))
            row = cur.fetchone()
        return None if row is None else _row_to_tenant(cast(dict[str, Any], row))

    def list_tenants(self) -> list[Tenant]:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_LIST_TENANTS_SQL))
            rows = cur.fetchall()
        return [_row_to_tenant(cast(dict[str, Any], row)) for row in rows]

    def create_user(
        self,
        tenant_id: str,
        email: str,
        role: str = "viewer",
        status: str = "active",
        oidc_sub: str | None = None,
    ) -> User:
        import uuid

        role = _validate_role(role)
        status = _validate_user_status(status)
        user_id = str(uuid.uuid4())
        with self.connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    _to_mysql(_INSERT_USER_SQL),
                    (user_id, tenant_id, email, oidc_sub, role, status, self._now_fn()),
                )
            except pymysql.err.IntegrityError as exc:
                raise DuplicateUserError(
                    f"user (tenant {tenant_id}, email {email!r}, oidc_sub "
                    f"{oidc_sub!r}) already exists"
                ) from exc
        user = self.get_user(user_id)
        if user is None:
            raise IdentityStoreError("user insert did not persist")
        return user

    def get_user(self, user_id: str) -> User | None:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_SELECT_USER_SQL), (user_id,))
            row = cur.fetchone()
        return None if row is None else _row_to_user(cast(dict[str, Any], row))

    def get_user_by_email(self, tenant_id: str, email: str) -> User | None:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_SELECT_USER_BY_EMAIL_SQL), (tenant_id, email))
            row = cur.fetchone()
        return None if row is None else _row_to_user(cast(dict[str, Any], row))

    def get_user_by_oidc_sub(self, oidc_sub: str) -> User | None:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_SELECT_USER_BY_OIDC_SUB_SQL), (oidc_sub,))
            row = cur.fetchone()
        return None if row is None else _row_to_user(cast(dict[str, Any], row))

    def list_users(self, tenant_id: str) -> list[User]:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_LIST_USERS_SQL), (tenant_id,))
            rows = cur.fetchall()
        return [_row_to_user(cast(dict[str, Any], row)) for row in rows]

    def update_user(
        self, user_id: str, *, role: str | None = None, status: str | None = None
    ) -> User:
        if role is not None:
            role = _validate_role(role)
        if status is not None:
            status = _validate_user_status(status)
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_UPDATE_USER_SQL), (role, status, user_id))
        user = self.get_user(user_id)
        if user is None:
            raise UserNotFoundError(f"user {user_id!r} not found")
        return user

    def create_api_token(
        self,
        user_id: str,
        name: str,
        token_hash: str,
        secret_hash: str,
        scopes: str = "",
        expires_at: float | None = None,
        token_id: str | None = None,
    ) -> ApiTokenRow:
        import uuid

        if self.get_user(user_id) is None:
            raise UserNotFoundError(f"user {user_id!r} not found")
        token_id = token_id or str(uuid.uuid4())
        with self.connection() as conn:
            conn.cursor().execute(
                _to_mysql(_INSERT_TOKEN_SQL),
                (token_id, user_id, name, token_hash, secret_hash, scopes,
                 expires_at, self._now_fn()),
            )
        row = self.get_token_by_hash(token_hash)
        if row is None:
            raise IdentityStoreError("token insert did not persist")
        return row

    def get_token_by_hash(self, token_hash: str) -> ApiTokenRow | None:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_SELECT_TOKEN_BY_HASH_SQL), (token_hash,))
            row = cur.fetchone()
        return None if row is None else _row_to_token(cast(dict[str, Any], row))

    def touch_token_last_used(self, token_id: str, now: float) -> None:
        with self.connection() as conn:
            conn.cursor().execute(_to_mysql(_TOUCH_TOKEN_SQL), (now, token_id))

    def revoke_token(self, token_id: str) -> bool:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_DELETE_TOKEN_SQL), (token_id,))
            return bool(cur.rowcount)

    def list_tokens(self, user_id: str) -> list[ApiTokenRow]:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_LIST_TOKENS_SQL), (user_id,))
            rows = cur.fetchall()
        return [_row_to_token(cast(dict[str, Any], row)) for row in rows]


# ── Store factory (SPECPROOF_IDENTITY_URL, agent_jobs convention) ─────────────


def build_identity_store(url_spec: str) -> IdentityStore:
    """Build a backend from a URL spec; fails closed on an unknown scheme.

    * ''            -> InMemoryIdentityStore (dev/tests);
    * 'sqlite:<p>'  -> SqliteIdentityStore (file path, or ':memory:');
    * 'mysql://...' -> MySqlIdentityStore (production).
    """
    if url_spec == "":
        return InMemoryIdentityStore()
    if url_spec.startswith("sqlite:"):
        path = url_spec[len("sqlite:"):]
        return SqliteIdentityStore(path)
    if url_spec.startswith("mysql://") or url_spec.startswith("mysql+pymysql://"):
        return MySqlIdentityStore(url_spec)
    raise ValueError(
        "SPECPROOF_IDENTITY_URL must be '' (in-memory), 'sqlite:<path>' or "
        f"'mysql://...'; got {url_spec!r}"
    )
