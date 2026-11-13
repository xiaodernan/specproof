"""chat() now rides the streaming endpoint and every call's cache evidence is
visible to the ledger.

WHY THIS FILE EXISTS. The gateway's prompt-caching works on identical
prefixes (measured against wkapi.pro with a long stable system prompt:
17.3s cold → 2.8s warm, 5376 cached tokens in usage). Two facts meant the
product's own accounting never saw any of it:

1. Every pipeline call went out as a non-streaming chat completion, so the
   gateway dashboard reported the whole product as 非流.
2. ``_parse_usage`` only read the DeepSeek-style ``prompt_cache_hit_tokens``
   field. This gateway (and OpenAI itself) reports the cached share under
   ``prompt_tokens_details.cached_tokens`` — which the ledger dropped on
   the floor. The cache hits were invisible to token-budget accounting.

These legs pin the repair:

* ``chat()`` sends ``stream=True`` with ``include_usage`` and AGGREGATES the
  stream back into the one-response contract every caller already expects
  (content, reasoning, tool calls, finish reason, usage);
* the aggregated response reports ``prompt_cache_hit_tokens`` from the
  OpenAI-style field, so billing accounts cache hits at the cache-hit
  weight instead of full price;
* a DeepSeek-style gateway that reports its own field is not overridden;
* the aggregated response with tool calls keeps them whole, across chunk
  boundaries.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from providers import openai_compatible as mod
from providers.base import LLMMessage, LLMResponse

_API_KEY = "sk-" + "test-" + "key"


class _ChunkStream:
    def __init__(self, items: list[Any]) -> None:
        self._items = list(items)
        self._index = 0

    def __aiter__(self) -> _ChunkStream:
        return self

    async def __anext__(self) -> Any:
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        if isinstance(item, BaseException):
            raise item
        return item


class _Completions:
    def __init__(self, chunks: list[Any]) -> None:
        self.calls: list[dict[str, Any]] = []
        self._chunks = chunks

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(dict(kwargs))
        assert kwargs.get("stream") is True, (
            "chat() must request streaming from the gateway"
        )
        assert kwargs.get("stream_options") == {"include_usage": True}, (
            "chat() must ask the gateway to report usage on the final chunk"
        )
        return _ChunkStream(self._chunks)


class _FakeClient:
    def __init__(self, chunks: list[Any]) -> None:
        self.chat = SimpleNamespace(completions=_Completions(chunks))

    async def close(self) -> None:
        pass


def _provider(chunks: list[Any]) -> mod.OpenAICompatibleProvider:
    provider = mod.OpenAICompatibleProvider(
        base_url="http://llm.test/v1",
        api_key=_API_KEY,
        model="test-model",
    )
    provider._client = _FakeClient(chunks)  # type: ignore[assignment]
    return provider


def _chunk(content=None, reasoning=None, tool_calls=None, finish_reason=None,
           usage=None, model="test-model") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    content=content,
                    reasoning_content=reasoning,
                    tool_calls=tool_calls,
                ),
                finish_reason=finish_reason,
            )
        ] if usage is None else [],
        usage=usage,
        model=model,
    )


def _usage(prompt_tokens=100, cached=None) -> SimpleNamespace:
    details = SimpleNamespace(
        cached_tokens=cached, cache_write_tokens=None,
        reasoning_tokens=None, audio_tokens=None,
        image_tokens=None, text_tokens=None,
    )
    return SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=25,
        total_tokens=prompt_tokens + 25,
        completion_tokens_details=None,
        prompt_tokens_details=details if cached is not None else None,
    )


@pytest.mark.asyncio
async def test_chat_streams_and_aggregates_into_one_response() -> None:
    chunks = [
        _chunk(content="Hello"),
        _chunk(content=" world"),
        _chunk(finish_reason="stop", usage=_usage(cached=41),
               model="test-model"),
    ]
    provider = _provider(chunks)
    resp = await provider.chat(messages=[LLMMessage(role="user", content="hi")])
    assert isinstance(resp, LLMResponse)
    assert resp.content == "Hello world"
    assert resp.finish_reason == "stop"
    assert resp.model == "test-model"


@pytest.mark.asyncio
async def test_cached_tokens_from_openai_style_details_reach_the_usage() -> None:
    chunks = [
        _chunk(content="ok"),
        _chunk(finish_reason="stop", usage=_usage(cached=5376)),
    ]
    provider = _provider(chunks)
    resp = await provider.chat(messages=[LLMMessage(role="user", content="hi")])
    assert resp.usage["prompt_cache_hit_tokens"] == 5376


@pytest.mark.asyncio
async def test_deepseek_native_cache_field_wins_over_openai_details() -> None:
    usage = _usage(cached=5376) if False else SimpleNamespace(
        prompt_tokens=100,
        completion_tokens=25,
        total_tokens=125,
        prompt_cache_hit_tokens=80,
        prompt_cache_miss_tokens=40,
        completion_tokens_details=None,
        prompt_tokens_details=SimpleNamespace(
            cached_tokens=5376, cache_write_tokens=None, reasoning_tokens=None,
            audio_tokens=None, image_tokens=None, text_tokens=None,
        ),
    )
    chunks = [
        _chunk(content="ok"),
        _chunk(finish_reason="stop", usage=usage),
    ]
    provider = _provider(chunks)
    resp = await provider.chat(messages=[LLMMessage(role="user", content="hi")])
    assert resp.usage["prompt_cache_hit_tokens"] == 80
    assert resp.usage["prompt_cache_miss_tokens"] == 40


@pytest.mark.asyncio
async def test_tool_calls_are_accumulated_across_chunks() -> None:
    def tc(index: int, id_: str | None, name: str | None, args: str | None) -> SimpleNamespace:
        return SimpleNamespace(
            index=index,
            id=id_,
            type="function",
            function=SimpleNamespace(name=name, arguments=args),
        )

    chunks = [
        _chunk(tool_calls=[tc(0, "call_42", "get_weather", '{"cit')]),
        _chunk(tool_calls=[tc(0, None, None, 'y": "Par')]),
        _chunk(tool_calls=[tc(0, None, None, 'is"}')]),
        _chunk(finish_reason="tool_calls", usage=_usage(cached=10)),
    ]
    provider = _provider(chunks)
    resp = await provider.chat(
        messages=[LLMMessage(role="user", content="hi")],
        tools=[{
            "type": "function",
            "function": {"name": "get_weather", "parameters": {}},
        }],
    )
    assert len(resp.tool_calls) == 1
    call = resp.tool_calls[0]
    assert call["id"] == "call_42"
    assert call["function"]["name"] == "get_weather"
    assert call["function"]["arguments"] == '{"city": "Paris"}'
    assert resp.usage["prompt_cache_hit_tokens"] == 10


@pytest.mark.asyncio
async def test_empty_stream_still_refuses_like_a_dead_gateway() -> None:
    provider = _provider([])
    with pytest.raises(RuntimeError, match="no text or tool calls"):
        await provider.chat(messages=[LLMMessage(role="user", content="hi")])
