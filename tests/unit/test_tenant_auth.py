"""Multi-tenant identity security tests — the phase-1 exit criteria.

docs/architecture/MULTI_TENANT_DESIGN.md §6, all of it:
  * cross-tenant job read -> 404 (never 403) + audit(attempted_tenant);
  * RBAC matrix assertions per role × resource (viewer write -> FORBIDDEN);
  * OIDC mock JWKS: RS256 signed / expired / wrong-issuer;
  * tenant_id comes from the principal only (request param override is
    ineffective);
  * existing security gates stay green (no-key-leak runs separately);
  * single-tenant compat: with auth NOT configured the API is unchanged.

No Docker: the identity store runs on SQLite (SPECPROOF_IDENTITY_URL),
the jobs store is faked at the route level, and the OIDC IdP is an
httpx.MockTransport. All fake keys are built by string concatenation so
the no-key-leak scanner can never match them.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from api.identity.oidc import OidcValidator
from api.identity.principal import (
    ALL_ACTIONS,
    ROLE_MATRIX,
    Principal,
    principal_allowed,
    roles_allowed,
)
from api.identity.tokens import mint_token, verify_local_token
from api.server import app
from storage.mysql import MySQLStore
from storage.tenant_scope import TENANT_SCOPE_VAR, TenantScope

HMAC_KEY = "test" + "-hmac-" + "key-w37"
ISSUER = "https://idp.test"
CLIENT_ID = "specproof-web"


def _payload() -> dict[str, str]:
    return {
        "repo_path": "D:/repo",
        "base_ref": "base",
        "head_ref": "head",
        "spec_path": "demo/requirement.txt",
        "depth": "FAST",
    }


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── Matrix (§2) ───────────────────────────────────────────────────────────────


EXPECTED_MATRIX: dict[str, dict[str, frozenset[str]]] = {
    "admin": {
        "jobs": ALL_ACTIONS["jobs"],
        "cases": ALL_ACTIONS["cases"],
        "billing": ALL_ACTIONS["billing"],
        "admin": ALL_ACTIONS["admin"],
    },
    "operator": {
        "jobs": ALL_ACTIONS["jobs"],
        "cases": frozenset({"read", "trigger"}),
        "billing": frozenset({"read"}),
        "admin": frozenset({"users", "tokens"}),
    },
    "viewer": {
        "jobs": frozenset({"read"}),
        "cases": frozenset({"read"}),
        "billing": frozenset(),
        "admin": frozenset(),
    },
    "auditor": {
        "jobs": frozenset({"read"}),
        "cases": frozenset({"read", "verify"}),
        "billing": frozenset({"read"}),
        "admin": frozenset({"audit"}),
    },
}


def test_rbac_matrix_encodes_design_table_exactly() -> None:
    """Every role × resource cell matches the §2 table (16 cells)."""
    assert set(ROLE_MATRIX) == set(EXPECTED_MATRIX)
    for role, resources in EXPECTED_MATRIX.items():
        assert set(ROLE_MATRIX[role]) == set(resources)
        for resource, actions in resources.items():
            assert ROLE_MATRIX[role][resource] == actions, (role, resource)


def test_roles_allowed_union_of_roles() -> None:
    assert roles_allowed({"viewer"}, "jobs", "read")
    assert not roles_allowed({"viewer"}, "jobs", "write")
    assert roles_allowed({"viewer", "auditor"}, "cases", "verify")
    assert not roles_allowed({"operator"}, "admin", "manage")
    assert roles_allowed({"operator"}, "admin", "users")


def test_principal_scope_intersection() -> None:
    principal = Principal(
        user_id="u1", tenant_id="t1",
        roles=frozenset({"operator"}), scopes=frozenset({"jobs:read"}),
    )
    assert principal_allowed(principal, "jobs", "read")
    assert not principal_allowed(principal, "jobs", "write")  # scope narrows role
    wildcard = Principal(
        user_id="u2", tenant_id="t1",
        roles=frozenset({"operator"}), scopes=frozenset({"jobs:*"}),
    )
    assert principal_allowed(wildcard, "jobs", "write")
    unscoped = Principal(
        user_id="u3", tenant_id="t1",
        roles=frozenset({"viewer"}), scopes=frozenset(),
    )
    assert principal_allowed(unscoped, "jobs", "read")
    assert not principal_allowed(unscoped, "jobs", "write")


# ── Local token crypto (§1) ───────────────────────────────────────────────────


@pytest.fixture()
def tenant_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Enable tenant mode against a per-test SQLite identity store."""
    monkeypatch.setenv("SPECPROOF_AUTH_ENABLED", "true")
    monkeypatch.setenv("SPECPROOF_IDENTITY_URL", f"sqlite:{tmp_path / 'identity.db'}")
    monkeypatch.setenv("SPECPROOF_TOKEN_HMAC_KEY", HMAC_KEY)
    monkeypatch.setenv("SPECPROOF_BCRYPT_ROUNDS", "4")
    monkeypatch.delenv("SPECPROOF_API_KEY", raising=False)
    monkeypatch.delenv("OIDC_ISSUER", raising=False)
    monkeypatch.delenv("OIDC_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPECPROOF_DEFAULT_TENANT_ID", raising=False)
    from api.identity.oidc import reset_oidc_validator
    from api.identity.store import reset_identity_store

    reset_identity_store()
    reset_oidc_validator()


