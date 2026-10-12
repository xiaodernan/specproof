"""API tests for POST /api/v1/demo/prepare (roadmap Phase 1.3, backend half).

These tests prove the HTTP + auth contract of the demo-prepare endpoint and the
translation of the underlying command's click errors into HTTP responses. The
real ``prepare_demo_repo`` (which mutates the demo repo's git state) is covered
by its own command test; here it is mocked so the endpoint test never touches
the filesystem or the demo repo, and stays deterministic in any environment.
"""

import click
import pytest
from fastapi.testclient import TestClient

from api.server import app

API_KEY = "test-api-key-demo-123456"


@pytest.fixture(autouse=True)
def auth_env(monkeypatch):
    monkeypatch.setenv("SPECPROOF_API_KEY", API_KEY)


@pytest.fixture
def client():
    return TestClient(app)


def test_prepare_requires_api_key(client):
    # No X-API-Key header -> 401 (fail-closed auth).
    resp = client.post("/api/v1/demo/prepare")
    assert resp.status_code == 401


def test_prepare_is_idempotent_when_refs_exist(client, monkeypatch):
    monkeypatch.setattr(
        "api.routes.demo.prepare_demo_repo", lambda *a, **k: False
    )
    resp = client.post(
        "/api/v1/demo/prepare", headers={"X-API-Key": API_KEY}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is False
    assert body["refs"] == ["base", "head-v1"]
    # Honest message: already present, not "created".
    assert "已存在" in body["message"]


def test_prepare_reports_created_when_refs_were_missing(client, monkeypatch):
    monkeypatch.setattr(
        "api.routes.demo.prepare_demo_repo", lambda *a, **k: True
    )
    resp = client.post(
        "/api/v1/demo/prepare", headers={"X-API-Key": API_KEY}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is True
    assert body["refs"] == ["base", "head-v1"]


def test_prepare_surfaces_setup_errors_as_422(client, monkeypatch):
    # A genuine setup failure (missing demo dir / spec, or guard already
    # removed) must become a 422 with the original message — never a
    # fabricated 200 success.
    def _boom(*a, **k):
        raise click.ClickException("演示仓库目录未找到: demo/spring-backend")

    monkeypatch.setattr("api.routes.demo.prepare_demo_repo", _boom)
    resp = client.post(
        "/api/v1/demo/prepare", headers={"X-API-Key": API_KEY}
    )
    assert resp.status_code == 422
    assert "演示仓库目录未找到" in resp.text
