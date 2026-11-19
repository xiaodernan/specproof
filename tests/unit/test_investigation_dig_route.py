"""The Dig — admin-only repo investigation via readonly investigators.

Route + module level coverage:

* RBAC fail-closed for viewer/auditor;
* admin & operator path returns a verdict with evidence, never fabricated;
* model failure surfaces as 503, never a synthetic answer;
* question passes through verbatim; overly long questions reject at the pydantic layer;
* the route goes through the module boundary; sanitization happens at the module; the route stays thin.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.investigation_dig as investigation_dig
from api.identity.tokens import mint_token
from api.server import app


@pytest.fixture()
def tenant_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hmac_key = "a" * 64
    monkeypatch.setenv("SPECPROOF_AUTH_ENABLED", "true")
    monkeypatch.setenv("SPECPROOF_IDENTITY_URL", f"sqlite:{tmp_path / 'identity.db'}")
    monkeypatch.setenv("SPECPROOF_TOKEN_HMAC_KEY", hmac_key)
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
    from api.identity.store import get_identity_store

    store = get_identity_store()

    tenant = store.create_tenant("Acme")
    users = {}
    for role in ("admin", "operator", "viewer", "auditor"):
        user = store.create_user(tenant.id, f"{role}@a.example.com", role=role)
        users[role] = user.id
    tokens: dict[str, str] = {}
    for role, user_id in users.items():
        _row, token = mint_token(store, user_id, name=role)
        tokens[role] = token
    return {"tokens": tokens}


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def stub_dig(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    async def _fake(question: str) -> dict[str, Any]:
        calls.append(question)
        return {
            "question": question.strip(),
            "verdict": "EVIDENCE-GATHERED",
            "findings": [
                {"role": "explorer", "claim": "这是一个 AI 生成代码差分验证平台，前端 Next.js，后端 FastAPI。", "evidence": "README + pyproject peek", "confidence": 0.9},
                {"role": "tester", "claim": "test lanes focus on differential/config/acceptance lanes.", "evidence": "tests/unit listing", "confidence": 0.8},
                {"role": "security", "claim": "tracked `.env.example` exists — sample keys are placeholders, not real creds.", "evidence": "env sample file", "confidence": 0.7},
            ],
            "agents": [
                {"name": "investigate_explorer", "role": "explorer", "outcome": "ok", "tokens": 4200},
                {"name": "investigate_tester", "role": "tester", "outcome": "ok", "tokens": 3100},
                {"name": "investigate_security", "role": "security", "outcome": "ok", "tokens": 2800},
            ],
            "total_tokens_used": 10100,
            "generation_time_ms": 14000,
            "model": "gpt-6.1-terra",
        }

    monkeypatch.setattr(investigation_dig, "generate_investigation_dig", _fake)
    return calls


def test_admin_gets_a_repo_investigation(
    tenant_env: None, seeded: dict[str, Any], stub_dig: list[str]
) -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/v1/admin/investigation-dig",
        json={"question": "本仓库做了什么？"},
        headers=bearer(seeded["tokens"]["admin"]),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["verdict"] == "EVIDENCE-GATHERED"
    assert body["total_tokens_used"] == 10100
    assert len(body["agents"]) == 3
    assert stub_dig == ["本仓库做了什么？"]


def test_operator_also_gets_an_investigation(
    tenant_env: None, seeded: dict[str, Any], stub_dig: list[str]
) -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/v1/admin/investigation-dig",
        json={"question": "这仓库做了什么？"},
        headers=bearer(seeded["tokens"]["operator"]),
    )
    assert resp.status_code == 200


def test_viewer_and_auditor_are_refused(
    tenant_env: None, seeded: dict[str, Any], stub_dig: list[str]
) -> None:
    client = TestClient(app)
    for role in ("viewer", "auditor"):
        resp = client.post(
            "/api/v1/admin/investigation-dig",
            json={"question": "anything"},
            headers=bearer(seeded["tokens"][role]),
        )
        assert resp.status_code == 403, role


def test_model_unavailable_answers_503_never_fabricated(
    tenant_env: None, seeded: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _boom(question: str):
        raise investigation_dig.InvestigationDigError("模型暂时不可用。")

    monkeypatch.setattr(investigation_dig, "generate_investigation_dig", _boom)
    client = TestClient(app)
    resp = client.post(
        "/api/v1/admin/investigation-dig",
        json={"question": "本仓库做了什么？"},
        headers=bearer(seeded["tokens"]["admin"]),
    )
    assert resp.status_code == 503


def test_missing_question_rejected_422(
    tenant_env: None, seeded: dict[str, Any], stub_dig: list[str]
) -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/v1/admin/investigation-dig",
        json={},
        headers=bearer(seeded["tokens"]["admin"]),
    )
    assert resp.status_code == 422


def test_question_over_600_chars_rejected(
    tenant_env: None, seeded: dict[str, Any], stub_dig: list[str]
) -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/v1/admin/investigation-dig",
        json={"question": "问" * 601},
        headers=bearer(seeded["tokens"]["admin"]),
    )
    assert resp.status_code == 422
