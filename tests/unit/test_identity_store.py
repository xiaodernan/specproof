"""Identity store tests (industrialization phase 1, no Docker).

Covers the InMemory + SQLite backends (full CRUD parity via one shared
scenario), the store factory URL contract, the MySQL SQL translation
(single-cursor discipline is enforced by construction — one execute per
statement, values only through placeholders) and the schema/status
consistency invariant mirroring TestSharedSqlConsistency in agent_jobs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from storage.identity import (
    _SCHEMA_MYSQL,
    _SCHEMA_SQLITE,
    ROLE_SET,
    ROLE_VALUES,
    USER_STATUS_VALUES,
    DuplicateUserError,
    IdentityStore,
    InMemoryIdentityStore,
    MySqlIdentityStore,
    SqliteIdentityStore,
    UserNotFoundError,
    _to_mysql,
    build_identity_store,
)

EMAIL_A = "alice@example.com"
EMAIL_B = "bob@example.com"


def _scenario(store: IdentityStore) -> dict[str, str]:
    """Exercise every store operation once; returns key ids."""
    tenant = store.create_tenant(name="acme", plan_id="pro")
    assert store.get_tenant(tenant.id) is not None
    assert store.list_tenants()[0].name == "acme"

    alice = store.create_user(tenant.id, EMAIL_A, role="admin")
    bob = store.create_user(tenant.id, EMAIL_B, role="viewer")
    assert store.get_user(alice.id) is not None
    assert store.get_user_by_email(tenant.id, EMAIL_A) is not None
    assert store.get_user_by_oidc_sub("sub-xyz") is None

    oidc_user = store.create_user(tenant.id, "carol@example.com", oidc_sub="sub-xyz")
    assert store.get_user_by_oidc_sub("sub-xyz") == oidc_user

    assert {u.email for u in store.list_users(tenant.id)} == {
        EMAIL_A, EMAIL_B, "carol@example.com",
    }

    updated = store.update_user(bob.id, role="operator")
    assert updated.role == "operator"
    disabled = store.update_user(bob.id, status="disabled")
    assert disabled.status == "disabled"

    row = store.create_api_token(
        alice.id, "ci", "h" * 64, "s" * 60, scopes="jobs:read",
    )
    assert store.get_token_by_hash("h" * 64) == row
    store.touch_token_last_used(row.id, 1234.0)
    touched = store.get_token_by_hash("h" * 64)
    assert touched is not None and touched.last_used_at == 1234.0
    assert [t.name for t in store.list_tokens(alice.id)] == ["ci"]
    assert store.revoke_token(row.id) is True
    assert store.get_token_by_hash("h" * 64) is None
    assert store.revoke_token(row.id) is False

    return {"tenant": tenant.id, "alice": alice.id, "bob": bob.id}


def test_in_memory_backend_scenario() -> None:
    store = InMemoryIdentityStore()
    _scenario(store)


def test_sqlite_backend_scenario(tmp_path: Path) -> None:
    db = tmp_path / "identity.db"
    store = SqliteIdentityStore(db)
    ids = _scenario(store)
    store.close()
    # Reopen: everything persisted.
    reopened = SqliteIdentityStore(db)
    assert reopened.get_user(ids["alice"]) is not None
    assert reopened.get_user(ids["bob"]) is not None
    reopened.close()


def test_sqlite_duplicate_email_rejected(tmp_path: Path) -> None:
    store = SqliteIdentityStore(tmp_path / "identity.db")
    tenant = store.create_tenant("acme")
    store.create_user(tenant.id, EMAIL_A)
    with pytest.raises(DuplicateUserError):
        store.create_user(tenant.id, EMAIL_A)


def test_sqlite_duplicate_oidc_sub_rejected(tmp_path: Path) -> None:
    store = SqliteIdentityStore(tmp_path / "identity.db")
    tenant = store.create_tenant("acme")
    store.create_user(tenant.id, EMAIL_A, oidc_sub="sub-1")
    with pytest.raises(DuplicateUserError):
        store.create_user(tenant.id, EMAIL_B, oidc_sub="sub-1")


def test_sqlite_missing_user_update_raises(tmp_path: Path) -> None:
    store = SqliteIdentityStore(tmp_path / "identity.db")
    with pytest.raises(UserNotFoundError):
        store.update_user("missing", role="admin")


def test_sqlite_token_requires_existing_user(tmp_path: Path) -> None:
    store = SqliteIdentityStore(tmp_path / "identity.db")
    with pytest.raises(UserNotFoundError):
        store.create_api_token("missing", "ci", "h" * 64, "s" * 60)


def test_sqlite_role_validation() -> None:
    store = InMemoryIdentityStore()
    tenant = store.create_tenant("acme")
    with pytest.raises(ValueError):
        store.create_user(tenant.id, EMAIL_A, role="superuser")


def test_factory_url_contract() -> None:
    assert isinstance(build_identity_store(""), InMemoryIdentityStore)
    assert isinstance(build_identity_store("sqlite::memory:"), SqliteIdentityStore)
    mysql = build_identity_store("mysql://user:pass@db.example.com:3306/specproof")
    assert isinstance(mysql, MySqlIdentityStore)
    with pytest.raises(ValueError):
        build_identity_store("postgres://nope")


def test_mysql_sql_uses_pymysql_placeholders() -> None:
    assert "%s" in _to_mysql("INSERT INTO t (a) VALUES (?)")
    from storage.identity import _INSERT_USER_SQL

    assert "%s" in _to_mysql(_INSERT_USER_SQL)
    assert "?" not in _to_mysql(_INSERT_USER_SQL)


def test_sqlite_schema_applies_idempotently(tmp_path: Path) -> None:
    db = tmp_path / "identity.db"
    store = SqliteIdentityStore(db)
    store.ensure_schema()  # second pass must not raise
    store.close()


def test_role_and_status_invariants() -> None:
    """The canonical role/status tuples must match the constants."""
    assert frozenset(ROLE_VALUES) == ROLE_SET
    assert "active" in USER_STATUS_VALUES and "disabled" in USER_STATUS_VALUES
    for schema in (_SCHEMA_SQLITE, _SCHEMA_MYSQL):
        assert "api_tokens" in schema and "users" in schema and "tenants" in schema
        assert "token_hash" in schema and "secret_hash" in schema


def test_sqlite_backend_serializes_concurrent_writes(
    tmp_path: Path,
) -> None:
    """The lock + single connection keep threaded writes safe."""
    import threading

    store = SqliteIdentityStore(tmp_path / "identity.db")
    tenant = store.create_tenant("acme")
    errors: list[BaseException] = []

    def work(index: int) -> None:
        try:
            store.create_user(tenant.id, f"user{index}@example.com")
        except BaseException as exc:  # noqa: BLE001 — collected and asserted
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(store.list_users(tenant.id)) == 8
    store.close()
