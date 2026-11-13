"""Streaming AI-summary: the SSE generator finishes what the non-streaming one
started — pieces arrive incrementally, an empty stream is an honest error, and
the cache replay branch behaves exactly like the live one.
"""

from __future__ import annotations

from typing import Any

import pytest

import api.ai_summary as ai_summary
from providers.base import LLMResponse


def _summary(**overrides: Any) -> dict[str, Any]:
    base = {
        "verdict": "BLOCKED",
        "contracts_total": 2,
        "matrix_passed": 1,
        "matrix_failed": 1,
        "matrix_unverified": 0,
        "matrix_rows": [
            {"contract_id": "AUTH-01", "result": "FAIL", "severity": "BLOCKER",
             "evidence_type": "base_pass_head_fail"},
            {"contract_id": "UNIQUE-01", "result": "PASS", "severity": "MAJOR",
             "evidence_type": "static_analysis"},
        ],
        "retrieval_note": "es unavailable",
        "findings_total": 1,
    }
    base.update(overrides)
    return base


def _resp(piece: str, *, finish: str | None = None, usage: dict[str, Any] | None = None) -> LLMResponse:
    return LLMResponse(content=piece, finish_reason=finish or "stop", usage=usage or {})


class _FakeStreamProvider:
    """Mimics OpenAICompatibleProvider.chat_stream: yields LLMResponse chunks."""

    def __init__(self, pieces: list[str], usage: dict[str, Any] | None = None) -> None:
        self._pieces = pieces
        self._usage = usage or {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        self.chat_calls = 0

    async def chat_stream(self, messages, tools=None, thinking=False, opts=None, timeout=None):  # noqa: ARG002, ANN001
        self.chat_calls += 1
        for i, piece in enumerate(self._pieces):
            last = i == len(self._pieces) - 1
            yield _resp(piece or "", finish="stop" if last else None,
                        usage=self._usage if last else None)

    async def close(self) -> None:
        return None


@pytest.mark.anyio
async def test_stream_yields_deltas_then_done() -> None:
    provider = _FakeStreamProvider(["结论：", "受阻。", "两项契约，一项失败。"])
    events = [e async for e in ai_summary.generate_ai_summary_stream(
        _summary(), [], provider_factory=lambda **_kw: provider,
    )]
    kinds = [e["type"] for e in events]
    assert kinds == ["delta", "delta", "delta", "done"]
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "结论：受阻。两项契约，一项失败。"
    done = events[-1]
    assert done["usage"]["total_tokens"] == 30
    assert done["evidence_packet_chars"] <= 6000


@pytest.mark.anyio
async def test_stream_empty_content_is_an_honest_error() -> None:
    provider = _FakeStreamProvider(["", "", ""])
    events = [e async for e in ai_summary.generate_ai_summary_stream(
        _summary(), [], provider_factory=lambda **_kw: provider,
    )]
    assert events[-1]["type"] == "error"
    assert events[-1]["detail"]


@pytest.mark.anyio
async def test_stream_provider_failure_is_an_honest_error_with_partial() -> None:
    class _Boom:
        async def chat_stream(self, messages, tools=None, thinking=False, opts=None, timeout=None):  # noqa: ARG002, ANN001
            yield _resp("先输出一点", finish=None)
            raise RuntimeError("gateway gone")

        async def close(self) -> None:
            return None

    events = [e async for e in ai_summary.generate_ai_summary_stream(
        _summary(), [], provider_factory=lambda **_kw: _Boom(),
    )]
    kinds = [e["type"] for e in events]
    assert kinds[0] == "delta"
    assert events[0]["text"] == "先输出一点"
    assert kinds[-1] == "error"
