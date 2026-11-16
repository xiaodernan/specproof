# SpecProof — the code change acceptance firewall

> **中文版**: [README.md](./README.md) · This file is the English edition; the Chinese README is authoritative for Chinese readers.

SpecProof does two things: **it lets AI modify code on demand, and it independently checks whether the change actually respects the demand.**

## Newcomers start here · 5 minutes

| Read this / enter here | For whom |
|---|---|
| [`docs/operations/USER_GUIDE.md`](docs/operations/USER_GUIDE.md) (Chinese) · [`EN/USER_GUIDE_EN.md`](docs/operations/EN/USER_GUIDE_EN.md) (English) | From clone to your first `VERDICT: BLOCKED` |
| [`docs/operations/TOUR_MANUAL.md`](docs/operations/TOUR_MANUAL.md) | To play 「巡览 · The Grand Tour」 |
| [`docs/operations/MCP_GUIDE.zh.md`](docs/operations/MCP_GUIDE.zh.md) · [`MCP_GUIDE.md`](docs/operations/MCP_GUIDE.md) | To wire an AI agent into the verification pipeline |
| Frontend at `http://127.0.0.1:5173/` (after `npm run build`) | To walk the product — sidebar: 巡览 / 史诗 / 铁证词典 |

> The **EN / 中** language toggle switches the whole UI (English / Chinese — never mixed); the choice lives in this browser's `specproof_locale`.

- **AI Development**: describe the requirement → model plans the changes → you approve → files are edited, checks run → you review the diff.
- **Change Verification**: point at a Git repository, base version, head version, and requirement file → run the available checks → see coverage, risk, and evidence.

Spec is the requirement; Proof is the evidence that proves it. For teams that must review AI-written code, chase regressions, and keep delivery records.

## Getting started

Requires Python 3.12+, Node.js 18+, and Docker Desktop (optional).

```powershell
python --version            # at least 3.12+ (Windows python may be an alias)
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
pwsh scripts/start_local.ps1
```

> If `python --version` prints something else, use `py -3.12 -m venv .venv` or `uv venv --python 3.12`. The repository only accepts syntax/features supported by 3.12+; in practice it treats 3.13 as fine to target.

### Fastest path, no Docker needed

Light mode needs only Python 3.12 and Node 18+; onboarding takes about 30 seconds.

```powershell
pwsh scripts/start_local_light.ps1
```

Light mode stores small amounts of data in `.local/*.sqlite3`; nothing touches Docker. Some paths —— the new AI delivery entry, model provider configuration & the epic prologue —— require Java/Spring, RabbitMQ + a worker, full tenant read-write and approvals, and are only complete in full mode.

