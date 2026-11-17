# Lane Cache Probe — 2026-11-18 (live aizzz/gpt-6.1-terra via Clash Verge · 127.0.0.1:7897)

**Setup that finally rings the cache bell:** the ~410 KB world-book bible rides the cacheable lanes as one byte-identical system message (`api/system_codex.py` · codex → covenant → role, identical order everywhere), each lane passes a sticky `prompt_cache_key` (≤ 64 chars, never randomized), `reasoning_effort` untouched per lane policy, `store=false` (unchanged), court never carries either. Code lines this ledger entry rides on: #1977.

**Codex bodies (byte-frozen at commit time):**

| body | bytes | sha256 |
|---|---|---|
| `docs/world/SPECROOF_WORLD.md` (zh) | 413,655 | `fe2aee36db601acd2db33c11188cad81700af5281dac585e4a0e146d72cdf771` |
| `docs/world/EN/SPECROOF_WORLD_EN.md` (en) | 424,582 | `9fc608a718305fe91b8c3d79e2353b7f8d504aad5400aa5bbe261033c4262894` |

**Raw sanity** (`scripts/codex_cache_sanity.py` · en codex · `reasoning_effort=low` · key `specproof-probe-sanity`):

| strike | elapsed | prompt | cached | miss | output |
|---|---|---|---|---|---|
| 1 | 12.47 s | 117,801 | 0 (write) | 117,801 | 7 tok |
| 2 | 5.03 s | 117,801 | **111,742 (94.8 %)** | 6,059 | 7 tok |

**Lane probes** (two consecutive strikes of the real lane code path; the prefix is byte-identical within a strike pair):

| lane | locale · effort | prompt (1st) | cached 2nd | hit ratio | key |
|---|---|---|---|---|---|
| `/observe` advice | zh · max | 136,514 | **129,495** | **94.9 %** | `specproof-observe-advice` |
| `/insight` advice | zh · max | 136,144 | **129,129** | **94.9 %** | `specproof-insight-advice` |
| `/ai-summary` | zh · max | 136,132 | **129,130** (94.9 %) | `specproof-ai-summary` |
| `/dig` (3 agents) | en · low | ~118 K each | 224,705 → **338,027** across runs | ~75 → **~95 %** | `specproof-dig` |
| `/runbook` (3 agents) | en · low | ~118 K each | 0 (write) → **342,517** | 0 → **~96 %** | `specproof-runbook` |

Going cold (first-ever strike per key) always reads `cached=0` — the key is being *written*, not failing. Repeat strikes stabilize at ~95 %. A third, fully-warm pass of `/observe` showed `cached=129,495` on **both** strikes (13.8 s / 11.5 s).

**Honest boundaries, in writing:**

1. `/dig`'s first probe probe (before `ParallelRunner` was taught to preserve `AgentRunResult.usage`) reported `cache_hit_tokens` blind — the hit was likely there, invisible. After the fix (`craft/agents.py` stamps `usage` through), hits are visible and recorded above — do not read them as a pre-fix success.
2. The probe packet is a synthetic, labeled `PROBE`-shaped tenant (`scripts/lane_cache_probe.py`) — these strikes measure cache mechanics, not any product verdict; no gate values were minted or altered.
3. `cached` here refers to prefix tokens served by the gateway's cache (`input_tokens_details.cached_tokens` → mapped through `providers/responses_protocol.usage_data`). Outputs/reasoning tokens are never cached.
4. Courts (`agent/review_court/`) were never struck, never keyed, never codex'd — `tests/unit/test_system_codex.py` pins that; the court lock `4117d2b0ca5fb23a` is unchanged.
5. The gateway is a black box: if `reasoning_effort=max` output cost shifts, the cache math above is unaffected, but latency on cold strikes is paid once per key per 24 h window.
6. The merged `lane-cache-probe-2026-11-18.json` holds the post-warm rows (latest two strikes per lane); the cold numbers quoted here were observed in the same session and are written down above verbatim — no row was manufactured.

**What changed to make this real** (the four-line summary): `api/system_codex.py` (byte-frozen bible prefix) · lane wirings (`codex_first` + sticky key at every cacheable call site) · `ParallelRunner` preserves `usage` · per-lane timeout 45 s → 150 s (45 s predates the 135 K-token prompt era).

— evidence kept beside the world · not a verdict · not beautified · committed as-struck
