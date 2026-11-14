# The Book of Iron Evidence · SpecProof Genesis (English Concordance)

> The Chinese original lives at `../SPECROOF_WORLD.md`. This English concordance mirrors its
> structure scroll-for-scroll — every scroll, every anchor, every unfinished roadmap item.
> The iron remains iron in every language.

## Scroll 0 · The Furnace of Evidence

The world wrote code with fire. AI shot arrows into the sky without asking who would catch them.
The Acceptance Officer stood up in the first day and made one rule: *iron first, then a verdict;
no iron, no acceptance.* The furnace opened: base and head were cooked in the same sandbox
(`docker_sandbox.py`), and the flames either bent back toward the baseline (the past was safe)
or toward the head (the future is on fire). Evidence condemned or exonerated.

`base_pass_head_fail` became the iron — the baseline green, the head red, the same flame on both.

## Scroll 1 · Iron Evidence, the Matrix, and the Review Court

### 1.1 The five evidence tiers

| Tier | Name | Exemplar | Iron-ness |
|---|---|---|---|
| 5 | `static_analysis` | regex hits, lint, type errors | suspect |
| 4 | `java_source_diff` | source diff only, no execution | half-suspect |
| 3 | `constitution_check`, `probe_differential` | rule hits, probe runs | semi-iron |
| 2 | `differential_execution` | both sides executed, compared | pre-iron |
| 1 | `base_pass_head_fail` | baseline green → head red | **iron** |

Every cell in the matrix is stamped with its `execution_surface` — where the flame was lit,
and whether anyone was burned.

### 1.2 The Review Court

Not a place where AI passes judgment — a place where AI makes arguments in front of an
iron-stating policy table. The prosecution shows burns; the defense argues "maybe the fire was
already hot"; the judge strikes severity once told "iron". Model prose is allowed to persuade
no one. The `specproof_review_court` policy tables (`tests/unit/test_matrix_pure.py`) are the
actual verdict law.

> Case #1638 — **probe defense turned the wrong way**: the probe was meant to confirm, but the
> static tier tried to make it prove. Iron's name list was pinned back to genuine
> differential-execution only. From that day, a probe is testimony, never a verdict.

### 1.3 Counterexamples

The Acceptance Officer does not sit in court admiring good fires. The compiler produces
JUnit tests that **target the exact change**: baseline green, head red, red like seeing the
wound directly. **A bug that survives the furnace earns the name "iron".**

## Scroll 2 · The Witness and the Scribe

### 2.1 The Scribe's rules

The Scribe (frontend) never lies: blank fields render "未提供" ("not supplied"), never "没有";
findings never outrank their evidence tier; the severity vocabulary is frozen
(`BLOCKER / MAJOR / MINOR / PASS`); unparseable timeline stamps are "honestly omitted" rather
than invented; AI commentary is quarantined from judgment.

### 2.2 Print is the seal

`print.css` is not a stylesheet — it is an instrument of office. Every page that leaves the
printer carries its evidence tier stamped like a notary's red chop.

### 2.3 Copy-to-paste is the reviewer's second language

Every verdict page offers two buttons: "Copy Markdown summary" (plain text for issue threads)
and "Copy Epic Certificate" (the composed scroll for the reading ear). Both are compiled from
the server's own numbers — neither is written by the model on first principles.

## Scroll 3 · The Cache Doctrine

### 3.1 The streaming holy war

