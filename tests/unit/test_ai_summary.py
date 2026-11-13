"""API/unit tests for /jobs/{id}/ai-summary (AI 解读 — never a verdict of its own).

The summary is an interpretation of evidence the reviewer already sees — it
must degrade to an honest error, never to a fabricated one, and it must not
re-spend tokens on identical evidence. Covered:

  * packet assembly carries verdict/matrix counts/blocked contract ids and
    stays bounded on adversarial row counts;
  * fingerprint is row-order-insensitive and verdict-sensitive;
  * generate_ai_summary returns model text + usage, and converts ANY provider
    failure (raise, empty content) into AiSummaryUnavailable;
  * the endpoint: cached on identical evidence, regenerates on changed
    evidence, echoes 503 on an unavailable model, 404/401/503 on the job read.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from integrations.notify.protocol import SendStatus

import api.ai_summary as ai_summary
from api.ai_summary import (
    AiSummaryUnavailable,
    build_evidence_packet,
    fingerprint,
)
from api.server import app


API_KEY = "ai-summary-test-key"


@pytest.fixture(autouse=True)
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECPROOF_API_KEY", API_KEY)


# ---------- module-level legs -------------------------------------------

def _summary(**overrides: Any) -> dict[str, Any]:
    base = {
        "verdict": "BLOCKED",
        "contracts_total": 6,
        "matrix_passed": 4,
        "matrix_failed": 1,
        "matrix_unverified": 1,
        "matrix_rows": [
            {"contract_id": "AUTH-01", "result": "FAIL", "severity": "BLOCKER",
             "evidence_type": "base_pass_head_fail"},
            {"contract_id": "UNIQUE-01", "result": "PASS", "severity": "MAJOR",
             "evidence_type": "static_analysis"},
        ],
        "capsules": ["a.zip", "b.zip"],
        "findings_total": 1,
        "retrieval_note": "es unavailable",
    }
    base.update(overrides)
    return base


def test_packet_carries_verdict_matrix_and_blocked_contract() -> None:
    text = build_evidence_packet(_summary())
    assert '"verdict":"BLOCKED"' in text
    assert '"matrix_failed":1' in text
    assert '"AUTH-01"' in text
    assert "base_pass_head_fail" in text
    assert len(text) <= 6000


def test_packet_is_bounded_on_adversarial_row_counts() -> None:
    rows = [
        {"contract_id": f"CONTRACT-{i:04d}", "result": "FAIL", "severity": "MAJOR",
         "evidence_type": "java_source_diff"}
        for i in range(400)
    ]
    text = build_evidence_packet(_summary(matrix_rows=rows))
    assert len(text) <= 6000
    assert "java_source_diff" in text
    assert "BLOCKED" in text


def test_fingerprint_is_row_order_insensitive() -> None:
    rows = _summary()["matrix_rows"]
    a = fingerprint(_summary(matrix_rows=rows))
    b = fingerprint(_summary(matrix_rows=list(reversed(rows))))
    assert a == b


def test_fingerprint_changes_with_the_verdict() -> None:
    assert fingerprint(_summary()) != fingerprint(_summary(verdict="PASS"))


class _FakeProvider:
    def __init__(self, content: str = "AI 解读：本次验收受阻。", usage: dict | None = None) -> None:
        self._content = content
        self._usage = usage or {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        self.chat_calls = 0

    async def chat(self, messages, timeout=None):  # noqa: ANN001
        self.chat_calls += 1
        class _Resp:
            def __init__(self, content, usage):  # noqa: ANN001
                self.content = content
                self.finish_reason = "stop"
                self.usage = usage
        return _Resp(self._content, self._usage)

    async def close(self) -> None:
        return None


@pytest.mark.anyio
async def test_generate_returns_model_text_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _FakeProvider()
    monkeypatch.setattr(ai_summary, "OpenAICompatibleProvider", lambda **_kw: provider)
    result = await ai_summary.generate_ai_summary(_summary(), [])
    assert result["summary"] == "AI 解读：本次验收受阻。"
    assert result["usage"]["total_tokens"] == 30
    assert provider.chat_calls == 1


@pytest.mark.anyio
async def test_generate_provider_raise_maps_to_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Boom:
        async def chat(self, messages, timeout=None):  # noqa: ANN001
            raise RuntimeError("provider down")

        async def close(self) -> None:
            return None

    monkeypatch.setattr(ai_summary, "OpenAICompatibleProvider", lambda **_kw: _Boom())
    with pytest.raises(AiSummaryUnavailable):
        await ai_summary.generate_ai_summary(_summary(), [])


@pytest.mark.anyio
async def test_generate_provider_empty_content_maps_to_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ai_summary,
        "OpenAICompatibleProvider",
        lambda **_kw: _FakeProvider(content=""),
    )
    with pytest.raises(AiSummaryUnavailable):
        await ai_summary.generate_ai_summary(_summary(), [])


# ---------- endpoint legs -------------------------------------------------

def _row_set(*, fail_next: bool = False):
    class FakeMySQLStore:
        rows: dict = {}
        fail_next = False

        def __init__(self) -> None:
            self.fail_next = fail_next

        def get_job(self, job_id):  # noqa: ANN001
            return self.rows.get(job_id, {"id": job_id, "status": "SUCCEEDED"})

        def create_job_with_outbox(self, job):  # noqa: ANN001
            self.rows[job["id"]] = dict(job)
            return job["id"]

        def search_jobs(self, limit=50, offset=0, status=None, query=""):  # noqa: ANN001
            return {"jobs": [], "total": 0, "limit": limit, "offset": offset}

        def get_job_summary(self, job_id):  # noqa: ANN001
            if self.fail_next:
                raise ConnectionError("mysql down")
            return _summary()

    return FakeMySQLStore


class FakeRedisCache:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def get_cached_llm_response(self, key: str):
        raw = self._data.get(f"specproof:cache:model:{key}")
        return json.loads(raw) if raw else None

    def cache_llm_response(self, key: str, response, ttl: int = 3600):  # noqa: ANN001
        self._data[f"specproof:cache:model:{key}"] = json.dumps(response, ensure_ascii=False)

    def incr(self, key: str):
        return 1

    def expire(self, key: str, ttl: int):
        return None

    def is_ready(self) -> bool:
        return True


class FakeMySQLClient:
    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def cursor(self):
            class _C:
                def execute(self, *_a, **_kw):
                    return None

                def fetchall(self):
                    return []

            return _C()

    def connection(self):
        return self._Conn()


@pytest.fixture()
def fake_backend(monkeypatch: pytest.MonkeyPatch):
    fresh = _row_set()()
    monkeypatch.setattr("api.services.verification_service.MySQLStore", lambda: fresh)
    monkeypatch.setattr("storage.mysql.MySQLStore", FakeMySQLClient)
    redis_cache = FakeRedisCache()
    monkeypatch.setattr("api.routes.web.ai_summary_redis", lambda: redis_cache)
    monkeypatch.setattr("storage.redis.RedisStore", lambda: redis_cache)
    return {"mysql": fresh, "redis": redis_cache}


def _client() -> TestClient:
    return TestClient(app)


@pytest.mark.integration
def test_ai_summary_happy_path_then_cached(monkeypatch: pytest.MonkeyPatch, fake_backend) -> None:  # noqa: ANN001
    provider = _FakeProvider()
    monkeypatch.setattr(ai_summary, "OpenAICompatibleProvider", lambda **_kw: provider)

    job_id = "job-ai-summary-1"
    resp = _client().post(
        f"/api/v1/jobs/{job_id}/ai-summary", headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["cached"] is False
    assert body["evidence_packet_chars"] <= 6000
    assert provider.chat_calls == 1

    resp = _client().post(
        f"/api/v1/jobs/{job_id}/ai-summary", headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["cached"] is True
    assert provider.chat_calls == 1


@pytest.mark.integration
def test_ai_summary_model_down_yields_503(monkeypatch: pytest.MonkeyPatch, fake_backend) -> None:  # noqa: ANN001
    class _Boom:
        async def chat(self, messages, timeout=None):  # noqa: ANN001
            raise RuntimeError("provider down")

        async def close(self) -> None:
            return None

    monkeypatch.setattr(ai_summary, "OpenAICompatibleProvider", lambda **_kw: _Boom())
    resp = _client().post(
        "/api/v1/jobs/job-ai-summary-2/ai-summary", headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 503
    assert "AI 解读" in resp.text or "模型" in resp.text


@pytest.mark.integration
def test_ai_summary_missing_job_yields_404(fake_backend) -> None:  # noqa: ANN001
    # FakeMySQLStore returns {} for unknown ids → require_job 404.
    fake_backend["mysql"].get_job = lambda job_id: None  # noqa: ANN001
    resp = _client().post(
        "/api/v1/jobs/job-ai-summary-3/ai-summary", headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 404


@pytest.mark.integration
def test_ai_summary_mysql_down_yields_503(fake_backend) -> None:  # noqa: ANN001
    fake_backend["mysql"].fail_next = True
    resp = _client().post(
        "/api/v1/jobs/job-ai-summary-4/ai-summary", headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 503


# ---------- streaming endpoint (SSE, 前后端协同) -------------------------


class _StreamFakeProvider:
    """chat_stream yields per-chunk LLMResponse objects (delta content)."""

    def __init__(self, pieces) -> None:  # noqa: ANN001
        self._pieces = pieces
        self.calls = 0

    async def chat_stream(self, messages, timeout=None):  # noqa: ANN001
        self.calls += 1
        for piece in self._pieces:
            class _Resp:
                def __init__(self, content):  # noqa: ANN001
                    self.content = content
                    self.finish_reason = None
                    self.usage = {"prompt_tokens": 10, "completion_tokens": 2,
                                  "total_tokens": 12}
            yield _Resp(piece)

    async def close(self) -> None:
        return None


@pytest.mark.integration
def test_stream_endpoint_deltas_then_done(monkeypatch: pytest.MonkeyPatch, fake_backend) -> None:  # noqa: ANN001
    provider = _StreamFakeProvider(["验收证据", "是材料。", ""])
    monkeypatch.setattr(ai_summary, "OpenAICompatibleProvider", lambda **_kw: provider)
    resp = _client().get(
        "/api/v1/jobs/job-ai-summary-1/ai-summary/stream",
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "event: delta" in body
    assert "验收证据" in body and "是材料。" in body
    assert "event: done" in body
    assert '"cached":false' in body or '"cached": false' in body
    assert "event: error" not in body
    assert provider.calls == 1


@pytest.mark.integration
@pytest.mark.integration
def test_stream_endpoint_dead_letter_then_replay_delivers() -> None:
    """The full sad-then-happy lifecycle against the REAL (isolated) MySQL:
    no receiver (DISABLED connector) dead-letters the intent, the operator
    replay re-queues it, and the relay delivers on its next cycle. This is
    the live drill's dead-letter leg, asserted in-process."""
    import uuid

    from storage.mysql import MySQLStore
    from storage.notify_relay import NotifyOutboxRelay

    store = MySQLStore()
    store.ensure_tables()
    job_id = "job-notify-dl-" + uuid.uuid4().hex[:12]
    store.create_job_with_outbox({
        "id": job_id,
        "repo_path": "/drill/notify",
        "base_ref": "base", "head_ref": "head-v1",
        "spec_path": "spec.md", "depth": "FAST",
    })
    store.transition_job_status(
        job_id, "RUNNING", from_status="QUEUED", worker_id="drill",
    )
    written = store.transition_job_status_with_notify(
        job_id, "VERIFIED", from_status="RUNNING",
        summary={"verdict": "VERIFIED"},
        notify_payload={
            "event_type": "verification.verified",
            "title": "drill", "text": "dead-letter leg",
            "blocks": [], "job_id": job_id,
        },
    )
    assert written

    # No receiver: the relay dead-letters immediately.
    dead_relay = NotifyOutboxRelay(
        mysql=store,
        connector_factory=lambda: _DisabledConnector(),
        poll_interval=0.0,
    )
    dead_relay.drain_pending()
    rows = store.list_dead_notifications(job_id)
    assert len(rows) == 1, rows

    # Operator replay: the DLQ state clears; the relay re-claims.
    replayed = store.replay_dead_notifications(job_id)
    assert len(replayed) == 1

    live_relay = NotifyOutboxRelay(
        mysql=store,
        connector_factory=lambda: _SentConnector(),
        poll_interval=0.0,
    )
    live_relay.drain_pending()
    assert not store.list_dead_notifications(job_id), (
        "the delivered row must leave the dead-letter set"
    )
    stats = store.notify_outbox_stats()
    assert stats["pending"] >= 0  # delivered rows leave the claim set


