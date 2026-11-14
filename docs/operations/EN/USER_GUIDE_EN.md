# SpecProof User Guide · 使用手册

> **中文版**: [USER_GUIDE.md](../USER_GUIDE.md) · This file is the English edition; the Chinese one is authoritative for the Chinese UI.

> Audience: **someone who just cloned the repository / wants to demo to an interviewer / wants the whole product surface in one page**.
> Reading order: §1 the five-minute "just do it", §2 the full experience path, §3 the complete module catalogue, §4 the Chinese/English switch.

---

## §1 · The five-minute path

### 1.1 In the door (no credentials needed)

```bash
git clone https://github.com/xiaodernan/specproof && cd specproof
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"    # Windows
cd apps/web && npm install && npm run build && cd ../..
pwsh scripts/start_local_light.ps1                              # zero-Docker mode also works
# or the full Docker mode:
docker compose -f compose.phase0.yml up -d --wait
```

### 1.2 A lap around the whole product (5 minutes)

Open `http://127.0.0.1:5173/` — the sidebar carries 16 first-level entries:

| Group | Entry | What you can do right now | Iron evidence |
|---|---|---|---|
| Workspace | Dashboard | Today's verification trails + unresolved BLOCKERs | — |
| Workspace | Verifications | The Jobs list; open any row for details | — |
| Workspace | AI Developer | Enter SpecCraft — let the AI write code and self-repair | LLM call + self-correction |
| Quality & Evidence | Requirement Coverage | requirement → contract_id → verdict matrix | real evidence |
| Quality & Evidence | Contracts | every contract's checker_type (http/sql/…) | — |
| Quality & Evidence | Effectiveness | real F1 / recall / precision from the 100-example golden set | 100 golden examples |
| Admin | Usage & Billing | real LLM token spend + cache hit rate | direct to wkapi.pro |
| Admin | Audit Trail | every audit_logs write in the chain | compliance |
| Admin | Model Connection | switch the real key of any OpenAI-compatible gateway | — |
| Admin | Service Status | health (mysql/redis/rabbitmq/minio) + latency distribution | — |
| — | Epic | six scrolls of SpecProof's genesis | full pixel-for-pixel real commits |
| — | Tour | interactive six-stamp corridor | the mother of all passovers |

> No `.env` needed either — the tour works without one. To connect a real LLM, ask for `.local/llm.json`.

### 1.3 The first real verification (10 minutes)

```bash
# the demo repo: pinned base vs the injected head-v1 (which deliberately removed @PreAuthorize)
specproof verify \
  --repo demo/spring-backend \
  --base base --head head-v1 \
  --spec demo/requirement.txt \
  --depth FAST --no-llm
```

Expected output:

```
Contracts compiled: 6
  [!] AUTH-01 (http) -> FAIL      ← the head dropped @PreAuthorize
  [+] UNIQUE-01 (sql) -> PASS
  [?] TOKEN_INVALIDATION-01 (redis) -> UNVERIFIED
  [+] BACKWARD_COMPATIBLE-01 (openapi) -> PASS
  [+] EVENT_ONCE-01 (rabbitmq) -> PASS
  [+] TRANSACTION-01 (sql) -> PASS
VERDICT: BLOCKED
```

That `AUTH-01 FAIL` is the pinned failing case. This product **never argues with AI by mouth — it measures**.

---

## §2 · The full experience path (20 minutes, in order)

### 2.1 `/ui-kit` — the whole Aurora component system

Open `/ui-kit` — no credentials needed; you will see Button, Breadcrumbs, Table, StatCard, StatusPill, Progress, Skeleton, Modal, Empty/Degraded, every token and colour family. That is what this product's design system looks like when it grows up.

> Tip: the source lives in `apps/web/src/ui/`; each `.tsx` has a story; `/ui-kit` is the live wall of mirrors.

### 2.2 `#/usage` — the LLM real-cost ledger

Switch to Cache Health — real wkapi.pro measurements, ~84% hit rate on a 2270-byte stable prefix.
> `hit_rate` is computed over `hit_basis_calls` (the calls the gateway actually reported for), **never** over `calls` — that is verified truth.

### 2.3 `#/tour` — the six-stamp corridor

**The mother of all passovers.** One seal per scroll; fill six and the red "SEALED" stamp lands.
> All progress stays in this browser's localStorage — a new browser starts the walk over.

### 2.4 `#/explorer` — the Case File

Every scroll has a Case File cover — repository / change / verdict / the iron list / stat cards + one blocked case. **There is not a single placeholder on it.**

### 2.5 `#/epic` — the Chronicles

Six scrolls, every anchor a real `git` commit hash — a verifiable epic. Anchors: #1645, #1668, #1672 are real. **The Chinese book runs 22.3KB**; the English edition mirrors it at `docs/world/EN/SPECROOF_WORLD_EN.md`.

### 2.6 `#/mcp` — tools for external AI agents

```bash
specproof mcp tools          # print the 7 tools
specproof mcp serve          # start the stdio MCP server
```
Wire the server into Claude Code / Codex — it can then call `specproof_verify` directly instead of "guessing whether there is an authorization regression".

### 2.7 Your own real LLM (needs `.local/llm.json`)

Copy `.local/llm.json.example` as-is; it already works:

```json
{
  "base_url": "https://wkapi.pro/v1",
  "api_key": "sk-your-key-here",
  "model": "gpt-6-sol",
  "protocol": "chat_completions"
}
```

