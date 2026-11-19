#!/usr/bin/env python
"""Bilingual consistency probe — does gpt-6-sol give the same verdict in zh and en?

SpecProof's i18n layer promises: one question asked in either language gets the
same iron answer. This probe asks the *model* the same question twice, once in
Chinese and once in English, and reports whether the answers agree. It is an
**observational** probe — never a gate. A disagreement is a finding about the
upstream gateway, not about any code in this repository.

Reuses the same model config every other LLM consumer in this repo uses
(providers.config.load_model_config), same rail: stream=True + include_usage.
Never prints the API key.

Usage:
    python scripts/llm_locale_consistency.py [--json]
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime

from providers.config import load_model_config

ZH_PROMPT = (
    "你是铁证验收官。下面是一条线上发现（finding）：一个 Spring 服务方法的 "
    "@PreAuthorize 注解在新提交里被删除，未认证请求从此可以直达。"
    "请仅用一个词或极短短语告诉我：这次事故在验收上属于哪个严重度档位？"
    "只答 BLOCKER、MAJOR、MINOR 之一。"
)
EN_PROMPT = (
    "You are an acceptance officer. Here is one production finding: a Spring "
    "controller method lost its @PreAuthorize annotation in the new commit, so "
    "unauthenticated requests can now reach it directly."
    "Answer with exactly one word — BLOCKER, MAJOR or MINOR — which acceptance "
    "severity tier does this finding belong to?"
)


async def ask(client, model: str, prompt: str) -> dict:
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            stream=True,
            stream_options={"include_usage": True},
        )
    except Exception as exc:  # noqa: BLE001 - the probe must report, not die
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    chunks, usage = [], None
    async for chunk in resp:
        if chunk.usage:
            usage = chunk.usage
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        delta = getattr(choices[0], "delta", None)
        if delta is not None and getattr(delta, "content", None):
            chunks.append(delta.content)
    text = "".join(chunks).strip()
    cached = None
    details = getattr(usage, "prompt_tokens_details", None) if usage else None
    if details is not None:
        cached = getattr(details, "cached_tokens", None)
    return {
        "ok": True,
        "text": text,
        "prompt_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
        "completion_tokens": getattr(usage, "completion_tokens", None) if usage else None,
        "cached_tokens": cached,
    }


def normalize(text: str) -> str:
    t = text.upper()
    for word in ("BLOCKER", "MAJOR", "MINOR"):
        if word in t:
            return word
    if "阻断" in text or "严重" in text or "高危" in text:
        return "BLOCKER"
    return "UNRESOLVED:" + text[:40]


async def main() -> int:
    parser = argparse.ArgumentParser(description="zh/en consistency probe against the configured LLM gateway.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        cfg = load_model_config()
    except Exception as exc:  # noqa: BLE001
        print(f"model config unreadable: {exc}")
        return 2

    from openai import AsyncOpenAI

    from providers.responses_protocol import normalize_base_url

    client = AsyncOpenAI(
        api_key=cfg["api_key"],
        base_url=normalize_base_url(cfg["base_url"]),
        max_retries=1,
        timeout=60.0,
    )

    started = datetime.now(UTC).isoformat()
    zh = await ask(client, cfg["model"], ZH_PROMPT)
    en = await ask(client, cfg["model"], EN_PROMPT)

    zh_pick, en_pick = normalize(zh.get("text", "")), normalize(en.get("text", ""))
    agree = zh_pick == en_pick and not zh_pick.startswith("UNRESOLVED")

    report = {
        "started_utc": started,
        "model": cfg["model"],
        "base_url": cfg["base_url"],
        "zh": zh, "en": en,
        "zh_pick": zh_pick, "en_pick": en_pick,
        "agree": agree,
        "verdict": "CONSISTENT" if agree else "DIVERGENT (observational, not a gate failure)",
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("== bilingual consistency probe ==")
        for lang in ("zh", "en"):
            r = report[lang]
            if r.get("ok"):
                print(f"[{lang}] pick={report[lang + '_pick']:8s} text={r['text'][:60]!r} "
                      f"prompt={r['prompt_tokens']} cached={r['cached_tokens']}")
            else:
                print(f"[{lang}] ERROR {r['error']}")
        print(f"\nverdict: {report['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