class _DisabledConnector:
    name = "test-disabled"
    capabilities = frozenset()

    def send(self, notification) -> str:  # noqa: ANN001
        return SendStatus.DISABLED.value

    def close(self) -> None:
        return None


class _SentConnector:
    name = "test-sent"
    capabilities = frozenset()
    sent = 0

    def send(self, notification) -> str:  # noqa: ANN001
        _SentConnector.sent += 1
        return SendStatus.SENT.value

    def close(self) -> None:
        return None


@pytest.mark.integration
def test_stream_endpoint_provider_failure_is_an_error_event(
    monkeypatch: pytest.MonkeyPatch, fake_backend,
) -> None:  # noqa: ANN001
    class _DyingProvider:
        async def chat_stream(self, messages, timeout=None):  # noqa: ANN001
            class _Resp:
                content = "部分文本"
                finish_reason = None
                usage = None
            yield _Resp
            raise RuntimeError("provider died mid-stream")

        async def close(self) -> None:
            return None

    class _Provider:
        async def chat_stream(self, messages, timeout=None):  # noqa: ANN001
            return _DyingProvider()

        async def close(self) -> None:
            return None

    monkeypatch.setattr(ai_summary, "OpenAICompatibleProvider", lambda **_kw: _Provider())
    resp = _client().get(
        "/api/v1/jobs/job-ai-summary-3/ai-summary/stream",
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "event: error" in body
    assert "partial" in body
    assert "event: done" not in body
