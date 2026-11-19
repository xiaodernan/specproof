"""The exhibit copilot (#1978): the machine signs its own wall.

Sealed here, not somewhere else:

* an in-bounds, packet-provenance answer (every number in it is in the
  packet) seals HELD;
* one invented number seals DRIFTED — even a single stray digit;
* over-length outputs seal DRIFTED (the ceiling is a hard contract);
* markdown headings or an off-beat banned word seals DRIFTED;
* empty text seals DRIFTED;
* a wrong ``\n\n``-split seals DRIFTED;
* the copilot system-prompt bytes are pinned — one byte moved and it DRIFTS.
"""
from __future__ import annotations

import re

import api.exhibit_copilot as mod

FIXTURE_PACKET = {
    "exhibits_count": 18,
    "latest_file": "2026-11-17-static-warm-18.json",
    "started_utc": "2026-11-17T15:27:40.402187+00:00",
    "concurrency": 96,
    "total_requests": 768,
    "total_ok": 768,
    "worst_p99_ms": 2027.103,
    "avg_p95_ms": 1552.606,
    "vs_file": "2026-11-17-static-warm-17.json",
    "worst_p99_delta_ms": 492.643,
    "note": "static lane, 3 entry assets, fresh server on 127.0.0.1",
}

GOOD_ZH = (
    "这一波风压试没有翻车：96 个并发、768 次请求、0 错误，最慢一波停在 2027.103 毫秒的山腰上。"
    "它与上一件展品的距离是实实在在的负载差，不是退化——只是完整测试在门口喊了一声。"
    "先读 p99 的曲线，再读 p95 与分差，最后再看 0 错误本身。"
)
GOOD = GOOD_ZH + "\n\n" + (
    "This strike carried 96 concurrent lanes, 768 requests, and zero errors; "
    "the slowest rounded down at 2027.103 ms. Against the previous exhibit the "
    "p99 distance is load difference, not regression — the full pytest suite was at the door. "
    "Read the p99 curve first, then p95's valley, then zero errors."
)


def test_the_good_answer_seals() -> None:
    ok, failures = mod.validate_copilot(GOOD, FIXTURE_PACKET)
    assert ok, failures
    assert mod.validate_copilot(GOOD_ZH + "\n\n" + GOOD_ZH, FIXTURE_PACKET)[0] is True


def test_one_invented_digit_seals_drifted() -> None:
    answer = GOOD.replace("2027.103", "1739")
    ok, failures = mod.validate_copilot(answer, FIXTURE_PACKET)
    assert not ok
    assert any("1739" in f for f in failures)


def test_over_length_seals_drifted() -> None:
    answer = GOOD_ZH + "\n\n" + ("word " * 200 + "end")
    ok, failures = mod.validate_copilot(answer, FIXTURE_PACKET)
    assert not ok


def test_markdown_headings_seal_drifted() -> None:
    ok, failures = mod.validate_copilot(GOOD + "\n\n## appendix", FIXTURE_PACKET)
    assert not ok
    assert any("markdown marker" in f for f in failures)


def test_banned_words_seal_drifted() -> None:
    for banned in mod._BANNED:
        if banned in GOOD:
            continue
        answer = GOOD + "\n\n" + banned
        ok, failures = mod.validate_copilot(answer, FIXTURE_PACKET)
        assert not ok, banned


def test_empty_seals_drifted() -> None:
    ok, failures = mod.validate_copilot("", FIXTURE_PACKET)
    assert not ok
    assert failures == ["empty"]


def test_paragraph_count_is_a_hard_contract() -> None:
    ok, failures = mod.validate_copilot("one breath of truth", FIXTURE_PACKET)
    assert not ok


def test_the_prompt_bytes_are_pinned() -> None:
    import hashlib

    assert hashlib.sha256(mod.EXHIBIT_COPILOT_SYSTEM.encode("utf-8")).hexdigest() == mod.PIN_SHA256
    # a single-byte serif on the prompt flips the pin; the guarantee is the pin itself
    tampered = mod.EXHIBIT_COPILOT_SYSTEM + "。"
    assert hashlib.sha256(tampered.encode("utf-8")).hexdigest() != mod.PIN_SHA256


def test_numbers_extraction_reports_every_number() -> None:
    text = "0 · 96 · 768 · 2027.103 · 492.643"
    assert re.findall(r"\d+(?:\.\d+)?", text) == ["0", "96", "768", "2027.103", "492.643"]


def test_every_fixture_number_is_in_packet() -> None:
    source = mod._packet_text(FIXTURE_PACKET)
    for number in ("18", "96", "768", "2027.103", "492.643"):
        assert number in source