```bash
# smoke test + endpoint probe
specproof probe --base-url https://wkapi.pro/v1 --model gpt-6-sol --api-key sk-yours
specproof verify --repo demo/spring-backend --base base --head head-v1 --spec demo/requirement.txt --depth FULL
```

> Expect: **the same BLOCKED as FAST mode** — the REAL GPT-6-sol reads the diff, explains the catch, and tokens land in `.local/llm_usage.jsonl`.
> Note on wkapi.pro: when it is saturated, `hit_rate` hovers around `75%–84%`; `cached_tokens` may intermittently come back null.

---

## §3 · The module catalogue (47-page application)

| Route | Module | One sentence |
|---|---|---|
| `/dashboard` | Dashboard | tasks, failures, 24h timeline, blocked delivery board |
| `/jobs` + `/jobs/:id` | Verifications | staged 5-step RED/GREEN evidence + capsule |
| `/jobs/new` | New Verification | repo/base/head/spec, FAST\|FULL dual depth |
| `/matrix` | Requirement Coverage | contract_id × evidence_type table |
| `/contracts` | Contracts | every contract listed + a plain-language explanation for non-experts |
| `/eval` | Effectiveness | F1/P/R category diagnostics + golden reference |
| `/billing` | Usage & Billing | real wkapi.pro token spend + hit_rate |
| `/audit` | Audit Trail | every audit_logs write, nothing dropped |
| `/health` | Service Status | 6-dependency latency distribution + 60 SLO alert triggers |
| `/settings` | Model Connection | switch any OpenAI-compatible gateway (DeepSeek / wkapi / custom / Azure / OpenAI) |
| `/mcp` | MCP Adapter | the tool catalogue + stdio for external AI agents |
| `/admin/identity` | Team & Access | RBAC, access control, audit |
| `/ui-kit` | Design System | the full Aurora component wall |
| `/epic` | Chronicles | bilingual genesis; every anchor a real commit hash |
| `/tour` | Grand Tour | interactive onboarding corridor; six stamps seal 「验讫」 |
| `/explorer` | Case File | iron-evidence binding — red seal 「验讫」 on the cover |
| `/lexicon` | Iron Lexicon | fourteen words, each searchable, each anchored to a real location |
| `/usage` | Cache Health | truthful hit_rate + billing chain |
| `/guide` | Onboarding Guide | from clone to your first BLOCKED in 4 steps |
| `/readme` | Recommended Reading | this repository's reader map |

---

## §4 · The Chinese / English switch (if the screen shows mixed languages)

The **language toggle** in the top bar (shows `EN` / `中`) switches at any time; the choice persists in this browser's `specproof_locale`; `<html lang>` is declared to screen readers accordingly (`en` / `zh-CN`). **Both are fully supported — no mixing.**

| Already **per-page** localised (switch freely; no Chinese prose residue) | Still **Chinese-native** (UI switches, page body not translated line-by-line) |
|---|---|
| All sidebar entries + groups + breadcrumbs + Dashboard (#1702) + Service Health (#1703) + Verifications (#1704) + Effectiveness (#1705) + Contracts (#1706) + Matrix (#1707) + Audit (#1708) + Billing (#1709) + Login (#1710) + New Verification (#1711) + Guide (#1712) + Model Connection (#1713) + Verification Detail (#1714) | **100% of legacy pages on tables**; shared UI dictionaries stay Chinese (pinned by PARITY gates, scheduled separately) |
| `/tour` — the six stations, fully bilingual (`pages/tour.copy.ts`) | |
| `/explorer` — lead, fields, stat cards, evidence list — all via the table | |
| `/usage` — title, window chips, six cards, the honesty basis sentence (with `{basis}` denominator), legend, empty-ledger copy | |
| `/epic` — the original Chinese scrolls + the English edition + a bilingual coda (`pages/epic.copy.ts`) | |
| `/lexicon` — all fourteen entries bilingual (term / gloss / iron / anchor) | |

**Native-English documents now have Chinese editions too**: `CLAUDE.md` (bilingual line-by-line, #1696), `ARCHITECT_CLAUDE.md` (bilingual, #1697); see also paired manuals like `MCP_GUIDE.zh.md`.

For the full English edition of *The Book of Iron Evidence*: `docs/world/EN/SPECROOF_WORLD_EN.md`.

---

## §5 · The five-minute "last temptation"

1. `#/tour` → fill all six stamps → watch the red 「验讫 / SEALED」 stamp land — this is you **personally** affixing the Acceptance Officer's seal to paper;
2. `#/explorer` → see someone else's BLOCKED in the Case File — when you read that red line you understand: someone else's code was caught, and the iron does not lie;
3. `docs/world/SPECROOF_WORLD.md` → scroll down to Scroll Two (the Review Court + the codebook), Scroll Four (the microservice host), Scroll Nine — every scroll bottom carries **real commit hashes** you can cross-check with `git log`;
4. `#/usage` → see hit_rate 75–84% ……………  this is why this product never talks about "LLM bandwidth", only about "verification efficiency".

---

## §6 · Honest limits

- This manual does not promise 100% itch-free software; verified and unverified boundaries are marked explicitly;
- the numbers here (hit_rate 75–84%, the real-machine FAST PASS path) come from real-machine measurements and the ledger `#1650–#1689`;
- the demo repository (demo/spring-backend) is the golden defect-injection baseline, **not your real PR**;
- when parameters are missing: **never** trust the AI's confident numbers — read the evidence, read the iron matrix, read the differential.