Open the [local app](http://localhost:5173); no credentials are required, and the start script prints a default demo key `specproof-local-demo-key` (usable only on this machine).

> If a local DB is polluted, the Worker/API in front of it often holds file locks; display/record issues in the UI usually come from that — change the data, then use `pwsh scripts/start_local.ps1 -Restart`; to stop, use `pwsh scripts/stop_local.ps1`.

## Setting up a real model

Open **Model connection**; enter a base URL for your model provider and a key for the model you can really use.

| Setting | Value | Status |
|---|---|---|
| Model URL | `https://api.aizzz.xyz/v1` | live (HTTP 200 · 9 chunks · 3.7 s · via Clash Verge 127.0.0.1:7897) |
| Model | `gpt-6.1-terra` | live |
| Protocol | Responses API | live (stream=True + include_usage=True) |
| Reasoning effort | `max` | live |
| Note | Direct TLS is region-blocked — the lane must ride the host's Clash Verge (mihomo, 127.0.0.1:7897); without the ladder every probe stays red | fact · R14 |

The API key lives in `.local/llm.json` (outside version control); never commit it. Alternatively, set `LLM_BASE_URL / LLM_API_KEY / LLM_MODEL / LLM_PROTOCOL / LLM_REASONING_EFFORT`; model connection succeeds only when it reports a real successful call. Save/usage without a configured model is shown clearly — as "waiting for the model to recover", not as failure.

> After changing model connection settings, press **Test connection** to confirm the provider answers for real. If the test fails, re-check it; each attempt's scope is shown explicitly.

## Recommended tour

| You want to | Do this | Why |
|---|---|---|
| See the product | Onboarding guide | Step-by-step; it tells you which verifications can be run, which cannot |
| Release a real fixed bug with AI | AI Development → New verification | Runs the real loop from requirement to a verified change |
| Check a bug report | Change verification → New verification | repo, base/head, requirement file path |
| Check task status | Verifications / Audit trail / Findings | real-time run/failures, queue, evidence |
| Configure the environment | Model connection / Service status | switch gateways, check dependencies and health |
| Sign up for a workspace | Team & access / Billing | multi-tenant storage and read-only quotas |

> Every place the onboarding guide says "check" is a real check — not inference, not fabricated records. It prints "Unknown" and "Cannot be determined" exactly as such; "Cannot be determined" is never softened into "Unknown".

The built-in entry point:

```text
a change to double quotes
requirement: the calculator must always return a number
spec: calc.py test_calc.py
```

AI development executes in the current directory and modifies code directly; the base/head range defines the comparison range. The execution diff is listed here; the merged result is only applied after you confirm.

## Verdict semantics

- `VERIFIED` (≥ 0 missing): real executable evidence produced it and it passed.
- `BLOCKED` (≥ 1 missing): risk was found — evidence is mismatched, coverage wrong — see the findings and the evidence.
- `NEEDS_REVIEW` (≥ 3 missing): rows are insufficient and marked as such — it cannot be claimed either way; a human must judge.
- `FAILED` (≥ 2 missing): execution crashed; it may be a valid fix, it is not conclusive.
- Row-level `UNVERIFIED`: every unverified row is shown, stub claims are not laundered into PASS. It is not a verdict either — it says the requirement lacks enough evidence, and it cannot be used to claim a pass.

The `specproof verify` exit code distinguishes these. Row-level `UNVERIFIED` is a separate claim: that requirement lacks sufficient evidence — it is not a verdict, but it equally **cannot** be used to say the requirement is satisfied.

Verification selects the **original source of truth**. Its own execution lanes:

| Language | Executable source | Lane |
|---|---|---|
| Java/Maven | yes, from the repository checkout | Docker sandbox（root can write; cannot escape /work） |
| JavaScript/TypeScript | yes, `npm test` (Jest/Vitest/node:test), with the existing lockfile-assessed `node_modules`; never reinstalls; the first pass from a clean npm cache fails `ENOTCACHED`, which must NOT be read as "check failed" — without network access one must provide a seeded cache (`pwsh scripts/seed_npm_cache.ps1 -RepoPath <repo>`) | Docker sandbox (`node:22-alpine`, uid 1000, `--network none`; source writable only into cached `node_modules` dirs) |
| Python/pytest | yes, pytest with the existing venv; no reinstalls; with only a pip wheelhouse seeded (`pwsh scripts/seed_pip_wheelhouse.ps1 -RepoPath <repo>`), but no network, reinstall failure must not be read as "check failed" either — one must actually have the wheels | Docker sandbox (`python:3.12-slim`, uid 1000, `--network none`; source writable only into `.venv`) |
| Java/Gradle | yes, from the existing real Gradle test suite | Docker sandbox with pinned digest `gradle:8.10-jdk21@sha256:963d59f7f22767da4efbcf46b661361b61af5fb88b0309da1071c4234c647eba` (image inspected 2026-11-09; digest self-checks in `test_declared_image_digests_match_the_local_images`) |
| Go/go | yes, `go test -json ./...`; its verdict is the only source-of-truth for Go checks | Docker sandbox with `GOPROXY=off` and a read-only module cache; **CGO modules are out of scope** (alpine cannot produce the C ABI; the sandbox dies instead of faking a pass) |

**Any deployment targets a Java/Spring repository.** Without dependencies available, Java sources and resource files fail preflight compilation; then non-targets are not executed. But the rest will still fail in the background if it cannot produce a trustworthy verdict — the sandbox cannot be claimed to have run tests it cannot run. When unsure, say "not tested" — do not claim verification.

Execution surfaces shown explicitly: `docker_sandbox` / `local_host_no_sandbox` / `unconfirmed`; **unconfirmed means unknown to the reader**. The differential column on the Matrix page shows base/head verdicts per row; unconfirmed surfaces are highlighted in red HTML as "differential unconfirmed". **The online differential is usually NOT this-is-it** — it must be an actually executed differential, otherwise it cannot be claimed and never runs the comparison either.

Craft (the AI pipeline) prints its acceptance summary on the execution result page too — not only in a database column and the CLI output: verdict, gate details, linked findings and the merge-certificate path all come from the persisted `accept_json`. Two things must be said clearly:

- **"No acceptance run yet" and "acceptance run unreadable" are two different languages**: while the task has not reached its terminal state, the page says acceptance has not run yet; while it has reached a terminal state but no summary landed, it also prints "verdict is missing — try `specproof craft accept --job <id>`"; when the record exists but cannot be parsed, it says plainly that "unreadable ≠ not accepted".
- **Craft's `BLOCKED` has two meanings, and the page distinguishes them by `gates.overall`**: when an internal gate FAIL is set, it shows failure; when every gate summary passed but the full closure (SpecProof verification + certificate + signature) still needs git base/head and a signing key and the accept CLI is pending, it shows a warning that "a merge certificate has not been issued yet", not failure. When the projection carries no gate summaries at all, the page says it **cannot tell why** — it does not guess.

## What's new on the record · 2026-11-16

- **Model door re-hung**: `https://api.aizzz.xyz` · model `gpt-6.1-terra` · Responses API · reasoning effort `max`; `.local/llm.json` is this host's untracked config (git-ignored); no key ever enters git; the gateway requires streams (`stream_required`) — all answer lanes in this repo are streams anyway; `scripts/live_lane_probe.py` strikes HTTP 200 / chunks 9 / `cached_tokens: 4224` consistently; court is always `stream=True + include_usage=True` and court is never cached.
- **The Clash Verge egress this host runs** (mihomo @ 127.0.0.1:7897) is the precondition for every model lane exercised on this machine.
- **provider smoke is green** (through the proxy): probe → chat → JSON (5 fields) · JUnit (7 schema checks) · Maven compile exit 0 · secret scan · digest chain; report `artifacts/p0.5/provider-smoke-20261116T070508Z/` (git-ignored).
- **137/137 lane green**: `mvn -o test` gateway 84 · discovery 1 · config 1 · control-plane 51 — off-line fixtures; UI **570/570** · exhibit_entries=**16** (latest struck: exhibit #15, 384c · err **4.43 / 2.34 / 4.30 / 4.04%** · worst p99 **2,061.0 ms** · verdict BUDGET-BLOWN — non-monotone tonight: 192c at 64–70%, 256c at 34–45%, 384c at 2–4%; recorded as-is).
- **Exhibit #12**: 512c on this host · rounds 1–2 **100% err** · worst p99 **10,049.2 ms** · verdict **BUDGET-BLOWN** · all thirteen exhibits struck live · `/exhibits` page shows reserved #4 (1,526.1 ms forever) · Night Watch still **CRACKED** · saturation curve is in-page and reads straight from `evidence.json`.
- **Night Watch composite StateGraph** (`agent/graphs/night_watch_graph.py`): evidence∩purity∩audit on one spine · verdict→report→END · currently **CRACKED** (exhibit #4 p99 1,526ms vs exhibit #3 1,030ms · Δ=+495.99ms > 25ms rule; the graph strikes itself; the exhibit stays on file; exhibit #5 = 1,035ms OK).
- **UI 570/570** (Exhibits Hall · /exhibits timeline with 24→512c saturation curve incl. **192c · exhibit #13**, **48c · exhibit #14** and **384c · exhibit #15** · /stategraph seven living graphs · engine page rebuilt to the real 63-row ledger · R17 on file · Insight AI Advice on a live model strike · guide sync · routerSmoke bomb-verified).
- **The door that does not fall** (#1944): `tests/unit/test_rate_limit_fixed_window.py` pins the rate limiter into a regression gate — `SPECPROOF_RATE_LIMIT_PER_MIN` defaults to 5/min · `specproof:rl:<sha256(key)[:16]>:<window>` · incr → count==1 → expire(90) · over the limit ⇒ **429 RATE_LIMITED** · bucket down ⇒ admitted (fail-open stays as a declared stance, not a bug) · 32 consecutive wrong keys → all **401**, zero 5xx — brute-force storms produce nothing exploitable. The 28 MySQL-backed test files did not run this session (Docker was down at the time — recorded as-is, no MySQL faked). UI **571/571** · mvn -o **137/137** · Scroll CL filed bilingual.
- **Three red doors open** (#1945): ROADMAP-LIVE item #8's four design-system gates cracked open tonight — 4 px grid 601→0 · font scale 406→0 · radii ladder 101→0 · shadow gate 71→0 · **1,165 theme-blind literal colours remain on file** (each awaiting its semantic token — a separate remediation pass) · UI **571/571** · mvn -o **137/137** · Scroll CLI filed bilingual.
- **The red door moves half a foot more** (#1946): the theme-blind colour gate re-struck from **1,165 down to 593** (1,165→1,154→950→944→898→775→666→593, every step read off `pytest …::test_no_painted_color_bypasses_the_theme_tokens` directly) · **14** never-`var()`-referenced dead tokens removed (deleted only after a zero-reference sweep + zero test-string hits) · **tokens.css drifted twice tonight** (declarations floating outside `:root`; the `@media print` annotation torn in half) — the house now requires **both passes (lite + minified)** before a CSS change may enter the index · UI **571/571** · build ✓ · mvn -o **137/137** (gateway 84 + control-plane 51 re-struck in this process) · Scroll CLII filed bilingual.
- **Every door is open** (#1947): theme-blind colours **593→0** — 593 studio pigments registered **byte-for-byte** (**463** new `--pigment-*` tokens: one pigment · one token · zero value drift; **13** more re-bound to context-invariant tokens, the `--print-*` lane never reused) · `test_no_painted_color_bypasses_the_theme_tokens` **3/3 green** · the whole design-system family is now green on master (4 px grid 601→0 · radii ladder 101→0 · font scale 406→0 · shadows 71→0 · theme-blind colours **1,315→0**) · Atlas doorplate now `EST. Nº 130` · `lightningcss.transform` **42/42 OK** · UI **571/571** · build ✓ · mvn -o **137/137** · Scroll CLIII filed bilingual.
- **One ledger, two measures** (#1948): the cache account split along **lane × protocol** (`by_lane`: direct **0.5418** / policy **0.0** — R16 with machine backing · `by_protocol`: all historic rows honestly bucket `(unreported)` until new rows land) · **+3 honesty tests · 20/20 green** · Usage panel gains **"Lane × protocol · same cache account"** · court still locked (never cached) — the "non-stream" pill can only surface on the court lane by law · Scroll CLIV filed bilingual.
- **The coarse measure, made honest** (#1949): `scripts/i18n_audit.py` upgraded — new bucket C (same-line `L()`/`zh ?`/`{ zh: }`/`…_ZH` coordinated bilinguals, **1,172** reclassed) · bucket A **366→196→138** · noise only down, nothing reclassified as fine · the audit stays exit 0 forever, never a CI gate · Scroll CLV filed bilingual.


- **Insight AI Advice** (#1936): the Insight Deck gained "AI Advice — what the data says next" — admin/operator asks aizzz/gpt-6.1-terra to read this panel's anonymous aggregates; first strike 2026-11-16 (packet 730 B · latency 17,032 ms · the model quoted verbatim 201→113 tour drop-off and 84→41 first-to-accept, and volunteered "insufficient data" on onboarding_routes=0) · RBAC unchanged (admin/operator · "password-123" vetoed) · failure = one honest 503, never fabricated text · tests/unit **10/10** · UI **570/570** · Scroll CXLIV filed bilingual.
- **craft×aizzz, struck end-to-end** (#1937): a free-form Chinese requirement ("fix the logic error in `double`") → plan.mode=**llm** · four Chinese steps · the model itself wrote `x * 2` (no fix_registry, nobody told it) · LOOP_RESULT=**DONE** · acceptance gate **BLOCKED** (this host's Docker python cache carries no pytest — `No module named pytest` — not a code defect) · the door never opened and the patch was rolled back to base, exactly as designed · cached 4224 struck on the second call · evidence: `docs/evidence/2026-11-16-llm-craft-strike.md` · Scroll CXLV filed bilingual.
- **The sandbox bites pytest** (#1938): until today the python gate answered `No module named pytest` forever — **two independent causes** (slim image; a bare command that could never see the wheelhouse). The three-phase composite is on file: in effective docker mode `python -m pytest` ⇒ `venv → pip install --no-index --find-links /wheelhouse pytest` (+`-r requirements.txt`) → pytest · local dev mode byte-identical · wheelhouse seeded with pytest 9.2.0 (offline smoke green) · **the acceptance gate went green for the first time** (run_test **PASS 155 s** · run_build 40 s) → SpecProof **REJECTED** (Java/Maven-first: `No pom.xml found`) — recorded, not smoothed · no threshold moved · Insight AI advice joined the role-parity gate (11/11) · 25/25 runner assertions · evidence: `docs/evidence/2026-11-16-llm-craft-strike-2.md` · Scroll CXLVI filed bilingual.
- **Just struck today**: ✅ **OBSERVABILITY.md signed** (D1 · 2026-11-16 · owner endorsement · signature recorded in `OBSERVABILITY.md` §9 — identity unverified per `scripts/audit_unsigned.py`); **still owed**: **PORTFOLIO_TOKEN** (D2 — your PAT · Settings → Secrets). One of those two is signed today; the other waits for your hand.
- Boundary: no rack-booted deployment of this system has happened anywhere; nothing here is dressed for a production ceremony.

## Notable verifications

2026-09-23 — **the JavaScript/TypeScript "repository-self-carried differential" ran in a real sandbox** (temporary node:test repo: green exits 0, broken exits 1; uid 1000, `--network none`, `/work` read-only). It also repaired a defect affecting usability: **the "requirement coverage" page was empty for real verifications** — the per-row matrix (including base-pass / head-fail differential attribution) used to persist only counts, never the rows; it now lands with the task summary and flows to the UI, and one round-trip test pins producer to consumer. **Honest limit (2026-09-25 update)**: the Node sandbox can now do **offline dependency installs** for lockfile repositories (#56: dependencies only come from a pre-seeded npm cache volume, `scripts/seed_npm_cache.ps1`); seeded repos pass offline — unseeded packages fail `ENOTCACHED`, don't run, and are honestly judged "unreproducible". Zero-dependency repositories behave exactly as before.

2026-09-18 — ordinary replies from the specified gateway and model, streamed text, JSON, and tool-call/tool-result continuation all pass. The web Test-connection probe passes. In a standalone Python test repo, the real model wrote a 3-step plan in Chinese, and after approval changed `return x / 2` to `return x * 2` with the tests unchanged — tests and type checking pass; the build check is marked skipped for lack of build configuration. It proves the chain exists — not that every project can finish automatically.

See [the maintenance record](docs/operations/PRODUCT_REFRESH_2026-09-18.md). The original baselines, architecture diagrams and capability claims are kept in [the historical technical record](docs/operations/TECHNICAL_CAPABILITIES_HISTORY.md) — do not read either as the current release's SLA.

## Architecture sketch

Frontend is `apps/web` (React / TypeScript / Vite); API lives in `api/`; the AI loop lives in `craft/`; verification lives in `agent/`; storage lives in `storage/`; providers live in `providers/`.

```powershell
# run the web tests
cd apps/web
npm run build
# run the new-verification tests
npm run test -- src/pages/NewVerification.test.tsx
# the repository root setup, from inside the unit tests
.venv/Scripts/python -m pytest tests/unit/test_product_setup.py
# the project CI gate runs the full unit suite excluding 3 background lanes and integration lanes
.venv/Scripts/python -m pytest tests/unit -m "not integration and not slow" -q
```

The quick suite is only a **developer convenience**, not a release criterion: the merge gate in CI still runs `pytest tests/unit tests/security tests/fault` bare — the ~275 cases excluding `slow` are not excluded.

**Pushes require SSH, not HTTPS.** `git@github.com:xiaodernan/specproof.git` — OAuth tokens lack `workflow` scope, so any push touching `.github/workflows/*.yml` is refused by GitHub (`refusing to allow an OAuth App to create or update workflow ... without 'workflow' scope`). SSH key auth remains valid and does not touch OAuth at all:

```powershell
git remote set-url origin git@github.com:xiaodernan/specproof.git
```

## License / Contributing / Security

- License: [LICENSE](LICENSE) (MIT).
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md) — the test matrix, PR writing style, worktrees; locally always set `SPECPROOF_TEST_MYSQL_DATABASE=specproof_test2` and never point tests at the product schema.
- Security: [SECURITY.md](SECURITY.md) — how to report, what stays private; these are real product parts, harden them like you mean it.
- Changelog: [CHANGELOG.md](CHANGELOG.md) — 2026-11-09 and later.
