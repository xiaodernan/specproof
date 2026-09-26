from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.auth import enforce_rate_limit
from api.routes.model_settings import require_model_admin
from api.server import app
from providers.config import load_model_config, normalize_base_url, save_model_config
from storage.mysql import MySQLStore
from storage.tenant_scope import TENANT_SCOPE_VAR, TenantScope


@pytest.fixture
def model_file(monkeypatch, tmp_path):
    for name in (
        "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_PROTOCOL", "LLM_REASONING_EFFORT",
    ):
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "model.json"
    monkeypatch.setenv("SPECPROOF_MODEL_CONFIG", str(path))
    monkeypatch.setenv("SPECPROOF_API_KEY", "workspace-test")
    app.dependency_overrides[enforce_rate_limit] = lambda: None
    yield path
    app.dependency_overrides.pop(enforce_rate_limit, None)


def test_model_config_keeps_secret_on_server_and_preserves_blank_key(model_file):
    client = TestClient(app)
    headers = {"X-API-Key": "workspace-test"}
    payload = {"base_url": "https://example.test", "api_key": "private-model-value",
               "model": "gpt-6-astra", "protocol": "responses", "reasoning_effort": "max"}
    result = client.post("/api/v1/model/config", json=payload, headers=headers)
    assert result.status_code == 200
    assert "private-model-value" not in result.text
    assert result.json()["base_url"] == "https://example.test/v1"
    payload["api_key"] = ""
    payload["model"] = "other-model"
    assert client.post("/api/v1/model/config", json=payload, headers=headers).status_code == 200
    assert json.loads(model_file.read_text(encoding="utf-8"))["api_key"] == "private-model-value"
    assert "private-model-value" not in client.get("/api/v1/model/config", headers=headers).text
    assert client.get("/api/v1/model/config").status_code == 401


def test_shared_model_config_refuses_tenant_mutation():
    request = SimpleNamespace(state=SimpleNamespace(principal=SimpleNamespace(roles={"admin"})))
    with pytest.raises(Exception) as error:
        require_model_admin(request)
    assert error.value.status_code == 403


def test_environment_config_cannot_be_silently_overwritten(model_file, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "deployment-key")
    assert load_model_config()["source"] == "environment"
    with pytest.raises(ValueError, match="环境变量"):
        save_model_config({"base_url": "https://example.test", "api_key": "new-key"})
    assert not model_file.exists()


@pytest.mark.parametrize("url", ["file:///tmp", "https://user:secret@example.test", "https://example.test?k=s"])
def test_provider_url_rejects_credential_bearing_or_invalid_addresses(url):
    with pytest.raises(ValueError):
        normalize_base_url(url)


def test_job_search_uses_matching_tenant_filters_and_bounded_page(monkeypatch):
    statements = []
    class Cursor:
        def execute(self, sql, params):
            statements.append((sql, params))
        def fetchone(self):
            return {"total": 51}
        def fetchall(self):
            return [{"id": "job-26"}]
    class Connection:
        def cursor(self):
            return Cursor()
    @contextmanager
    def connection(self):
        yield Connection()
    monkeypatch.setattr(MySQLStore, "connection", connection)
    token = TENANT_SCOPE_VAR.set(TenantScope("tenant-a", roles=frozenset({"viewer"})))
    try:
        result = MySQLStore().search_jobs(25, 25, "BLOCKED", "checkout")
    finally:
        TENANT_SCOPE_VAR.reset(token)
    assert result["total"] == 51 and result["offset"] == 25
    assert len(statements) == 2
    for sql, params in statements:
        assert "tenant_id = %s" in sql and "status = %s" in sql and "LOCATE(%s" in sql
        assert params[:2] == ("tenant-a", "BLOCKED")
        assert "checkout" not in sql
    assert statements[1][1][-2:] == (25, 25)
    assert "last_error, summary," not in statements[1][0]