@pytest.fixture()
def seeded(tenant_env: None) -> dict[str, Any]:
    """Tenant A with one user per role, tenant B with a viewer; tokens for all."""
    from api.identity.store import get_identity_store

    store = get_identity_store()
    tenant_a = store.create_tenant("tenant-a")
    tenant_b = store.create_tenant("tenant-b")
    users: dict[str, str] = {}
    for role in ("admin", "operator", "viewer", "auditor"):
        user = store.create_user(tenant_a.id, f"{role}@a.example.com", role=role)
        users[role] = user.id
    viewer_b = store.create_user(tenant_b.id, "viewer@b.example.com", role="viewer")
    tokens: dict[str, str] = {}
    for role, user_id in users.items():
        _row, token = mint_token(store, user_id, name=role)
        tokens[role] = token
    _row, token_b = mint_token(store, viewer_b.id, name="viewer-b")
    tokens["viewer_b"] = token_b
    return {"tenant_a": tenant_a.id, "tenant_b": tenant_b.id,
            "users": users, "tokens": tokens}


def test_minted_token_shape_and_hash_discipline(tenant_env: None, seeded: dict[str, Any]) -> None:
    from api.identity.store import get_identity_store
    from api.identity.tokens import check_secret, token_hash_for

    store = get_identity_store()
    _row, token = mint_token(store, seeded["users"]["viewer"], "ci", scopes="jobs:read")
    parts = token.split("_")
    assert parts[0] == "sp" and len(parts) == 3
    row = store.get_token_by_hash(token_hash_for(token))
    assert row is not None
    assert row.token_hash != token  # HMAC hash, not the token
    assert row.secret_hash != token  # bcrypt hash, not the token
    assert row.token_hash != token_hash_for(parts[2])  # HMAC covers the whole token
    assert check_secret(parts[2], row.secret_hash)
    assert not check_secret("wrong-secret", row.secret_hash)


def test_verify_local_token_roundtrip_and_rejections(
    tenant_env: None, seeded: dict[str, Any],
) -> None:
    from api.identity.store import get_identity_store

    store = get_identity_store()
    token = seeded["tokens"]["viewer"]
    principal = verify_local_token(store, token)
    assert principal is not None
    assert principal.tenant_id == seeded["tenant_a"]
    assert principal.roles == frozenset({"viewer"})
    # Tampering / wrong tokens all reject with None (no oracle).
    assert verify_local_token(store, token[:-1] + ("a" if token[-1] != "a" else "b")) is None
    assert verify_local_token(store, "sp_unknown_" + "secret") is None
    assert verify_local_token(store, "not-a-token") is None
    assert verify_local_token(store, "") is None


def test_expired_token_rejected(tenant_env: None, seeded: dict[str, Any]) -> None:
    from api.identity.store import get_identity_store

    store = get_identity_store()
    _row, token = mint_token(store, seeded["users"]["viewer"], "short", ttl_days=1)
    assert verify_local_token(store, token, now=time.time()) is not None
    assert verify_local_token(store, token, now=time.time() + 2 * 86400.0) is None