In the beginning, every invocation rode the non-stream lane — the dashboard flickered "非流"
while the cache sat cold as a kettle. After the dual-stream unification (#1664) both lanes
now send `stream=True + include_usage`. `_parse_usage` maps
`prompt_tokens_details.cached_tokens → prompt_cache_hit_tokens`, and the billing sees it at
0.1× weight. "非流" no longer exists in this codebase.

### 3.2 The prefix is the temple

"Stable prefix first, variable tail last" is the iron law of the oracle. `_JUNIT_GENERATION_PROMPT`
(`2270` bytes, **96.5%** live cache hit on real calls) demonstrated the richest single cache
return in this codebase's history (#1645).

### 3.3 Honest A/B

#1668 recorded two A/B runs side-by-side: same-byte replay (A/B/C, ~240-250 token wedge) all
returned `cached_tokens=4224`, and same-bytes with a different variable tail returned
None on this gateway that day. Both are printed. Neither is claimed as a contract — the gateway
owns the cache, the temple only keeps its own bricks straight.

### 3.4 The semantic cache

`specproof_semcache:*` (Redis-backed, sha256 keys, 50ms dual timeouts, fail-open, evidence kinds
hard-rejected) — a duplication is only stored if the verdict is reproducible from the same
inputs. The court's voice is never stored. Mechanical kinds (`draft`, `diagnose`) are cached;
nothing else is.

## Scroll 4 · The Steel Rampart

### 4.1 Four services, one taskforce

| Service | Arm | Charge |
|---|---|---|
| `config-server` | quartermaster | `optional:configserver:` import; offline YAML behind it; `/actuator/health` = UP |
| `discovery-server` | roll call | Eureka; `specproof-gateway` registers itself; `/actuator/health` = UP |
| `gateway` | gatehouse | route table as law; two independently vehicle-mounted breakers; `/actuator/refresh` on its own port |
| `control-plane` | interior | tenants, facade, webhooks; the one source of business truth |

The gatehouse built the #1635 gate: a route table that names a `service-id` absent from Eureka
is a page that cannot route; the gate reports `missingServices=[api, control-plane]` by design.

### 4.2 The breaker is the wall

Resilience4j breakers (`specproof-edge` and `specproof-control-plane`) with slidingWindow=10,
minimumCalls=5, failureRatio=50, half-open=3. One night the `/api/v1/tenants` request path was
thrown into the darkness on purpose; calls 1–4 came back `state:closed`, call 5 and onward came
back `state:open` — twelve requests, five open, the wall up. When the wall rose, the error was
`{"edge":"circuit-open","state":"open"}`. The breaker did not apologize; it triggered; it was
working.

### 4.3 RabbitMQ does not knock

Rabbit is an *opt-in* bus (`specproof.observability.events`, six keys, off by default). When
nobody knocks, the `/actuator/health` must not 503. The edge's Rabbit health-check has been
disabled for the same reason the edge's Redis health-check is disabled: an absent opt-in bus
is a degraded capability, not an outage.

## Scroll 5 · The Chronicler's Ledger

### 5.1 Append-only

`docs/operations/DEEP_OPTIMIZATION_PLAN.md` — every entry dated, every number real,
top of each: commits hash. Nothing unsaid, nothing invented, no quiet erasures.

### 5.2 The ledger has four gates

IDs unique, numbering unique, queue pointers resolve, evidence claims true. The drums, the
seals, the words — all four gates keep files unmistakable.

### 5.3 The e2e caught a real bug

In the notes of #1672, `openEventStream` turned `event: done` into a no-op; the AI reading
panel stayed "正在解读…" for as long as the world lasted. The e2e found it; the fix shipped;
the 16/16 number reflects it. The chronicler keeps this red light as proof the gate is real.

## Scroll 6 · The People

- **The Acceptance Officer** — not the AI, not the PM, the one who turns "I don't trust this"
  into "verify".
- **The Witness** — `gpt-6-sol` (`https://wkapi.pro/v1`), streaming lane, never the verdict
  drawer, always the ink.
- **The Scribe** — the frontend modules (`StageTimeline`, `Tour`, `Usage`, `Epic`,
  `Case File`, `imagery`), the silent witness in front of the user.
- **The Chronicler** — the append-only ledger; every entry typewritten, every number real.

## Scroll 7 · The Endless Stories (Roadmap — unfinished)

Future scrolls, unnumbered: **Cache key negotiation** — the fleet's reduction of the red line
into readable ceremony; **Gateway's broken door** — the hystrix quo of the edge; **The ledger
that would not let go** — the gate that refuses a ledger with fake green drums; **The notary's
hand that prints red**.

All unfinished stories are finished inside this book; the ones we know are in the map.

## Final Scroll · The Unfinished

Every victory, defeat, ledger, and scroll in this book lands on one answer:

> **The iron verifies itself.**

Roadmap open items: `PRODUCT_ROADMAP.md` §§1.3 (demo self-check), 1.6 (verify kernel decoupling),
4.2 (counterexample quality policy), 5.3 (observability default-on), 5.4 (deployment shape),
6.1 (IDE/CI integration). Each written there, all named, none hidden.

*This book does not finish; its scrolls accumulate. You are reading at its current edge.
The next leaf is one commit away.*


---

## Scroll 8 · The Chronicler's Vigil

> This scroll was written by the chronicler in real time. It is not a story about the past;
> it is the night's own chronicle, dated 2026-11-14 — the day SpecProof learned to write itself into its own product.

### 8.1 The march of one afternoon

| Time | Event |
|---|---|
| Morning | 「史诗 · The Chronicles of SpecProof」 landed (`#1675`) — a six-scroll bamboo-manuscript page, serif Chinese, jade medallions, red seal 「验讫」 — iron-clad anchors from this repo as 「史官细则」 footnotes |
| Dawn | 「铁证之书 · SpecProof 创世记」 world bible began (`#1676`); this book is the sequel |
| Midday | Interactive 「巡览 · The Grand Tour of SpecProof」 landed (`#1677`) — six stations, each requiring you to touch the real product and stamp each one by hand; six seals render 「验讫」 |
| Afternoon | Spring Cloud full chain built and booted offline: config-server UP, discovery-server UP, gateway registered itself and proxied to the agent runtime; circuit breaker tripped on a dead upstream after 5 calls; `/actuator/refresh` witness meter went 0.0 → 1.0 |
| Dusk | The parallel lane's token-level LLM usage ledger was taken over; three red test contracts rewritten honestly as doc-string contracts; 17/17 green |

### 8.2 The Bottomless Well and the Stars

Three iron teachings this night:

1. **Watch the corners no one watches** — even RabbitMQ's health indicator, a signal nobody asked about, was noted honestly. #1674.
2. **Do not invent** — every "it happened" is anchored to a commit hash; what could not be produced is marked "not yet complete", never "done".
3. **Invite the next chronicler** — the world bible is never finished; it is continuously added to.

### 8.3 Why the world matters

SpecProof is a story about a human who must verify an AI's work. The protagonist is the person,
not the model. A product whose identity is wrapped in myth conveys its values through ornamentation —
and ornamentation that lies is worse than none. Every metaphor in this book rests on real code,
real commits, real tests.

> He who would verify must first verify himself; he who would enter history must first show iron;
> before iron, scepticism is wisdom, faith is truthfulness, doubt is courage.

---

## Appendix A · The Equation

```
验收者之道 = 差分之火 × 契约之法 × 矩阵之镜 × 史官之手
SpecProof  = (AI writes code) → (Differential execution) → (The Matrix) → (Human signs)
```

This is not allegory — `experiments/differential.py`, the contract compiler, `apps/web/src/pages/Matrix.tsx`,
and the 「史诗纪要」 button are the four concrete terms of the same equation.

---

## Appendix B · The Successors

If you are reading this, the chronicler has already begun. Scrolls `#1680`, `#1700`, `#1800` …
will become new panels, new gates, new verification modules. Each will have roots in this book:
the directory first, the details second, and the proof that "it exists" third.

**This book remains open.**

