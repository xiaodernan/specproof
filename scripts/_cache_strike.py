import asyncio
import io, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from providers.config import load_model_config
from providers.openai_compatible import OpenAICompatibleProvider
from providers.base import LLMMessage

async def main():
    cfg = load_model_config()
    print("source", cfg["source"], "| protocol", cfg["protocol"], "| model", cfg["model"])
    for i in range(1, 5):
        provider = OpenAICompatibleProvider(
            api_key=cfg["api_key"], base_url=cfg["base_url"], model=cfg["model"],
            protocol=cfg["protocol"], reasoning_effort=cfg.get("reasoning_effort"),
        )
        resp = await provider.chat(
            [LLMMessage(role="user", content="你是谁？用一句话回答。")],
            timeout=60.0,
        )
        u = resp.usage
        print(f"strike {i}: prompt={u.get('prompt_tokens')} hit={u.get('prompt_cache_hit_tokens')} miss={u.get('prompt_cache_miss_tokens')} (details={u.get('prompt_tokens_details')})")
        print(f"   reply: {(resp.content or '')[:80]}")
    print("live invoke (HTTP 200, cache cached_tokens) via direct stream check:")
    import subprocess
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "live_lane_probe.py")],
        capture_output=True, text=True, timeout=60,
        encoding="utf-8", errors="replace",
    )
    print(out.stdout, out.stderr)

asyncio.run(main())