def test_disabled_user_token_rejected(tenant_env: None, seeded: dict[str, Any]) -> None:
    from api.identity.store import get_identity_store

    store = get_identity_store()
    store.update_user(seeded["users"]["viewer"], status="disabled")
    assert verify_local_token(store, seeded["tokens"]["viewer"]) is None


def test_revoked_token_rejected(tenant_env: None, seeded: dict[str, Any]) -> None:
    from api.identity.store import get_identity_store
    from api.identity.tokens import token_hash_for

    store = get_identity_store()
    row = store.get_token_by_hash(token_hash_for(seeded["tokens"]["viewer"]))
    assert row is not None
    store.revoke_token(row.id)
    assert verify_local_token(store, seeded["tokens"]["viewer"]) is None


def test_mint_requires_hmac_key(
    tenant_env: None, seeded: dict[str, Any], monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.identity.store import get_identity_store
    from api.identity.tokens import TokenConfigError, token_hash_for

    monkeypatch.delenv("SPECPROOF_TOKEN_HMAC_KEY", raising=False)
    with pytest.raises(TokenConfigError):
        token_hash_for("sp_x_y")
    store = get_identity_store()
    # Verification fails closed instead of raising.
    assert verify_local_token(store, seeded["tokens"]["viewer"]) is None


# ── HTTP: middleware / RBAC / cross-tenant (exit criteria) ───────────────────


class FakeJobStore:
    """Route-level jobs store; tenant comes from the request scope."""

    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self.audit: list[dict[str, Any]] = []

    def create_job_with_outbox(self, job: dict[str, Any]) -> str:
        from storage.tenant_scope import current_scope

        scope = current_scope()
        job["tenant_id"] = scope.tenant_id if scope is not None else None
        self.jobs[job["id"]] = dict(job)
        return str(job["id"])

    def insert_job(self, job: dict[str, Any]) -> None:
        from storage.tenant_scope import current_scope

        scope = current_scope()
        job["tenant_id"] = scope.tenant_id if scope is not None else None
        self.jobs[job["id"]] = dict(job)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self.jobs.get(job_id)

    def get_job_summary(self, job_id: str) -> dict[str, Any] | None:
        row = self.jobs.get(job_id)
        return row.get("summary") if row else None

    def list_recent_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        del limit
        return list(self.jobs.values())

    def transition_job_status(self, job_id: str, to_status: str, **kwargs: Any) -> bool:
        del job_id, to_status, kwargs
        return True

    def record_audit(self, **kwargs: Any) -> None:
        self.audit.append(kwargs)

    def get_job_tenant(self, job_id: str) -> str | None:
        row = self.jobs.get(job_id)
        if row is None:
            return None
        tenant = row.get("tenant_id")
        return str(tenant) if tenant else None

    def list_audit_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        del limit
        return list(self.audit)

    def is_ready(self) -> bool:
        return True


class FakeRedisStore:
    class _Client:
        def incr(self, key: str) -> int:
            del key
            return 1

        def expire(self, key: str, ttl: int) -> None:
            del key, ttl

    @property
    def client(self) -> FakeRedisStore._Client:
        return self._Client()

    def is_ready(self) -> bool:
        return True

    def xread_progress(
        self, job_id: str, from_id: str = "0", count: int = 50,
    ) -> list[dict[str, Any]]:
        del job_id, from_id, count
        return []


@pytest.fixture()
def fakes(monkeypatch: pytest.MonkeyPatch) -> FakeJobStore:
    fake = FakeJobStore()
    import api.routes.jobs as jobs_module
    import api.routes.web as web_module

    monkeypatch.setattr("storage.mysql.MySQLStore", lambda: fake)
    monkeypatch.setattr(jobs_module, "MySQLStore", lambda: fake)
    monkeypatch.setattr(web_module, "MySQLStore", lambda: fake)
    monkeypatch.setattr("storage.redis.RedisStore", FakeRedisStore)
    return fake


def test_missing_credentials_401_auth_required_envelope(
    tenant_env: None, fakes: FakeJobStore,
) -> None:
    client = TestClient(app)
    resp = client.get("/jobs")
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"]["code"] == "AUTH_REQUIRED"
    assert body["schema_version"] == 1
    assert body["detail"] == "Missing or invalid bearer credentials"


def test_invalid_bearer_401(tenant_env: None, fakes: FakeJobStore) -> None:
    client = TestClient(app)
    resp = client.get("/jobs", headers=bearer("sp_forged_forged"))
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTH_REQUIRED"


def test_auth_me_returns_principal(
    tenant_env: None, fakes: FakeJobStore, seeded: dict[str, Any],
) -> None:
    client = TestClient(app)
    resp = client.get("/auth/me", headers=bearer(seeded["tokens"]["viewer"]))
    assert resp.status_code == 200
    principal = resp.json()["principal"]
    assert principal["tenant_id"] == seeded["tenant_a"]
    assert principal["roles"] == ["viewer"]
    assert principal["scopes"] == []


def test_rbac_matrix_http_assertions(
    tenant_env: None, fakes: FakeJobStore, seeded: dict[str, Any],
) -> None:
    """Per-role × per-resource HTTP assertions over the live middleware."""
    client = TestClient(app)
    t = seeded["tokens"]
    # admin: jobs write + admin manage + audit
    assert client.post("/jobs", json=_payload(), headers=bearer(t["admin"])).status_code == 202
    assert client.get("/api/v1/admin/tenants", headers=bearer(t["admin"])).status_code == 200
    assert client.get("/api/v1/admin/audit", headers=bearer(t["admin"])).status_code == 200
    # operator: jobs write + user/token management; tenants/audit forbidden
    assert client.post("/jobs", json=_payload(), headers=bearer(t["operator"])).status_code == 202
    assert client.get("/api/v1/admin/users", headers=bearer(t["operator"])).status_code == 200
    assert client.get("/api/v1/admin/tokens", headers=bearer(t["operator"])).status_code == 200
    assert client.get("/api/v1/admin/tenants", headers=bearer(t["operator"])).status_code == 403
    assert client.get("/api/v1/admin/audit", headers=bearer(t["operator"])).status_code == 403
    # viewer: reads only; the exit-criterion cell: write -> TENANT_FORBIDDEN
    assert client.get("/jobs", headers=bearer(t["viewer"])).status_code == 200
    forbidden = client.post("/jobs", json=_payload(), headers=bearer(t["viewer"]))
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "TENANT_FORBIDDEN"
    assert client.get("/api/v1/admin/users", headers=bearer(t["viewer"])).status_code == 403
    assert client.post(
        "/api/v1/admin/tokens", json={"name": "n"}, headers=bearer(t["viewer"]),
    ).status_code == 403
    # auditor: jobs read + audit view; writes/admin forbidden
    assert client.get("/jobs", headers=bearer(t["auditor"])).status_code == 200
    assert client.post("/jobs", json=_payload(), headers=bearer(t["auditor"])).status_code == 403
    assert client.get("/api/v1/admin/audit", headers=bearer(t["auditor"])).status_code == 200
    assert client.get("/api/v1/admin/users", headers=bearer(t["auditor"])).status_code == 403


def test_cross_tenant_job_read_404_with_audit(
    tenant_env: None, fakes: FakeJobStore, seeded: dict[str, Any],
) -> None:
    """Exit criterion: A-tenant token reads B-tenant job -> 404 + audit."""
    fakes.jobs["job-b"] = {
        "id": "job-b", "status": "QUEUED", "tenant_id": seeded["tenant_b"],
    }
    client = TestClient(app)
    resp = client.get("/jobs/job-b", headers=bearer(seeded["tokens"]["viewer"]))
    assert resp.status_code == 404  # never 403 — no existence leak
    assert resp.json()["error"]["code"] == "JOB_NOT_FOUND"
    denied = [a for a in fakes.audit if a.get("action") == "tenant_isolation_blocked"]
    assert denied, "the refused attempt must be audited"
    assert denied[0]["attempted_tenant"] == seeded["tenant_b"]


def test_same_tenant_job_read_ok(
    tenant_env: None, fakes: FakeJobStore, seeded: dict[str, Any],
) -> None:
    fakes.jobs["job-a"] = {
        "id": "job-a", "status": "QUEUED", "tenant_id": seeded["tenant_a"],
    }
    client = TestClient(app)
    resp = client.get("/jobs/job-a", headers=bearer(seeded["tokens"]["viewer"]))
    assert resp.status_code == 200
    assert resp.json()["job"]["id"] == "job-a"


def test_auditor_cross_tenant_view_allowed(
    tenant_env: None, fakes: FakeJobStore, seeded: dict[str, Any],
) -> None:
    fakes.jobs["job-b"] = {
        "id": "job-b", "status": "QUEUED", "tenant_id": seeded["tenant_b"],
    }
    client = TestClient(app)
    resp = client.get("/jobs/job-b", headers=bearer(seeded["tokens"]["auditor"]))
    assert resp.status_code == 200


def test_tenant_id_from_principal_not_request_param(
    tenant_env: None, fakes: FakeJobStore, seeded: dict[str, Any],
) -> None:
    """Exit criterion: body/query tenant_id override is ineffective."""
    client = TestClient(app)
    payload = _payload()
    payload["tenant_id"] = seeded["tenant_b"]
    resp = client.post(
        "/jobs?tenant_id=" + seeded["tenant_b"],
        json=payload,
        headers=bearer(seeded["tokens"]["admin"]),
    )
    assert resp.status_code == 202
    created = fakes.jobs[resp.json()["job_id"]]
    assert created["tenant_id"] == seeded["tenant_a"]


def test_strip_tenant_id_from_json_helpers() -> None:
    """/jobs body tenant_id is dropped before routing (middleware unit)."""
    from api.middleware import _strip_tenant_id_from_json

    stripped = _strip_tenant_id_from_json(
        json.dumps({"repo_path": "r", "tenant_id": "tenant-b"}).encode("utf-8")
    )
    assert json.loads(stripped) == {"repo_path": "r"}
    # No tenant_id → byte-identical (no re-serialization).
    original = b'{"repo_path": "r"}'
    assert _strip_tenant_id_from_json(original) == original
    # Non-object JSON untouched.
    assert _strip_tenant_id_from_json(b"[1, 2]") == b"[1, 2]"
    # Invalid JSON untouched (routing rejects it as before).
    assert _strip_tenant_id_from_json(b"not json") == b"not json"


def test_body_tenant_id_stripped_before_routing(
    tenant_env: None, fakes: FakeJobStore, seeded: dict[str, Any],
) -> None:
    """Exit criterion §6 (body only): the strict job model never sees a
    client-supplied tenant_id; the stored tenant is the principal's."""
    client = TestClient(app)
    payload = _payload()
    payload["tenant_id"] = seeded["tenant_b"]
    resp = client.post(
        "/jobs", json=payload, headers=bearer(seeded["tokens"]["admin"]),
    )
    assert resp.status_code == 202
    created = fakes.jobs[resp.json()["job_id"]]
    assert created["tenant_id"] == seeded["tenant_a"]


def test_admin_tenant_field_not_stripped(
    tenant_env: None, fakes: FakeJobStore, seeded: dict[str, Any],
) -> None:
    """/api/v1/admin/* DECLARES tenant_id (admin row of the §2 matrix):
    the middleware leaves it so admins can target a tenant explicitly."""
    client = TestClient(app)
    resp = client.post(
        "/api/v1/admin/users",
        json={
            "email": "cross@b.example.com",
            "role": "viewer",
            "tenant_id": seeded["tenant_b"],
        },
        headers=bearer(seeded["tokens"]["admin"]),
    )
    assert resp.status_code == 201
    assert resp.json()["user"]["tenant_id"] == seeded["tenant_b"]


def test_sse_accepts_token_query_param(
    tenant_env: None, fakes: FakeJobStore, seeded: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import Request as FastAPIRequest

    import api.routes.jobs as jobs_module

    async def fake_is_disconnected(self: Any) -> bool:
        del self
        return True

    # jobs_module.Request IS fastapi.Request; patch the class object.
    monkeypatch.setattr(FastAPIRequest, "is_disconnected", fake_is_disconnected)
    monkeypatch.setattr(jobs_module, "_redis", FakeRedisStore())
    client = TestClient(app)
    resp = client.get(
        "/jobs/j-1/progress?key=" + seeded["tokens"]["viewer"],
    )
    assert resp.status_code == 200


def test_admin_users_token_flow_tenant_scoped(
    tenant_env: None, fakes: FakeJobStore, seeded: dict[str, Any],
) -> None:
    """Operator manages users/tokens inside its own tenant only."""
    client = TestClient(app)
    operator = seeded["tokens"]["operator"]
    # create a viewer in own tenant
    created = client.post(
        "/api/v1/admin/users",
        json={"email": "new@a.example.com", "role": "viewer",
              "tenant_id": seeded["tenant_b"]},  # override must be ignored
        headers=bearer(operator),
    )
    assert created.status_code == 201
    assert created.json()["user"]["tenant_id"] == seeded["tenant_a"]
    # mint a show-once token for that user
    minted = client.post(
        "/api/v1/admin/tokens",
        json={"name": "ci", "user_id": created.json()["user"]["id"],
              "scopes": "jobs:read"},
        headers=bearer(operator),
    )
    assert minted.status_code == 201
    cleartext = minted.json()["cleartext"]
    assert cleartext.startswith("sp_")
    # operator may not create admins
    assert client.post(
        "/api/v1/admin/users",
        json={"email": "bad@a.example.com", "role": "admin"},
        headers=bearer(operator),
    ).status_code == 403
    # cross-tenant user mutation -> 404 (never 403)
    assert client.post(
        f"/api/v1/admin/users/{seeded['users']['viewer']}/role",
        json={"role": "operator"}, headers=bearer(seeded["tokens"]["viewer_b"]),
    ).status_code == 403  # viewer may not manage users at all
    assert client.get(
        "/api/v1/admin/users", headers=bearer(seeded["tokens"]["viewer_b"]),
    ).status_code == 403


def test_operator_cross_tenant_token_revoke_is_404(
    tenant_env: None, fakes: FakeJobStore, seeded: dict[str, Any],
) -> None:
    from api.identity.store import get_identity_store
    from api.identity.tokens import token_hash_for

    store = get_identity_store()
    row = store.get_token_by_hash(token_hash_for(seeded["tokens"]["viewer_b"]))
    assert row is not None
    client = TestClient(app)
    resp = client.delete(
        f"/api/v1/admin/tokens/{row.id}", headers=bearer(seeded["tokens"]["operator"]),
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "USER_NOT_FOUND"


# ── OIDC: mock JWKS (RS256 signed / expired / wrong issuer) ──────────────────


def _rsa_key() -> tuple[Any, str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key()
    numbers = public.public_numbers()
    n_bytes = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
    e_bytes = numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")

    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    return key, b64url(n_bytes), b64url(e_bytes)


def _mock_idp_transport(issuer: str, jwks: dict[str, Any]) -> httpx.MockTransport:
    discovery = {
        "issuer": issuer,
        "authorization_endpoint": issuer + "/authorize",
        "token_endpoint": issuer + "/token",
        "jwks_uri": issuer + "/jwks",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/.well-known/openid-configuration":
            return httpx.Response(200, json=discovery)
        if request.url.path == "/jwks":
            return httpx.Response(200, json=jwks)
        if request.url.path == "/token":
            return httpx.Response(200, json={"id_token": "unused"})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture()
def oidc_setup(
    tenant_env: None, seeded: dict[str, Any], monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    key, n, e = _rsa_key()
    jwks = {"keys": [{"kty": "RSA", "use": "sig", "alg": "RS256",
                      "kid": "kid-1", "n": n, "e": e}]}
    validator = OidcValidator(
        ISSUER, CLIENT_ID, transport=_mock_idp_transport(ISSUER, jwks),
        discovery_ttl=0.0,
    )
    monkeypatch.setenv("OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("OIDC_CLIENT_ID", CLIENT_ID)
    import api.identity.oidc as oidc_module

    monkeypatch.setattr(oidc_module, "_validator", validator)
    monkeypatch.setattr(oidc_module, "_validator_key", (ISSUER, CLIENT_ID))
    return {"key": key, "kid": "kid-1"}


def _sign_id_token(
    key: Any, kid: str, *, issuer: str = ISSUER, audience: str = CLIENT_ID,
    exp_offset: float = 3600.0, claims: dict[str, Any] | None = None,
) -> str:
    now = time.time()
    payload: dict[str, Any] = {
        "iss": issuer,
        "aud": audience,
        "sub": "oidc-user-1",
        "email": "carol@oidc.example.com",
        "iat": now - 10.0,
        "exp": now + exp_offset,
    }
    if claims:
        payload.update(claims)
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": kid})


def test_oidc_valid_token_role_claim_mapping(
    oidc_setup: dict[str, Any], seeded: dict[str, Any],
) -> None:
    """RS256 mock-JWKS token: signature ok -> role claim -> principal."""
    token = _sign_id_token(
        oidc_setup["key"], oidc_setup["kid"],
        claims={"roles": ["specproof:operator"], "tenant_id": seeded["tenant_a"]},
    )
    client = TestClient(app)
    resp = client.get("/auth/me", headers=bearer(token))
    assert resp.status_code == 200
    principal = resp.json()["principal"]
    assert principal["roles"] == ["operator"]
    assert principal["tenant_id"] == seeded["tenant_a"]
    from api.identity.store import get_identity_store

    user = get_identity_store().get_user_by_oidc_sub("oidc-user-1")
    assert user is not None and user.tenant_id == seeded["tenant_a"]


def test_oidc_expired_token_rejected(
    oidc_setup: dict[str, Any], seeded: dict[str, Any],
) -> None:
    del seeded
    token = _sign_id_token(
        oidc_setup["key"], oidc_setup["kid"], exp_offset=-60.0,
    )
    client = TestClient(app)
    resp = client.get("/auth/me", headers=bearer(token))
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTH_REQUIRED"


def test_oidc_wrong_issuer_rejected(
    oidc_setup: dict[str, Any], seeded: dict[str, Any],
) -> None:
    del seeded
    token = _sign_id_token(
        oidc_setup["key"], oidc_setup["kid"], issuer="https://evil-idp.test",
    )
    client = TestClient(app)
    resp = client.get("/auth/me", headers=bearer(token))
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTH_REQUIRED"


def test_oidc_wrong_audience_rejected(
    oidc_setup: dict[str, Any], seeded: dict[str, Any],
) -> None:
    del seeded
    token = _sign_id_token(
        oidc_setup["key"], oidc_setup["kid"], audience="other-client",
    )
    client = TestClient(app)
    resp = client.get("/auth/me", headers=bearer(token))
    assert resp.status_code == 401


def test_oidc_unknown_role_falls_back_viewer(
    oidc_setup: dict[str, Any], seeded: dict[str, Any],
) -> None:
    token = _sign_id_token(
        oidc_setup["key"], oidc_setup["kid"],
        claims={"roles": ["super-hacker"], "tenant_id": seeded["tenant_a"]},
    )
    client = TestClient(app)
    resp = client.get("/auth/me", headers=bearer(token))
    assert resp.status_code == 200
    assert resp.json()["principal"]["roles"] == ["viewer"]


def test_oidc_tenant_comes_from_user_row_not_claim(
    oidc_setup: dict[str, Any], seeded: dict[str, Any],
) -> None:
    """A tenant claim can never move an existing user across tenants."""
    from api.identity.store import get_identity_store

    get_identity_store().create_user(
        seeded["tenant_b"], "pre@b.example.com", role="viewer",
        oidc_sub="oidc-user-1",
    )
    token = _sign_id_token(
        oidc_setup["key"], oidc_setup["kid"],
        claims={"roles": ["operator"], "tenant_id": seeded["tenant_a"]},
    )
    client = TestClient(app)
    resp = client.get("/auth/me", headers=bearer(token))
    assert resp.status_code == 200
    assert resp.json()["principal"]["tenant_id"] == seeded["tenant_b"]


def test_oidc_login_redirect_carries_state(
    oidc_setup: dict[str, Any], seeded: dict[str, Any],
) -> None:
    del seeded
    client = TestClient(app)
    resp = client.get("/auth/oidc/login", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert location.startswith(ISSUER + "/authorize")
    assert "state=" in location and "nonce=" in location


# ── Single-tenant compat (§4) ────────────────────────────────────────────────


def test_auth_disabled_admin_endpoints_503_and_config_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SPECPROOF_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("OIDC_ISSUER", raising=False)
    monkeypatch.delenv("SPECPROOF_TOKEN_HMAC_KEY", raising=False)
    from api.identity.oidc import reset_oidc_validator
    from api.identity.store import reset_identity_store

    reset_identity_store()
    reset_oidc_validator()
    client = TestClient(app)
    config = client.get("/auth/config")
    assert config.status_code == 200
    assert config.json()["auth_mode"] == "legacy"
    assert config.json()["oidc"]["enabled"] is False
    resp = client.get("/api/v1/admin/tenants")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
    # No bearer, no key: the legacy fail-closed path still governs /jobs.
    resp2 = client.get("/jobs")
    assert resp2.status_code in (401, 503)


# ── Repository-layer tenant scoping (storage/mysql.py) ───────────────────────


class _FakeCursor:
    def __init__(self, owner: _FakeMysql) -> None:
        self.owner = owner
        self.rows: list[dict[str, Any]] = []

    def execute(self, sql: str, params: Any = None) -> None:
        self.owner.queries.append((sql, params))
        self.rows = self.owner.pending_rows.pop(0) if self.owner.pending_rows else []

    def fetchone(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


class _FakeConn:
    def __init__(self, owner: _FakeMysql) -> None:
        self.owner = owner
        self._cursor = _FakeCursor(owner)

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


class _FakeMysql:
    def __init__(self) -> None:
        self.queries: list[tuple[str, Any]] = []
        self.pending_rows: list[list[dict[str, Any]]] = []

    def _connect(self) -> _FakeConn:
        return _FakeConn(self)


@pytest.fixture()
def fake_mysql(monkeypatch: pytest.MonkeyPatch) -> _FakeMysql:
    fake = _FakeMysql()
    store = MySQLStore()
    monkeypatch.setattr(store, "_connect", fake._connect)
    monkeypatch.setattr(MySQLStore, "_connect", fake._connect)
    return fake


def test_repository_get_job_scoped_returns_none_and_audits(fake_mysql: _FakeMysql) -> None:
    """Scoped read of another tenant's job = None + audit(attempted_tenant)."""
    fake_mysql.pending_rows = [[], [{"tenant_id": "tenant-b"}]]
    scope = TenantScope("tenant-a", user_id="u1", roles=frozenset({"viewer"}))
    store = MySQLStore()
    token = TENANT_SCOPE_VAR.set(scope)
    try:
        result = store.get_job("job-b")
    finally:
        TENANT_SCOPE_VAR.reset(token)
    assert result is None
    assert "tenant_id = %s" in str(fake_mysql.queries[0][0])
    audit = [q for q in fake_mysql.queries if "audit_logs" in str(q[0])]
    assert audit and "attempted_tenant" in str(audit[0][0])
    assert audit[0][1] is not None and audit[0][1][-1] == "tenant-b"


def test_repository_get_job_unscoped_sql_unchanged(fake_mysql: _FakeMysql) -> None:
    """Without a tenant scope the SQL is byte-identical to the old build."""
    fake_mysql.pending_rows = [[{"id": "job-1", "status": "QUEUED"}]]
    assert MySQLStore().get_job("job-1") is not None
    assert fake_mysql.queries[0][0] == "SELECT * FROM verification_jobs WHERE id = %s"


def test_repository_list_jobs_filters_by_tenant(fake_mysql: _FakeMysql) -> None:
    fake_mysql.pending_rows = [[{"id": "job-a"}]]
    scope = TenantScope("tenant-a", user_id="u1", roles=frozenset({"viewer"}))
    token = TENANT_SCOPE_VAR.set(scope)
    try:
        rows = MySQLStore().list_recent_jobs(10)
    finally:
        TENANT_SCOPE_VAR.reset(token)
    assert rows == [{"id": "job-a"}]
    assert "tenant_id = %s OR tenant_id IS NULL" in str(fake_mysql.queries[0][0])


def test_repository_create_job_stamps_principal_tenant(fake_mysql: _FakeMysql) -> None:
    scope = TenantScope("tenant-a", user_id="u1", roles=frozenset({"admin"}))
    job = {"id": "job-1", "repo_path": "r", "base_ref": "b", "head_ref": "h",
           "spec_path": "s", "depth": "FAST"}
    token = TENANT_SCOPE_VAR.set(scope)
    try:
        MySQLStore().create_job_with_outbox(job)
    finally:
        TENANT_SCOPE_VAR.reset(token)
    insert = fake_mysql.queries[0]
    assert "tenant_id" in str(insert[0])
    assert isinstance(insert[1], dict) and insert[1]["tenant_id"] == "tenant-a"
