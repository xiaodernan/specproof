"""next_step_advice — the book reads its own numbers, never ruling.

Mirror of test_observe_advice.py: env-less packet checks, codex-first
sandwich assertions, provider_factory stubs. No tokens are spent here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.next_step_advice import (
    NextStepAdviceError,
    build_next_step_packet,
    fingerprint,
    generate_next_step_advice,
)
from providers.base import LLMResponse


def test_packet_is_deterministic_and_bounded() -> None:
    p1 = build_next_step_packet()
    p2 = build_next_step_packet()
    assert p1 == p2
    assert set(p1) == {
        "commits",
        "ledger_sections",
        "repository_files",
        "lines_of_code",
        "worldbooks_volumes",
        "library_zh_en_pairs",
        "chronicle_entries",
        "unit_test_files",
        "court_lock",
    }
    assert p1["court_lock"] == "4117d2b0ca5fb23a"
    assert all(isinstance(v, (int, str)) for v in p1.values())


def test_packet_numbers_match_the_tree() -> None:
    p = build_next_step_packet()
    assert p["commits"] and p["commits"] > 2000
    assert p["ledger_sections"] and p["ledger_sections"] > 1500
    assert p["worldbooks_volumes"] == 206  # scroll 206 (#2078-2095 real facts), bilingual
    # Derived, not hardcoded: commit 5146c6c rebuilt the chronicle to 1833 and
    # left this pin at 1799, turning a data refresh into a red gate. Read the
    # same JSON the packet builder reads so the next rebuild cannot rot it.
    chronicle = json.loads(
        (Path(__file__).resolve().parents[2] / "apps/web/src/pages/chronicle.json").read_text(
            encoding="utf-8"
        )
    )
    assert p["chronicle_entries"] == len(chronicle)
    assert p["library_zh_en_pairs"] == 205  # scroll 206 library chapter (#2078-2095)
    assert p["unit_test_files"] and p["unit_test_files"] > 500


def test_fingerprint_is_stable_and_locale_sensitive() -> None:
    assert fingerprint("zh") == fingerprint("zh")
    assert fingerprint("zh") != fingerprint("en")
    assert len(fingerprint("zh")) == 64


def test_prompt_sandwich_carries_codex_then_covenant_then_lane() -> None:
    import api.next_step_advice as mod

    zh = mod._prompt("zh", json.dumps(build_next_step_packet(), sort_keys=True))
    en = mod._prompt("en", json.dumps(build_next_step_packet(), sort_keys=True))
    for msgs in (zh, en):
        assert [m.role for m in msgs] == ["system", "system", "system", "user"]
    assert zh[0].content.startswith("以下不是虚构")
    assert en[0].content.startswith("The following is not fiction")
    assert zh[1].content == en[1].content  # the covenant is byte-identical both languages


class _FakeProvider:
    def __init__(self, **_: object) -> None:
        pass

    async def chat(self, _messages, timeout: float | None = None, opts: dict | None = None):  # noqa: ANN001
        return LLMResponse(
            content="LIVE-READING: the ledger reads 1,799 · worldbook 204 · library 203 — not a verdict.",
            usage={"prompt_tokens": 169_000, "completion_tokens": 95},
            model="gpt-6.1-terra",
        )

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_live_path_returns_the_model_read() -> None:
    result = await generate_next_step_advice("zh", provider_factory=lambda timeout, max_retries: _FakeProvider())
    assert "LIVE-READING" in result["advice"]
    assert result["model"] == "gpt-6.1-terra"
    assert result["usage"]["prompt_tokens"] == 169_000
    # the packet rides inside the user message only, never into system-adjacent verdict tokens
    assert result["evidence_packet_chars"] > 40


class _Boom:
    def __init__(self, **_: object) -> None:
        pass

    async def chat(self, *_args, **_kwargs):  # noqa: ANN001
        raise RuntimeError("forced refusal")

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_provider_failure_raises_one_honest_exception() -> None:
    with pytest.raises(NextStepAdviceError):
        await generate_next_step_advice("en", provider_factory=lambda timeout, max_retries: _Boom())


class _Empty:
    def __init__(self, **_: object) -> None:
        pass

    async def chat(self, *_args, **_kwargs):  # noqa: ANN001
        return LLMResponse(content="", usage={"prompt_tokens": 10}, model="gpt-6.1-terra")

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_empty_model_answer_is_refused() -> None:
    with pytest.raises(NextStepAdviceError):
        await generate_next_step_advice("zh", provider_factory=lambda timeout, max_retries: _Empty())
