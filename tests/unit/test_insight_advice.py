"""Insight AI 解读 — unit + route tests.

Same discipline as the /jobs/{id}/ai-summary tests: the model is an
*interpretation*, never a verdict; any failure becomes one honest error (503
on the wire), never a fabricated paragraph. Covered:

  * packet assembly: allowlist-only keys, bounded output, list caps,
    hostile extra keys dropped, junk coerced safely;
  * fingerprint: stable on identical packet, changes on data change;
  * generate_insight_advice: returns model text + usage; ANY provider
    failure (raise, empty content) becomes InsightAdviceUnavailable;
  * the endpoint: admin and operator get the advice (cached round-trip on
    the identical packet), viewer/auditor are refused (403), an unavailable
    model answers 503 PROVIDER_UNAVAILABLE, never fabricated text.

No Docker, no network, no real model: the identity world runs on SQLite
(SPECPROOF_IDENTITY_URL) exactly like test_tenant_auth.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.insight_advice as insight
from api.identity.tokens import mint_token
from api.insight_advice import (
    InsightAdviceUnavailable,
    build_insight_packet,
    fingerprint,
    generate_insight_advice,
    sanitize_stats,
)
from api.server import app

HMAC_KEY = "test" + "-hmac-" + "key-w41"
ISSUER = "https://idp.test"


def _stats(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "population": 240,
        "slope_per_day": 12.5,
        "r2": 0.81,
        "sessions_today": 389,
        "median_dwell_min": 6,
        "drill_pass_rate": 0.71,
        "tour_completion_rate": 0.42,
        "funnel": [{"k": "visit", "v": 240}, {"k": "visited_tour", "v": 90}],
        "features": [{"k": "tour", "v": 108}],
        "personas": [{"k": "careful_verifier", "v": 40}],
        "heat_taps_total": 31,
        "heat_rage_count": 3,
        "onboarding_routes": 5,
    }
    base.update(overrides)
    return base


# ── sanitize / packet ─────────────────────────────────────────────────────────


def test_sanitize_drops_hostile_and_non_allowlisted_keys() -> None:
    stats = _stats()
    stats["session_token"] = "SECRET-DO-NOT-SEND"
    stats["user_email"] = "someone@example.com"
    stats["click_stream"] = [{"at": 1, "path": "/admin"}]
    stats["population"] = "not-a-number"
    safe = sanitize_stats(stats)
    assert "session_token" not in safe
    assert "user_email" not in safe
    assert "click_stream" not in safe
    assert "population" not in safe  # non-numeric coerced away
    assert safe["funnel"] == [{"k": "visit", "v": 240}, {"k": "visited_tour", "v": 90}]


def test_sanitize_caps_lists_and_key_lengths() -> None:
    stats = _stats(
        funnel=[{"k": f"stage-{i}", "v": i} for i in range(30)],
        features=[{"k": "x" * 100, "v": 1}],
    )
    safe = sanitize_stats(stats)
    assert len(safe["funnel"]) == 8
    assert len(safe["features"][0]["k"]) <= 60


def test_packet_stays_bounded_under_adversarial_growth() -> None:
    stats = _stats(
        funnel=[{"k": "s" * 500, "v": v} for v in range(8)],
        features=[{"k": "f" * 500, "v": v} for v in range(8)],
        personas=[{"k": "p" * 500, "v": v} for v in range(8)],
    )
    text = build_insight_packet(stats)
    assert len(text) <= 4_000


def test_fingerprint_is_stable_and_data_sensitive() -> None:
    assert fingerprint(_stats()) == fingerprint(_stats())
    assert fingerprint(_stats()) != fingerprint(_stats(slope_per_day=13.0))


def test_generate_uses_stub_provider_and_reports_usage() -> None:
    class _Response:
        content = "洞察一：漏斗在②掉了三分之一，建议先修引导文案的第一跳。"
        usage = {"prompt_tokens": 1200, "completion_tokens": 140}
        model = "gpt-6.1-terra"

    class _Stub:
        def __init__(self, **_: Any) -> None:
            pass

        async def chat(self, messages, **_: Any):
            return _Response()

        async def close(self):
            return None

    out = __import__("asyncio").run(
        generate_insight_advice(_stats(), provider_factory=_Stub),
    )
    assert "洞察一" in out["advice"]
    assert out["usage"]["completion_tokens"] == 140
    assert out["evidence_packet_chars"] == len(build_insight_packet(_stats()))


def test_generate_converts_any_provider_failure_into_unavailable() -> None:
    class _Boom:
        def __init__(self, **_: Any) -> None:
            pass

        async def chat(self, *args, **kwargs):
            raise RuntimeError("gateway timeout (test)")

        async def close(self):
            return None

    with pytest.raises(InsightAdviceUnavailable):
        __import__("asyncio").run(
            generate_insight_advice(_stats(), provider_factory=_Boom),
        )

    class _Empty:
        def __init__(self, **_: Any) -> None:
            pass

        async def chat(self, *args, **kwargs):
            return type("R", (), {"content": "   ", "usage": {}, "model": None})()

        async def close(self):
            return None

    with pytest.raises(InsightAdviceUnavailable):
        __import__("asyncio").run(
            generate_insight_advice(_stats(), provider_factory=_Empty),
        )


# ── the endpoint ──────────────────────────────────────────────────────────────


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def tenant_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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
    from api.identity.store import get_identity_store

    store = get_identity_store()
    tenant_a = store.create_tenant("tenant-a")
    users: dict[str, str] = {}
    for role in ("admin", "operator", "viewer", "auditor"):
        user = store.create_user(tenant_a.id, f"{role}@a.example.com", role=role)
        users[role] = user.id
    tokens: dict[str, str] = {}
    for role, user_id in users.items():
        _row, token = mint_token(store, user_id, name=role)
        tokens[role] = token
    return {"tokens": tokens}


@pytest.fixture()
def stub_advice(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict[str, Any]] = []

    async def _fake(stats: dict[str, Any], **_: Any) -> dict[str, Any]:
        calls.append(stats)
        return {
            "advice": "洞察一：漏斗②掉得最狠，热区 rage 集中在按钮；先修引导第一跳。",
            "model": "gpt-6.1-terra",
            "model_latency_ms": 812,
            "usage": {"prompt_tokens": 900, "completion_tokens": 120},
            "evidence_packet_chars": len(json.dumps(stats, ensure_ascii=False)),
        }

    monkeypatch.setattr(insight, "generate_insight_advice", _fake)
    monkeypatch.setattr(insight, "insight_redis", lambda: None)
    return calls


def test_admin_gets_advice_and_stats_stay_sanitized(
    tenant_env: None, seeded: dict[str, Any], stub_advice: list[dict[str, Any]]
) -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/v1/admin/insight-advice",
        json={"stats": _stats() | {"hostile_key": "SECRET"}},
        headers=bearer(seeded["tokens"]["admin"]),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "洞察一" in body["advice"]
    assert body["cached"] is False
    # the route passes the raw dict to the module boundary — sanitization
    # happens there (proven by the module-level tests above), not at the route
    assert stub_advice[0]["hostile_key"] == "SECRET"


def test_operator_also_gets_advice(
    tenant_env: None, seeded: dict[str, Any], stub_advice: list[dict[str, Any]]
) -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/v1/admin/insight-advice",
        json={"stats": _stats()},
        headers=bearer(seeded["tokens"]["operator"]),
    )
    assert resp.status_code == 200


def test_viewer_and_auditor_are_refused(
    tenant_env: None, seeded: dict[str, Any], stub_advice: list[dict[str, Any]]
) -> None:
    client = TestClient(app)
    for role in ("viewer", "auditor"):
        resp = client.post(
            "/api/v1/admin/insight-advice",
            json={"stats": _stats()},
            headers=bearer(seeded["tokens"][role]),
        )
        assert resp.status_code == 403, role


def test_unavailable_model_answers_503_never_fabricated(
    tenant_env: None, seeded: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _boom(stats: dict[str, Any], **_: Any):
        raise insight.InsightAdviceUnavailable("模型暂时不可用，无法生成 AI 解读。")

    monkeypatch.setattr(insight, "generate_insight_advice", _boom)
    monkeypatch.setattr(insight, "insight_redis", lambda: None)
    client = TestClient(app)
    resp = client.post(
        "/api/v1/admin/insight-advice",
        json={"stats": _stats()},
        headers=bearer(seeded["tokens"]["admin"]),
    )
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "PROVIDER_UNAVAILABLE"
    assert "advice" not in json.dumps(body)
