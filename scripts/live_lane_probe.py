#!/usr/bin/env python
"""live_lane_probe — one minimal call to the configured LLM lane.

Reads `.local/llm.json` (or LLM_* env) via the project's own config code path,
issues ONE minimal streaming SSE call (`stream=True`, `include_usage=True`),
and prints:

  - HTTP status, chunk count, elapsed ms
  - the `usage` object the provider ACTUALLY returns (not what it should)
  - whether third-party promotional links appear in the body
  - whether `cached_tokens` appears in usage (honest report)

The api_key is NEVER printed or written anywhere. Cost: ~1 small call to the
configured endpoint. Not a load test; run it once if you need to re-verify
the lane; do NOT run in CI.
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from providers.config import load_model_config  # noqa: E402
from providers.net import (  # noqa: E402
    outbound_client,  # noqa: E402  (env-proxy mounts; bare httpx misroutes through the Clash Verge egress)
)

cfg = load_model_config()
print("source", cfg["source"], "| protocol", cfg["protocol"], "| model", cfg["model"], "| base_url", cfg["base_url"])

url = cfg["base_url"].rstrip("/") + "/chat/completions"
headers = {"Authorization": f"Bearer {cfg['api_key']}", "Accept": "text/event-stream"}
body = {
    "model": cfg["model"],
    "messages": [{"role": "user", "content": "用一句话确认：铁证不伪造。回答不超过 12 个汉字。"}],
    "temperature": 0,
    "max_tokens": 24,
    "stream": True,
    "stream_options": {"include_usage": True},
}

timer_start = time.monotonic()
chunks = 0
text_parts: list[str] = []
usage = None
try:
    with outbound_client(timeout=60) as client, client.stream("POST", url, json=body, headers=headers) as resp:
        if resp.status_code != 200:
            print("HTTP", resp.status_code)
            print(resp.read().decode("utf-8", errors="replace")[:500])
            raise SystemExit(1)
        for line in resp.iter_lines():
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                obj = json.loads(payload)
            except ValueError:
                continue
            chunks += 1
            if obj.get("usage"):
                usage = obj["usage"]
            piece = (obj.get("choices") or [{}])[0].get("delta", {}).get("content")
            if piece:
                text_parts.append(piece)
except Exception as exc:
    print("PROBE_ERROR:", type(exc).__name__, str(exc)[:200])
    raise SystemExit(1) from exc

elapsed_ms = round((time.monotonic() - timer_start) * 1000, 1)
print(f"HTTP 200 | chunks {chunks} | {elapsed_ms} ms")
print("reply:", "".join(text_parts).strip()[:120])
print("usage:", json.dumps(usage, ensure_ascii=False))
if usage and "cached_tokens" in str(usage):
    print("cached_tokens field present ✅")
else:
    print("cached_tokens field NOT present ❌ ('prefix-cached' or available-not-reported)")
links = re.findall(r"https?://[^\s)\]]+|utm_[a-z]+=[^\s)\]]+", "".join(text_parts))
if links:
    print("⚠️  third-party/ad links in reply:", links)
else:
    print("no third-party links in reply ✅")
print("done — no key material on this page, ever.")
