"""问世界书 —— the question is the only client input, the book is the only truth,
and nothing ever minted by the model becomes a verdict. Nothing in this module
touches the network."""

from __future__ import annotations

import pytest

from api.worldbook_ask import (
    WorldbookAskUnavailable,
    build_ask_messages,
    fingerprint,
    generate_ask_answer,
)
from providers.base import LLMResponse


def test_question_is_sanitized_and_bounded() -> None:
    from api.worldbook_ask import MAX_QUESTION_CHARS, _sanitize_question

    out = _sanitize_question("  你好， 世界？\r\nxyz  ")
    # nothing non-printable passes through
    assert "\r" not in out and "\n" not in out
    # no leading/trailing whitespace
    assert not out.startswith(" ") and not out.endswith(" ")
    # no run of spaces
    assert "  " not in out
    # contains the words, intact
    assert "你好" in out and "世界" in out and "xyz" in out
    # hard ceiling
    assert len(_sanitize_question("a" * (MAX_QUESTION_CHARS * 3))) == MAX_QUESTION_CHARS


def test_fingerprint_is_stable_and_locale_and_question_sensitive() -> None:
    assert fingerprint("zh", "你好世界") == fingerprint("zh", "你好世界")
    assert fingerprint("zh", "你好世界") != fingerprint("en", "你好世界")
    assert fingerprint("zh", "你好世界") != fingerprint("zh", "你好 world")
    assert len(fingerprint("zh", "你好世界")) == 64


def test_messages_are_locale_bounded_and_pin_no_verdict_vocabulary() -> None:
    zh = build_ask_messages("zh", "世界书从哪一卷开始？")
    en = build_ask_messages("en", "where does the world book begin?")
    # codex-first means the bible rides ahead of the system message
    zh_text = "\n".join(getattr(m, "content", "") for m in zh)
    en_text = "\n".join(getattr(m, "content", "") for m in en)
    # the bible is present (byte-frozen codex) in front of the question
    assert "SPECTRUM" not in en_text  # placeholder sanity — real codex has no MAGIC
    assert "你好世界" not in en_text
    assert "起源" in zh_text or "这本书" in zh_text
    assert "world book" in en_text or "bible" in en_text
    # the system message forbids verdicts explicitly
    assert "裁决" in zh_text
    assert "verdict" in en_text.lower()


class _FakeProvider:
    def __init__(self, **_: object) -> None:  # noqa: ANN003
        pass

    async def chat(self, _messages, timeout: float | None = None, opts: dict | None = None, **kwargs):  # noqa: ANN001
        return LLMResponse(
            content="LIVE-ANSWER: 书里说第零卷就是一切的开始。不是 verdict。",
            usage={"prompt_tokens": 700, "completion_tokens": 50},
            model="gpt-6.1-terra",
        )

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_live_answer_path_returns_protocol_object() -> None:
    result = await generate_ask_answer(
        "世界书从哪一卷开始？",
        "zh",
        provider_factory=lambda timeout, max_retries: _FakeProvider(),
    )
    assert result["answer"].startswith("LIVE-ANSWER")
    assert result["model"] == "gpt-6.1-terra"
    assert result["model_latency_ms"] >= 0
    assert result["question_chars"] > 0


@pytest.mark.asyncio
async def test_provider_failure_is_one_honest_error() -> None:
    def boom(*_: object, **__: object):  # noqa: ANN001
        raise RuntimeError("provider unreachable")

    with pytest.raises(WorldbookAskUnavailable):
        await generate_ask_answer("你好", "zh", provider_factory=boom)


@pytest.mark.asyncio
async def test_empty_answer_is_one_honest_error() -> None:
    class _EmptyProvider(_FakeProvider):
        async def chat(self, _messages, timeout: float | None = None, opts: dict | None = None, **kwargs):  # noqa: ANN001
            return LLMResponse(content="   ", model="gpt-6.1-terra")

    with pytest.raises(WorldbookAskUnavailable):
        await generate_ask_answer(
            "你好",
            "zh",
            provider_factory=lambda timeout, max_retries: _EmptyProvider(),
        )


@pytest.mark.asyncio
async def test_blank_question_is_rejected_before_the_provider_is_touched() -> None:
    def boom(_: object):  # noqa: ANN001,ARG001
        raise AssertionError("provider must not be called for a blank question")

    with pytest.raises(ValueError):
        await generate_ask_answer("   ", "zh", provider_factory=boom)
