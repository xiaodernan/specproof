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


---

## Addendum · 2026-11-18T06:46Z (post-#1995) — all-green re-strike, recorded verbatim

The two earlier sections above are left untouched: they record the 94.9 % strike of 2026-11-18 morning and the byte-frozen bodies at that moment (zh 413,655 B · en 424,582 B — **now drifted, see below**). This addendum is additive, never a rewrite.

**Bible bodies as of commit `ab1e676` (scroll #196 landed)** — the codex prefix is byte-frozen *per commit*, not forever; every scroll append re-freezes the bodies:

| body | bytes | sha256 |
|---|---|---|
| `docs/world/SPECROOF_WORLD.md` (zh) | 469,057 | `0bd35e34381ffab492165feb8cac3f09b40d9cbabc3464ea67095e7749374d6d` |
| `docs/world/EN/SPECROOF_WORLD_EN.md` (en) | 480,233 | `1bb97b727de286ca211231fa81a1b7a1af951c6ae4b45e01e29c7dba5ee42917` |

**This addendum's strike** (`scripts/lane_cache_probe.py` · protocol=`responses` · `stream=True` · `include_usage=True` · gateway was briefly flaky; see honesty note below):

| lane | strike | prompt | cached | hit |
|---|---|---|---|---|
| observe | #1 cold | 158,210 | 7,533 | 4.8 % |
| observe | #2 warm | 158,210 | **148,644** | **94.0 %** |
| insight | #1 cold | 157,822 | 7,515 | 4.8 % |
| insight | #2 warm | 157,822 | **148,264** | **93.9 %** |
| ai_summary | #1 cold | 157,808 | 7,514 | 4.8 % |
| ai_summary | #2 warm | 157,808 | **148,265** | **94.0 %** |
| dig · explorer | #1 cold | 138,415 | 6,591 | 4.8 % |
| dig · tester | #1 warm | 137,781 | 129,431 | 93.9 % |
| dig · security | #1 warm | 136,718 | 128,420 | 93.9 % |
| dig · explorer | #2 warm | 138,415 | 129,936 | 93.9 % |
| dig · tester | #2 cold | 137,781 | 6,561 | 4.8 % |
| dig · security | #2 warm | 136,718 | 128,420 | 93.9 % |
| runbook · explorer | #1 cold | 139,902 | 6,662 | 4.8 % |
| runbook · tester | #1 cold | 139,267 | 6,631 | 4.8 % |
| runbook · security | #1 cold | 138,205 | 6,581 | 4.8 % |
| runbook · explorer | #2 warm | 139,902 | 131,454 | 94.0 % |
| runbook · tester | #2 warm | 139,267 | 130,821 | 93.9 % |
| runbook · security | #2 warm | 138,205 | 129,810 | 93.9 % |

Mechanics unchanged: ~7,500-token frozen skeleton (4.8 % floor), one sticky `prompt_cache_key` per lane, ~94 % when warm. dig rotates warm/cold *per agent prefix* (tester and explorer swapped slots between strikes; security held). runbook opened cold across all three agents (en key first-written) and landed 93.9–94.0 % on the second strike.

**Honesty notes added this round:**

1. A same-command strike immediately before this one saw the six `observe` / `insight` / `ai_summary` calls turned away by the gateway with 「模型暂时不可用」 (model temporarily unavailable — no verdict, no usage accountable, dig/runbook survived). That run is not in the table above; it is recorded here and in the session terminal log; nothing was manufactured from it.
2. The 4.8 % cold-floor repeat across every lane on every first strike of the day is compositional (frozen prefix), not a cache bug.
3. Evidence JSON for this addendum: `docs/evidence/lane-cache-probe-2026-11-18.json` (generated `2026-11-18T06:46:43+00:00`; the earlier failed merge was superseded by this all-green write, and the failure is disclosed in this addendum, not deleted from history).
4. Court `4117d2b0ca5fb23a` untouched — no `prompt_cache_key`, no codex, ever; not struck in this probe, not struck in any probe.
