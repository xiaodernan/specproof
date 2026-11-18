"""Stress digest — the model reads the weekly-stress strike and says what it means.

The weekly-stress workflow measures the front door three times a week and
archives bare numbers: p50/p90/p95/p99, err_rate, bytes, and a machine verdict
on a 5000 ms sanity floor. Numbers nobody reads are decoration. This lane is
the reader:

* packet is derived from the committed evidence file at call time —
  ``docs/evidence/weekly-*.json`` — never an invented figure;
* the model may describe the reading and name at most three next actions;
  it may NOT rule on anything — court vocabulary is out of bounds here as in
  every public lane, and the packet is not a ledger entry;
* offline the digest is rendered deterministically (no network): a rounds
  table, the floor comparison as a fact, and the honesty line verbatim;
* live strikes spend zh/en against the configured lane with the byte-frozen
  codex prefix, ``prompt_cache_key=specproof-stress-digest``,
  ``stream=True`` + ``include_usage=True`` — same shape as every other lane;
* on any honest failure: one ``StressDigestUnavailable`` — never a simulated
  paragraph.
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from api.system_codex import codex_first
from api.system_covenant import covenant_prefix
from providers.base import LLMMessage, LLMResponse
from providers.openai_compatible import OpenAICompatibleProvider

logger = logging.getLogger(__name__)

LLM_TIMEOUT_SECONDS = 150.0

_ROOT = Path(__file__).resolve().parents[1]
_EVIDENCE_DIR = _ROOT / "docs" / "evidence"
FLOOR_MS = 5000  # the weekly-stress machine sanity floor; a fact, not an SLO


class StressDigestUnavailable(Exception):
    """The model could not read the evidence honestly right now."""


def latest_evidence(path: str | Path | None = None) -> Path | None:
    """Resolve the evidence file: explicit arg, env override, or newest weekly-*.json."""
    if path:
        p = Path(path)
        return p if p.is_file() else None
    env_path = os.environ.get("SPECPROOF_STRESS_EVIDENCE")
    if env_path:
        p = Path(env_path)
        return p if p.is_file() else None
    candidates = [
        p for p in _EVIDENCE_DIR.glob("weekly-*.json")
        if "digest" not in p.name
    ]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def build_stress_packet(path: str | Path | None = None) -> dict[str, Any]:
    evidence = latest_evidence(path)
    if evidence is None:
        return {
            "evidence_file": None,
            "error": "no weekly evidence file found under docs/evidence/weekly-*.json",
            "floor_ms": FLOOR_MS,
        }
    raw = evidence.read_text(encoding="utf-8")
    d = json.loads(raw)
    rounds = []
    for r in d.get("rounds", []):
        rounds.append({
            "total": r.get("total"),
            "ok": r.get("ok"),
            "err_rate": r.get("err_rate"),
            "p50_ms": r.get("p50_ms"),
            "p90_ms": r.get("p90_ms"),
            "p95_ms": r.get("p95_ms"),
            "p99_ms": r.get("p99_ms"),
            "max_ms": r.get("max_ms"),
            "avg_ms": r.get("avg_ms"),
            "bytes_read": r.get("bytes_read"),
        })
    p99s = [float(r["p99_ms"]) for r in rounds if r.get("p99_ms") is not None]
    worst = max(p99s) if p99s else None
    best = min(p99s) if p99s else None
    if worst is None:
        floor_comparison = "unknown"
    elif worst > FLOOR_MS:
        floor_comparison = "over"
    elif worst == FLOOR_MS:
        floor_comparison = "at"
    else:
        floor_comparison = "under"
    return {
        "evidence_file": evidence.name,
        "generated_from": "committed evidence, newest by mtime unless SPECPROOF_STRESS_EVIDENCE/path is set",
        "started_utc": d.get("started_utc"),
        "note": d.get("note"),
        "concurrency": d.get("concurrency"),
        "per_thread": d.get("per_thread"),
        "warmup_rounds": d.get("warmup_rounds"),
        "rounds": rounds,
        "worst_p99_ms": worst,
        "best_p99_ms": best,
        "err_rate_any": any(float(r.get("err_rate") or 0.0) > 0.0 for r in rounds),
        "floor_ms": FLOOR_MS,
        "floor_comparison": floor_comparison,
        "packet_verdict_echo": d.get("verdict"),  # echoed verbatim, never re-graded
        "honesty": d.get("honesty"),
        "packet_bytes": len(raw.encode("utf-8")),
    }


def fingerprint(locale: str) -> str:
    packet = json.dumps(
        {"packet": build_stress_packet(), "locale": "en" if locale == "en" else "zh"},
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(packet.encode("utf-8")).hexdigest()


_PROMPT_ZH = (
    "你是 SpecProof 周压测读数员——读数，不裁判。\n"
    "下面这份 JSON 包是某次周压测的真数字（出自仓里的 docs/evidence/weekly-*.json）：\n"
    "rounds[].p99_ms / p95_ms / avg_ms / err_rate、concurrency、worst_p99_ms、floor_ms（固定 5000，机器级地板，不是 SLO）。\n"
    "用中文写一段不超过 240 字，规则：\n"
    "1）先引包里的数字——至少引用 3 个（worst_p99_ms、某一轮的 err_rate、p95 或 avg），逐字写，不许换算不许编造；\n"
    "2）然后读出这轮数据的形状——干净（err_rate 全 0）还是有伤（任一轮 err_rate>0）、p99 离 floor_ms 还有多远；\n"
    "3）最后给最多 3 个“下一步该做什么”，每一条必须落在包里的数字或现象上；包里没有的依据就直说「包里没有这个证据」；\n"
    "4）不许用“通过／未通过／批准／阻断／放行”等词；可以说“这轮数据说明……”；\n"
    "5）纯文本，不写 Markdown 标题，不写时间戳/人名/邮箱/URL。\n"
    "只输出这段回答。"
)

_PROMPT_EN = (
    "You are the readings-officer of the SpecProof weekly stress strike — you read, you never rule.\n"
    "The JSON below is one real weekly-stress measurement, straight from docs/evidence/weekly-*.json:\n"
    "rounds[].p99_ms / p95_ms / avg_ms / err_rate, concurrency, worst_p99_ms, floor_ms (fixed 5000; a machine floor, not an SLO).\n"
    "Write one English paragraph, at most 140 words, hard rules:\n"
    "1) Quote at least 3 numbers from the packet verbatim — e.g. worst_p99_ms, some round's err_rate, p95 or avg; no re-computed or invented figures;\n"
    "2) Then read the shape of the strike — clean (all err_rate 0) or wounded (any err_rate>0) — and how much headroom sits between worst_p99_ms and floor_ms;\n"
    "3) Then at most 3 next actions, each grounded in a number present in the packet; if the packet cannot support one, say “the packet carries no evidence for that”;\n"
    "4) Never use approved / blocked / passed / failed vocabulary — write “this strike's numbers say …”;\n"
    "5) Plain text, no Markdown headings, no timestamps/people/emails/URLs.\n"
    "Output only the answer."
)


def _prompt(locale: str, packet: str) -> list[LLMMessage]:
    lang = "en" if locale == "en" else "zh"
    system = _PROMPT_EN if lang == "en" else _PROMPT_ZH
    return codex_first(covenant_prefix([
        LLMMessage(role="system", content=system),
        LLMMessage(
            role="user",
            content=("数据包（JSON）：\n" if lang == "zh" else "Packet (JSON):\n") + packet,
        ),
    ]), lang)


async def generate_stress_digest(
    locale: str,
    *,
    provider_factory: Callable[..., OpenAICompatibleProvider] | None = None,
) -> dict[str, Any]:
    """Call the model; raise StressDigestUnavailable on any honest failure."""
    if provider_factory is None:
        provider_factory = OpenAICompatibleProvider
    packet_obj = build_stress_packet()
    if packet_obj.get("error"):
        raise StressDigestUnavailable(
            "没有找到本周压力测试的证据文件（docs/evidence/weekly-*.json）。\n"
            "跑一次 scripts/stress_smoke.py 再来。"
            if locale != "en"
            else "No weekly stress evidence file found (docs/evidence/weekly-*.json). "
                 "Strike the stress script once before asking for a reading."
        )
    packet = json.dumps(packet_obj, ensure_ascii=False, sort_keys=True)
    provider: OpenAICompatibleProvider | None = None
    started = time.perf_counter()
    try:
        provider = provider_factory(timeout=LLM_TIMEOUT_SECONDS, max_retries=1)
        response: LLMResponse = await asyncio.wait_for(
            provider.chat(
                _prompt(locale, packet),
                timeout=LLM_TIMEOUT_SECONDS,
                opts={"prompt_cache_key": "specproof-stress-digest"},
            ),
            timeout=LLM_TIMEOUT_SECONDS + 5,
        )
    except Exception as exc:  # noqa: BLE001 - any provider failure becomes one honest error
        logger.info("stress-digest provider failure: %s", type(exc).__name__)
        raise StressDigestUnavailable(
            "模型暂时不可用，无法读出这份压测证据。稍后再试，或直接读表格。"
            if locale != "en"
            else "The model is unavailable right now; no reading of this strike. "
                 "Read the rounds table yourself."
        ) from exc
    finally:
        if provider is not None:
            with contextlib.suppress(Exception):
                await provider.close()
    text = (response.content or "").strip()
    if not text:
        raise StressDigestUnavailable(
            "模型返回了空读法。与其误导你，这里什么都不显示。"
            if locale != "en"
            else "The model returned an empty reading. Nothing is shown rather than mislead."
        )
    return {
        "digest": text,
        "model": response.model or None,
        "model_latency_ms": round((time.perf_counter() - started) * 1000),
        "usage": response.usage,
        "evidence_packet_chars": len(packet),
        "evidence_file": packet_obj.get("evidence_file"),
    }


def offline_reading(packet: dict[str, Any]) -> list[str]:
    """Deterministic, no network, and honest about being a table reading."""
    lines: list[str] = []
    if packet.get("error"):
        return [f"- {packet['error']}"]
    if packet["err_rate_any"]:
        lines.append("- Errors occurred in at least one round — this strike was not clean; investigate before shipping, not via a label.")
    else:
        lines.append("- Every round finished with err_rate 0 — the static lane delivered, byte after byte.")
    worst = packet["worst_p99_ms"]
    if worst is None:
        lines.append("- No p99 figures in the packet — nothing can be said about tail latency.")
    elif packet["floor_comparison"] == "over":
        lines.append(
            f"- worst_p99_ms = {worst:.1f} is OVER the {FLOOR_MS} ms machine floor — on this host the floor is information to act on, not a scoreboard."
        )
    else:
        headroom = FLOOR_MS - worst
        lines.append(f"- worst_p99_ms = {worst:.1f}, which sits {headroom:.1f} ms UNDER the {FLOOR_MS} ms machine floor on this host.")
    lines.append(f"- honest note from the strike, verbatim: “{packet.get('honesty')}”")
    return lines


def render_digest_md(
    packet: dict[str, Any],
    *,
    reading_zh: str | None = None,
    reading_en: str | None = None,
    mode: str,
) -> str:
    rows = []
    for i, r in enumerate(packet.get("rounds", []), 1):
        rows.append(
            f"| {i} | {r.get('err_rate')} | {r.get('p99_ms')} | {r.get('p95_ms')} | "
            f"{r.get('avg_ms')} | {r.get('total')}/{r.get('ok')} | {r.get('bytes_read')} |"
        )
    out = [
        "# Weekly stress digest · the strike, read aloud",
        "",
        f"- mode: {mode}",
        f"- evidence: {packet.get('evidence_file')} (packet {packet.get('packet_bytes')} bytes)",
        f"- started_utc: {packet.get('started_utc')} · concurrency={packet.get('concurrency')} · per_thread={packet.get('per_thread')} · warmup_rounds={packet.get('warmup_rounds')}",
        f"- note from the strike: {packet.get('note')}",
        f"- floor_ms: {FLOOR_MS} (machine sanity floor — not an SLO, not a verdict on this repo)",
        f"- floor_comparison: {packet.get('floor_comparison')} · worst_p99_ms={packet.get('worst_p99_ms')} · best_p99_ms={packet.get('best_p99_ms')}",
        f"- the strike's machine label, verbatim (never re-graded): {packet.get('packet_verdict_echo')}",
        "",
        "## Rounds",
        "",
        "| round | err_rate | p99_ms | p95_ms | avg_ms | total/ok | bytes |",
        "|---|---|---|---|---|---|---|",
        *rows,
        "",
        "## The reading (offline, deterministic)",
        "",
        *offline_reading(packet),
    ]
    if reading_zh:
        out += ["", "## The model's reading (zh)", "", reading_zh]
    if reading_en:
        out += ["", "## The model's reading (en)", "", reading_en]
    out += [
        "",
        "*This is a reading of one strike on one host. It is never a release decision; the court is never in this room.*",
    ]
    return "\n".join(out) + "\n"


def digest_stamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
