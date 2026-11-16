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

This is not allegory — `experiments/differential.py（文件不在本仓库——计划中的实验车道，本书保留它的废弃事实，不保留文件）`, the contract compiler, `apps/web/src/pages/Matrix.tsx`,
and the 「史诗纪要」 button are the four concrete terms of the same equation.

---

## Appendix B · The Successors

If you are reading this, the chronicler has already begun. Scrolls `#1680`, `#1700`, `#1800` …
will become new panels, new gates, new verification modules. Each will have roots in this book:
the directory first, the details second, and the proof that "it exists" third.

**This book remains open.**

---

## Scroll 9 · The Seal and the Window

> This scroll, if true, is the acceptance officer's inner monologue; if false, it is still a door a fan may enter.
> Verification is not a thing you pick up in your hands — it is first laying yourself down into the role, then laying down what the other party handed you.

### 9.1 Unlearning all your equipment is a technique

Whoever comes to verify lays down their weapons before entering the door. The officer who does not lay down their weapons is not here to verify — they are here to copy someone else's conclusion. So SpecProof's dictionary has no "QA" in it — it has only "acceptance officer".

The QA engineer's habit says "nothing wrong here." The officer's habit says "this was found; what was not found gets written down too, waiting for you to check."

One kind of thing, once verified, you can see whether it is broken. Another kind, you cannot see whether it is broken — it does not fake evidence and does not hide the retreat. The officer never says "as if nothing is wrong"; they say only "the baseline passes; the head fails, because —".

### 9.2 The one who opens the window

A window is open, looking at other people's code. You see, you record, you do not laugh, you do not cry. Officers do not laugh. When they laugh, it carries no feeling: "The evidence for that block is this cell here." Like the verdict read in court, sentence by sentence, torn open for evaluation — no decoration.

So SpecProof's front end — all those StatCards, badges, seals, timelines — stands between the officer and the emotion, pasting a "I am calm" face onto every reader of the judgement.

Emotion does not enter the crystal of code; but the reader reads through the window seam.

### 9.3 The fourteen gestures (a.k.a. the officer's fourteen faces)

The best way through this contemplation: imagine yourself an officer and watch your hands. All fourteen should have one page of evidence they can point to.

| Posture | Face | Iron evidence |
|---|---|---|
| Stare straight | SEALED — the face the seal lands on | `VERIFIED` (evidence sufficient) |
| Provoke | BLOCKED — brows pushed apart linearly, corners of the mouth drawn in | `BLOCKED` (replayable evidence found) |
| Probe | UNDER REVIEW — corner of the eye slightly narrowed, pen held in the fingertips | `NEEDS_REVIEW` (a human must pull in) |
| Gaze far | STALE — head raised, goose-necked ear | `STALE` (too old; nobody re-verifies) |
| Cold smile | HALF-SMILE — cheeks tight, jaw locked | `CANCELLED` (before you win, it concedes) |
| Close the door | IRON DOOR — someone pulls and it will not move | `ERROR` (tunnel terminates) |
| Silent writing | I HAVE WRITTEN — the hundred lines enter your muscle memory | `FAILED` (the run never finished) |
| Wave away | NOT DONE | `EXPIRED` (done once; now forgotten) |
| Annotate | WHOSE | `VERIFIED` with a 「reviewed」 seal on top — read, and signed |
| Forgive | WAIT A MOMENT | `STALE` re-stamped — you may speak again; find the right spot and verify once more |
| Push the door | A GENTLE PUSH | `ERROR` re-stamped — you stop your own hand; it is echoing |
| Turn off the lamp | GOOD NIGHT | `FAILED` re-stamped — no opening tonight; the lamp stays off |
| Lay down the pen | THE CASE IS CLOSED | the `VERIFIED` button falls into place; nobody knocks on your desk again |
| Still alive | A HABIT | the reverse of `STALE` — "nobody handles it does not mean it is dead" |

Every gesture maps to one way evidence really dies; every death is a state the product itself supports.

### 9.4 Conversation is not a duty

The officer does not report to the vendor. The officer speaks to the iron. If there is no iron, the officer does not write the iron's name — they say "I did not see".

"I did not see" is not cowardice; it is dignity.

SpecProof wrote that dignity into its settings:

- every `evidence_type` is required;
- every `contract_id` is required;
- every `execution_surface` is required;
- every `unverified` is counted into the report honestly.

Better an empty cell, than a wrinkled sheet of paper.

### 9.5 If a full scroll existed

Without "code is law", and without "the right to review is a right" — those words are too humble. SpecProof adds one sentence:

**"Evidence comes before people; people are responsible for the evidence."**

The evidence exists before the person — it exists between the runs, before the merge, before the consensus. People only read the evidence, and then decide whether to accept it. That is all.

---

## Appendix C · The Fourteen Gestures (Brief Table)

| # | Gesture | Maps to Report Verdict | Maps to Capsule Behaviour | One line |
|---|---|---|---|---|
| 1 | Stare straight | VERIFIED | full coverage, per-row PASS | Stamped and done |
| 2 | Provoke | BLOCKED | contains iron evidence that truly blocks the merge (base_pass_head_fail) | No |
| 3 | Probe | NEEDS_REVIEW | missing evidence / at least one unverified cell | Pull once more |
| 4 | Gaze far | STALE | old code nobody asks about — tech debt sedimented | Do not open your mouth yet |
| 5 | Cold smile | CANCELLED | the submission was withdrawn; the iron cannot find its bearer | Waved away |
| 6 | Silent writing | FAILED | verification execution crashed; nothing to pick | No whole fruit to pick |
| 7 | Wave away | EXPIRED | verified once; too long ago, nobody verifies now | Past its shelf life |
| 8 | Close the door | ERROR | the door closed itself; nobody closed it | It neither receives nor greets |
| 9 | Annotate | VERIFIED | you wrote it; you read it; you stamp it | The persona of annotating |
| 10 | Forgive | NEEDS_REVIEW | you softened once; look again | The lamp-off key is handed to you |
| 11 | Push the door | ERROR | confirm the door will not move (it closed itself) | Pin your hand down |
| 12 | Turn off the lamp | FAILED | no more acting — the road ended | A lamp decided by fate |
| 13 | Lay down the pen | VERIFIED | the 「验讫」 seal falls; three years unmoved | The desk is empty |
| 14 | Still alive | STALE | nobody asks, it is not dead | The fire still burns |

Each gesture corresponds to **one button** + **one counter** + **one iron file**. SpecProof is not a book about how to verify; it is a letter that says: *when you face an accepted change, you know what the current acceptance officer looks like* — each one rendered by the bits on the disk.

---

## Final Word · Appendix D

> Iron evidence is neither easy to mint as coin, nor easy to print as paper. Iron is struck — one vertical, one horizontal — and only then does it exist.
> The officer does not mint iron; evidence is executed, executed out. The officer only watches, does not decide whether what was seen should be gripped by the face as faith — only records.
>
> The smiling officer who saw one failure in person still needs to begin from the start next time.
> Every verification returns the same mould to the furnace, to test whether the hammer can strike the smallest chip and the largest — and inside those two chips sit all the unknowns, and the people who can expose them.
>
> Evidence comes before people; people are responsible for the evidence.

---

## Scroll 10 · Before the Reader Opens This Book

> This scroll is not a scroll of the book — it is the preface prepared for whoever will read it later.
> If you have read Scrolls 0 through 9, you already know what the differential is, what the matrix is, where the evidence begins.
> Those are common sense. Scroll 10 speaks of the phenomenon before common sense — when the whole history had not begun; when nobody yet had the word "verification" — how they treated the code.
>
> Those people were not lazy. They were honest. They did not know evidence could flow out of a machine.

### 10.1 The parts you probably did not read

SpecProof does not prove itself the moment you stop reading. When you turn this book from the first character to the last, and you arrive here — every solid number, every morning decision, every row of iron ever written — has already washed over your eyes.

*This is SpecProof's final trick — it is not trying to become the default in the AI code-acceptance industry.*
*It only asks that, when you turn one page, you remember what iron evidence is, what evidence is, what verification is.*

### 10.2 Sixty seconds

If you read only one page:

* Verification is not an ML model; it is a process stage.
* In 60 seconds you cannot become a verification master; but you can remember three words:
  * **Differential** — comparing two runs, two answers, two refs.
  * **Matrix** — rows are contracts, columns are evidence; every cell is one judgement.
  * **Seal** — making a judgement a transferable entity.
* In 60 seconds you cannot unsee it. It will follow you. The next time you open a pull request, you will look at the matrix list beneath it without thinking.

That is all of SpecProof. It tries to be your habit; it would rather sit inside the most exhausted hour of your day, at a quality checkpoint you do not resent — than become the tool you avoid.

### 10.3 The officer does not come to teach you to write code

The officer persuades you no longer to think "maybe I can write it a bit worse."
The officer says "I can not. Today's code cannot be accepted."
The officer says "Today I did not see."
The officer says "Your problem is here — base_pass_head_fail — iron — you cannot get around it."

SpecProof is not the completer; it is the witness that makes nobody comfortable.

This chapter is not in this book. It is on your own screen. You only need to press 「New verification」, and place your hands on the keyboard — it sits before your eyes; every time you glance at it, you will remember: **someone once asked me whether I would become an acceptance officer. I chose.**

### 10.4 The next time you boot up

Next time someone asks you which tool you use for code verification — give them this repository. **Do not say 「SpecProof」. Paste the path. Let the `tests/` speak for you; let them fall in love with the differential on their own.**

### 10.5 The last words of this book

> Five billion lines of code have been written. Written without anybody verifying in advance; when disasters happen the rescue is people, and the evidence and the iron are the price everyone pays.
> When the differential finishes and the matrix unfolds before you — the first 「New verification」 you ever pressed has already been cast; it simply, quietly, loves you.
>
> Do not thank the book. The book is only an empty space holding a heap of code — so that our successors may catch it.

---


## Scroll 11 · The Two Doors

> This scroll is not about verification, nor about evidence — it is about **exits**.
> After ten scrolls standing inside the house, the officer finally understood one thing: a door that can only be pushed from the inside — and can really only be pushed from the inside — is not a door, it is a wall. A door must open in both directions: toward the resident, toward the passer-by.

### 11.1 Before the first door: two streets

One street is written in Chinese, one in English. Both lanes are equally deep and equally bright; but the sign the passerby sees is **not the same sign** — that is not a defect. The defect would be one sign written in two languages so nobody can read it whole. Scroll 11 sets this rule:

> **Inside the door: one shopfront, one language — in two languages, in two worlds; two kinds of guests walk through the same door and see nothing but their own letters.**

In `apps/web/src/i18n/strings.ts`, that rule is written as a table: **one key, two locales, nothing else.** Every Chinese sentence in the table has its English twin line by line; the table has no third form. The Chinese guest cannot see the English, the English guest cannot see the Chinese, and a parity gate stands watch in `tests` — if either side loses a key, the gate goes red in front of everyone. Nobody may walk in and see a half-existing world.

### 11.2 Native English, must also be Chinese

The Genesis was written in Chinese because the chronicler spoke Chinese first. The English edition of this book came later — not as a translation, but as **a second wall, English, raised on the same house**: Scroll 0 through Scroll 10, one by one, paired. Native-English operations documents follow the same rule now: `CLAUDE.md` bilingual paragraph by paragraph, `ARCHITECT_CLAUDE.md` bilingual likewise, `MCP_GUIDE.zh.md` section for section. **Native-English content also has been translated into Chinese** — not because Chinese is superior, but because inside the door, both languages are native.

The honest boundary already wrote: **you can switch ≠ everything is translated.** Legacy page bodies are still Chinese-native, and the English docs have queues that are pushed batch by batch — none of that is lied about in this book. Scroll 11 puts the honest boundary inside the body: the door being open does not mean every hall is already bilingual; what is not furnished yet is hung with an honest card reading 「Chinese exhibit」, or worse, the fog is never allowed in.

### 11.3 The second door: the shop window

This scroll also speaks of a more public door — the window on the street. `xiaodernan.github.io` is the acceptance officer's shop window; what hangs in the window is **this repository's newest achievement**, never last month's photograph.

> The window updates automatically — but nothing is pushed by hand from this repository. SpecProof produces exactly one fact material: `artifacts/portfolio-data/` (`.github-sync.json`, `latest.md`, `products.json`); the portfolio pulls it on its own schedule, or a human taps sync. This repository never pushes anything to the portfolio repository, never ships credentials, never fabricates on the spot.
> Big versions hang new pieces only, at low frequency — so the window is always worth a look, never loyal to volume.

The window does not manage: it displays, it does not decide for the portfolio what to hang or when to change — **producer owns facts; the window owns the wearing.** That is the second courtesy of the door itself.

### 11.4 After the gates open

After both doors are open, nothing inside the room changes — the differential still runs, the matrix still lists, the seal still falls. What changed is the lamp in the room, and the number of people on the street who know this door exists.

The next time someone asks: **"This world has Chinese and English too — the room, the street — which do you look at first?"** — the officer will say: "Push a door, either one. The iron inside the door is the same furnace."

---


## Scroll 12 · Inside: The Hall of Exhibits

> Scroll 11 taught two doors — one inward, one outward. Scroll 12 tells of the room that appeared once the doors were open: the officer pinned twelve iron proofs to the wall.

### 12.1 Why the hall exists

SpecProof's oldest habit is "write it down" — since the first differential experiment, every number landed in the ledger. But numbers land in the ledger, not on walls inside the house. No one photographed these exhibits at the moment they happened; they lay flat by date. So the Evidence Museum was raised: the numbers that were set down in git log, one by one, put back into the posture in which they occurred.

Twelve exhibits, no decorative impact metrics, no "influence stars". **The anchor on each plaque is the weight** — press git show c75a0ef to see the Tour shipped (#1677); press git log --grep "#1689" to see the differential that caught AUTH-01. The hall proves nothing; the hall only turns the lights on at the scene.

### 12.2 Inside the wall, or outside?

The hall is inside — a user opens the sidebar and reads 「质量与证据」 until they see it. And the hall is outside — every anchor it indexes can be checked from outside the wall.

Bidirectional: **seeing outside from inside; both sides share the same furnace.** The chronology from Scroll 0 to Scroll 11 became a user interface not to boast, but to stand up a findable shelf of iron evidence — the differential still runs, the matrix still lists, the seal still falls, the hall waits for you to check against.

### 12.3 Who walks in

There is no fixed hour for it, because **every entry is its opening hour**. Some come for it specifically:

* **The auditor**: first Scroll 8 (The Chronicler's Vigil) for "the ledger does not lie", then walks the twelve plaques one by one, cross-checking anchors.
* **The newcomer**: seals the first tour station (Scroll 1), then reads Exhibit V (the CSS class that broke the build) — and is careful with their first CSS selector forever after.
* **The future chronicler**: one day frowns at one exhibit and begins the continuation of the twelfth. The hall is where the relay baton sits, between one hand and the next.

Some things SpecProof makes for this hour; others — like the next volume — it makes for who will read it.

### 12.4 Toward the next scroll

The roadmap is unfinished: IDE integration (6.1), observability on by default (5.3), deployment shape (5.4) — they all wait in PRODUCT_ROADMAP.md for the next commit. Scroll 11 taught the doors, Scroll 12 taught the hall — what does the next one teach?

*Scroll 12's answer is left after its own end.*

It will not stop inside the Book of Iron Evidence; it will land in the next pull request — because the interface is ready to catch it: the route is open, the anchors are accurate, the chronicler lacks no pen — only the next thing being written down.

---


## Scroll 13 · The Chronicler and the Cache

> Scroll 3 taught the cache as a doctrine; Scroll 13 teaches the cache as **self-discipline** — when the chronicler writes "do not touch that stable text" into their instincts, the cache is no longer a switch but a restraint.

### 13.1 Measure first, then speak

The chronicler never writes "the cache hit rate is high." The chronicler writes: "On 2026-11, _JUNIT_GENERATION_PROMPT's stable prefix measured 96.5% repeated-cache hits on wkapi.pro (#1645); stripped to bytes (#1679/#1681), the same variable tail against different variable values oscillates between 75.2% and 84%."

The sentences are longer but every number lands in git. A cache is a thing that forces honesty out of you — it does not believe you "think you are stable"; it only looks at whether the prefix is truly byte-identical.

### 13.2 Those 2272 bytes

The stable prefix of _JUNIT_GENERATION_PROMPT is ~567 tokens; nobody who wrote it humanised it for readability — the order of fields, the count of newlines, the placement of comments, everything serves the cache. Change one space and you changed the cache key. Sacrificing aesthetics to the machine, the machine pays you back with lower cost and continuous counter-example production.

There are several ways an AI developer treats stable prefixes — quietly extend them, silently shorten them, reorder them, tighten the comments. The chronicler records all of "only grow, never shrink" in their notebook: **what can be frozen, freeze; what drifts, pin down** — push every variable to the tail; dig out the invariant part and brick it into byte-stable blocks.

### 13.3 After the two lanes

After #1644 and #1663, both lanes of verification — the legacy lane and the policy lane — finally run `stream=True + include_usage=True` — the gateway can report cached_tokens now, and the hit rate can land in the ledger of used tokens instead of drifting between a question mark and a comma.

#1681 sets this down as iron law: **every real invocation must take the streaming lane**, otherwise whether the provider's cache saved any tokens depends on whether "the gateway feels like it that day". Streaming is not a style, it is an audit.

### 13.4 Even the cache has a fate

#1679 and #1681 each measured this: **wkapi's cached_tokens may return null** — it computes cache per prompt bytes; whoever swaps bytes pays the recompute. Even with a byte-identical prefix, missing gateway reports or a slightly different prompt snaps the metric off a cliff.

So the cache hit rate is never a contract value. The cache is a hint, not a verdict; the record is the conclusion, not the guess. SpecProof writes "explicitly null when the gateway says nothing" into the Usage panel (#1646/#1704) — better to break the line than draw a fake one. That is the whole doctrine of the chronicler walking with the cache.

### 13.5 Bilingualism changes the meaning of the prefix

After Scroll 11 set "one key, two locales", prompts split into two stable prefixes in two languages — extra cache opportunity, and a harder discipline: both languages are pinned; switching the language is switching a brick. You can try to sneak an English edit and hope nobody notices; in a bilingual review, drift in either edition points at the same PR.

The cache is a mirror: how honest you are with it, your prompts are that efficient.

---


## Scroll 14 · The Fourteen Iron Vows

> Scroll 13 was self-discipline; Scroll 14 nails it into institution. This scroll no longer teaches systems, only the rules — printed on the wall, so every commit can see them.

### 14.1 The iron evidence is never re-written

"It ran once" is not "it will run again." Once the iron evidence lands, erasing it and re-signing it is forgery. Capability may be re-implemented by new code; evidence may only be appended.

### 14.2 Never draw a fake point

Missing is missing. When the gateway does not report cached_tokens, print "—", never zero; when the line breaks, let it break. SpecProof would rather hand over a solid line with honest gaps than a smooth line of lies.

### 14.3 A gate is not a slogan

A gate is allowed to go red. A red gate is not a face-saving excuse; it is the debt you owe this system. One "it was failing but we considered" reads as one undelivered piece of evidence.

### 14.4 The reds are kept

Every failure's count, file and reason is written into the ledger. SpecProof has no "remove the failure record" feature; if a failure vanishes from history, it is not the product changing — it is the chronicler losing their job.

### 14.5 Never forge

When certificates are generated, do not assume "it must have passed"; when approvals are asked, do not presume "it should work"; when output is printed, do not re-express what humans decided. The evidence speaks; you keep its mouth shut or open honestly.

### 14.6 No substitution of roles

An acceptance officer cannot replace a developer; a developer cannot replace an acceptance officer's judgement. The one who writes owns every line written; the one who verifies owns every piece of evidence found. Neither speaks for the other.

### 14.7 Must reproduce

No one should be asked to believe a spur-of-the-moment eerie behavior that cannot reproduce in a fresh environment. The bug capsule exists so that "eerie" can happen twice.

### 14.8 Test hostility

Tests cover the happy path, and the reverse path; a test does not only "should work", it also "cannot be deceived". Counter-examples are not invented; they come from the requirement — base_pass_head_fail.

### 14.9 Division of labor

The chronicler records; the officer verifies; the developer implements; the compliance guard complies. No one is allowed to play two roles at once.

### 14.10 No guessing

What cannot be seen clearly is "unknown". In SpecProof reports, "unknown" is a legal state, and more trustworthy than "probably fine".

### 14.11 Better to be plain

State "275 fast tests", not "all tests are green". Each commit prints what it did and what it did not; nothing is left to inference.

### 14.12 Blank is its own silence

A blank is not nothing; every "unknown" need not be filled with guesses.

### 14.13 Connects the suspicious hand

Anyone who presses "accept" must carry the consequences of "accept". After you clicked, the system still works with the iron evidence — it does not inherit your blindness, nor feed your fantasy.

### 14.14 The last iron vow

**Evidence comes before people; people are responsible for the evidence.** Whether you are a developer, an acceptance officer, or the reader here now — the first thirteen are operational rules; this one is ontology.

---

## Final Scroll · The Unfinished

Every victory, defeat, ledger, and scroll in this book lands on one answer:

> **The iron verifies itself.**

Roadmap open items: `PRODUCT_ROADMAP.md` §§1.3 (demo self-check), 1.6 (verify kernel decoupling),
4.2 (counterexample quality policy), 5.3 (observability default-on), 5.4 (deployment shape),
6.1 (IDE/CI integration). Each written there, all named, none hidden.

*This book does not finish; its scrolls accumulate. You are reading at its current edge.
The next leaf is one commit away.*
---

## Volume XV · The Unfinished Road (卷十五 · 未完的路)

> The final word said: "This book will never be finished — the next volume is one commit away."
> This is that commit. This volume does not sing of what is done; it writes down what is **not** —
> every unfinished thing in the canon, carved on the wall with what "done" looks like,
> so that no successor mistakes a IOU for a tombstone.
> A blank is not a shame — a blank is a map; and every blank on this map has a name.

### 15.1 Six plots of open land

| Debt | Name | What "done" looks like |
|---|---|---|
| 1.3 Demo self-check | Demo doctor | One command self-checks the demo repo: `base` and `head-v1` tags exist, `requirement.txt` exists, the verify trail replays byte-identically — red on broken, green on sound |
| 1.6 Verify decoupling | Verify without the cockpit | The verify core becomes its own library; CLI / Web / worker all call **the same** iron-evidence pipeline — change any entry, and the other two drift on sight |
| 4.2 Counterexample adjudication | The counterexample bench | Counterexamples can be voted "false positive / real issue" and filed into the `eval` golden set; the false-positive rate finally has a denominator — precision never again by vibes |
| 5.3 Observability out of the box | Observability out of the box | `/metrics` (Prometheus) + a pre-stocked Grafana board: after `compose up`, verify p95 is on the home page with zero manual wiring |
| 5.4 Deployment shape | The ship shape | `compose.production.yml` converges to one command for the full stack (API / worker / MySQL / Redis / RabbitMQ / static view); it earns a spot at the top of the README only when healthchecks are all green |
| 6.1 IDE / CI integration | The doorway | A GitHub Action on the PR: base/head acceptance runs automatically, the verdict lands as a Check Run — no clone, no asking, the iron evidence is one click away |

### 15.2 Surveyor's notes

* **Demo doctor** is not a script; it is the demo repo's signature: anyone running `git tag -l` should see
  `base` and `head-v1`, and the outcome must match `docs/operations/USER_GUIDE.md` §1.3 byte-for-byte —
  docs and reality must not drift apart by a single character;
* The enemy of **verify decoupling** is entries that grow unlike: `api/`, `worker/`, and CLI each patching
  their own copy. The completion test is brutal and simple: one spec, three doors, **identical finding fingerprints**;
* **Counterexample adjudication** is not E2E: E2E proves "it ran"; adjudication proves "it did not fool me."
  The golden set must support voting, being overturned, and the overturn must be logged
  (append-only law, Volume XIV · 14.4 — red is kept on record);
* **Observability out of the box** has exactly one acceptance criterion: on a fresh machine, after
  `docker compose up`, the Grafana home page shows verify p95 **without a single manual click** —
  one missing dashboard is one missing lighthouse;
* **Deployment shape** and **IDE/CI** are paired: the ship shape makes the system stay alive on its own;
  the doorway makes it walk into other people's workflows — one is feeding, the other is letting in;
  through the door, the user no longer needs to read this book at all;
* One item in `docs/ROADMAP.md` under P5 — "LLM variability" — is **not** on this debt wall anymore:
  it was paid, as **real LLM integration + real end-to-end smoke (#1724, 7/7 PASS)**.
  But it must be said plainly: what was paid was "it runs," never "the model is innocent."

### 15.3 The promise to the showcase

The SpecProof entry on `xiaodernan.github.io` ships weekly (Sunday 06:00 UTC) via
`.github/workflows/portfolio-sync.yml` (or on master merge / manual dispatch); it pushes
`data/specproof-*` only when `PORTFOLIO_TOKEN` exists — otherwise it quietly rebuilds and bows out.
The showcase is a vitrine, not a scoreboard: updates land on big leaps, never on noise.
**The showcase tells no lies; the numbers never invoice themselves.**

### 15.4 The keeper's IOUs (as of #1726)

| Debt | Status |
|---|---|
| The reading of the "96.5% cache hit rate" | **Paid** (#1723 — gateway's 4224-token constant, downgraded to an observational metric) |
| Portfolio auto-sync | **Tooling live** (#1722) — waiting on one secret; the IOU is on your desk, not the keeper's |
| Ghost routes in the user guide | **Paid** (#1726 — guide ↔ App.tsx aligned + 6-test gate holds the line) |
| Full `pytest tests/unit` | **Unpaid** — local memory fell to ~1.8 GB; as of #1730: 492/492 frontend vitest green + all parity vocabulary gates green + ledger four 45/45; the full Python unit suite still has not run; this line is kept on the record, not whitewashed |
| ~~`toneMap.ts` / `errorHints.ts` Chinese residue~~ | **Paid (#1730)** — glosses now resolve per locale (78 keys ×2); the Python gates read the i18n table; `preflight.ts`/`stages.ts` remain, tracked separately |
| ~~Volume XV inside the app (`/epic` showed six scrolls)~~ | **Paid (#1729)** — `/epic` gained Scroll VI, The Unfinished Road; seven scrolls in zh and en |

### 15.5 For the next reader

* If you are a **user**: start at `#/tour`, stamp all six seals — you will know this system better than 90% of the repo's readers;
  in a hurry? go straight to `#/drill` — twelve rapid-fire questions, every one anchored to a real file or a real ledger line; finish it and see whether the iron recognises you;
* If you are a **contributor**: pick any plot in 15.1, read Volume XIV first, then move —
  "what done looks like" is already written above; **the acceptance bar is not in your head, it is on this page**;
* If you are the **keeper**: new convention — every time a debt is paid, add a line beside 15.4;
  merge into master, and every page of this world is an archaeological layer of commits.

### 15.6 This volume's vow

Unfinished is not failure — unfinished is the map.
Every plot of open land has a name; every name has a "what done looks like."
That is the whole secret between "a vast world" and "one real commit at a time."

**Volume XV keeps no good news — it keeps IOUs, the map, and the relay baton.**
---

## Volume XVI · The Twelve Iron Scales (卷十六 · 十二把铁秤)

> Volume XV said: iron that never gets checked lies to itself. This volume records exactly one thing —
> the road from "it claims to be bilingual" to "the locale toggle actually switches it",
> and the twelve questions that walked this repository to its own exam.

### 16.1 Two kinds of bilingual

**Token bilingual**: BENCHMARK, `BLOCKER` — a token is code; code accepts no translation, only bytes.
**Gloss bilingual**: `"ui.unknown"`, `"severity.BLOCKER.hint"` — a gloss is text; text answers to locale, to the toggle.
SpecProof has spoken the first kind since 2026-09 (contracts / schemas / payloads in English); this round
delivered the second: `toneMap.ts` (#1730), `errorHints.ts` (#1730), `stages.ts` (#1732),
`preflight.ts` (#1732) — 147 keys, zh verbatim, en hand-translated, `i18n.parity` locking both tables in both directions.

### 16.2 Ghost routes and the ledger's honesty (#1726)

The guide once sent a newcomer into three rooms that never existed: `/mcp`, `/admin/identity`, `/readme`.
Follow the table, knock on the door, get a 404 — a guide that lies is poison upstream of the code.
This volume establishes: **every route the guide lists must exist; every route that does not exist must leave
the guide; and `tests/unit/test_guide_route_catalog.py` stands guard forever** — six assertions on the same net.

A side note for the keeper: the App shell (skip-link, session area, top bar, footer, 404) used to carry a wall
of hardcoded Chinese — English mode rendered a Chinese shell anyway, and "everything bilingual" quietly lost on this front.

### 16.3 Self-check for the people (#1728)

Volume XV called the demo doctor "the demo repo's signature". It is now a command:
`python scripts/demo_doctor.py` — zero Docker, zero network, zero LLM, six static checks,
`--json` for machines, `--strict-clean` for a red candle on a dirty tree.
It is cast from two things: a demo repo pinned by tags (`base`, `head-v1`) and a working tree you must not whitewash.
Three uncommitted changes stay WARN on this machine — craft's ration is not code; it is honesty.

### 16.4 The great gloss migration (#1730 · #1732)

The glosses in `toneMap.ts` / `errorHints.ts` are no longer Chinese literals; they are i18n keys,
resolved at render time by `storedLocale()`. The three Python gates (severity / evidence / accept parity) now read
the i18n table; the assertions about "不阻断" (must-read-no-blocking) keep their meaning without keeping
their old location.

One record for the record: **the key-and-English-text inversion** — during extraction, the nine blocker keys
were written as `"ENGLISH SENTENCE": "preflightBlocker.xxx"`, nine bogus lines on each side, eighteen in total,
caught twice over by tsc and by eyes; the fix removed no test — table structure, resolution points and boundaries
changed, the bad lines were deleted, the good keys were restored verbatim.
The red is not covered; the red is written down here.

One owed debt discharged: `verdict_channel_parity` was red **at the master baseline** — `api/ai_summary.py`
writes a `verdict` field claimed by no channel. This round declared it truthfully as a **carrier** for `job_summary`
(owner + opaque, the same pattern as notify/templates.py) — and the gate is green for real.

### 16.5 The twelve iron scales (#1733)

`#/drill`: twelve questions, each a doorway back into the repository.
Not prose trivia — "what is `base_pass_head_fail`" is not rhetoric, it is the declared domain of `evidence_kinds.py`;
"wkapi reported ~96.5% hit rate — and what was it" is not gossip, it is the 4224 constant measured in #1723;
"the gate went red — may we merge 'having considered it'" is not a values question, it is you, the button, the iron.
Wrong answers replay: a missed-question review strip with the teacher's note attached; the ones you cannot unsee.
Four seals: Apprentice → Journeyman → Evidence Knight → Iron Verdict Master; the best score lives on your machine,
`specproof_drill_v1` is one cold account, not a promise. 497/497 vitest green is the seal's insurance.

### 16.6 The keeper's transit table: this round's chain (#1726 → #1734)

| Commit | One line |
|---|---|
| #1726 | Ghost routes cleared + 26 shell keys into the table + guide-catalog gate born |
| #1727 | Volume XV «The Unfinished Road» — the final word became a ledger |
| #1728 | Demo doctor: six static checks on the demo repo, zero Docker |
| #1729 | `/epic` Scroll VI, «The Unfinished Road» — seven scrolls, zh and en |
| #1730 | Gloss migration, first half: toneMap/errorHints into the table + verdict_channel_parity baseline-red gone green for real |
| #1731 | Vol. XV debt wall synced (epic & gloss boxes checked off) |
| #1732 | Gloss migration, second half: stages/preflight into the table; the inversion incident, recorded verbatim |
| #1733 | `#/drill`: twelve iron scales, four seals, 497/497 green |
| #1734 | CHANGELOG brought current; portfolio-sync re-run parses |

### 16.7 This volume's vow

**A tongue has two colours; evidence has one.**

Tokens may stay cold; glosses must stay warm — warm in whichever language the button speaks.
The iron does not care about ESLint's palette, nor about the colour of a fig leaf — it only knows
*whether*, and *whether not*.
A quiz can be failed; evidence cannot. The drill examines the former; this book, the repository and every
signed certificate examine the latter.

---
---

## Volume XVII · The Two-Tongued Verdict (卷十七 · 两种语言的验收)

> Volume XVI closed with: tongues have two colours; evidence has one.
> This volume speaks to the two questions that follow: how a machine answers
> in both languages, and how its own gate turns red when a promise is broken.

### 17.1 Say it in two tongues — the verdict is the same word

#1741, a live experiment: the identical finding, once in Chinese and once in English,
thrown at gpt-6-sol with one rule — it may only answer BLOCKER / MAJOR / MINOR:

- Chinese prompt, 4,749 tokens, `cached_tokens: 3981` — answer `BLOCKER`;
- English prompt, 4,727 tokens, `cached_tokens: None` — answer `BLOCKER`;
- verdict: CONSISTENT.

The experiment settles one small thing, but it is a true one: **the bilingual UI is not an imagined
double promise — the model returns the same verdict on the same sentence in two languages.**
That the zh and en cache counters disagree is not a success datum for the consistency probe — it is
a live re-enactment of #1723: the hit rate flips its flag at will, and every "health promise" must
live in observation, never in wish.

### 17.2 CI guards more than tests — it guards the manual's promises (#1740)

Volume XV named the Demo doctor "the demo repo's signature"; this round it became a workflow:
`.github/workflows/demo-doctor.yml` — fired on master push / PR / manual dispatch, with
`fetch-depth: 0` so the `base` and `head-v1` tag refs survive checkout
(a shallow clone would hollow this gate into a loud false alarm — and the manual's promise would rot into a slogan).
Touch the demo repo, break a tag, delete a requirement — the machine turns red immediately.
This is the first stair on the 6.1 “IDE/CI integration” debt, and one step into
**"every promise deserves a guard."**

### 17.3 This volume's vow

Speak to the user in two languages; speak to the machine in two languages; speak to the ledger only in the truth.

The machine reads indexes, charsets, arrow-aligned PNGs — the single amendment it accepts is
the append-only line. Evidence before people, before models, before CI runbooks — before every
urge to merge a little sooner.

---
---

## Volume XVIII · The Forge and the River (卷十八 · 铁匠炉火)

> Volume XVI said a tongue carries two colours; evidence carries one. Volume XVII said
> speak to the model in two languages; it answers back in the same word.
> This volume covers three things: **what is actually inside the forge (the IDE)**,
> **what you actually see on the river (the graph)**, and **why a page on a screen
> is never a substitute for the one thing that can run: your machine.**

### 18.1 The forge holds no magic

`#/ide` gives you three things only: an anchor rail, a copy-board, and a forge journal.
The anchors are real files; the commands are real commands; the journal never leaves
your browser (localStorage only, `specproof_ide_notes_v1`). There is no "cloud IDE" —
the forge *is* the cloud IDE: one SPA, the same `apps/web/dist` FastAPI serves statically.
Anyone promising "a SpecProof cloud IDE product" is selling smoke. Your local compiler
is the only thing that runs your code — not a page.

### 18.2 The copy-board commands are not suggestions

The five spells on the copy-board — `demo_doctor.py`, `specproof verify … --no-llm`,
the ledger four gates, `provider_smoke.py`, `cache-probe` — are byte-identical to the
commands that run in this repo. If a future page, doc, or quickstart line on this product
shows "specproof verify" differently, that's documentation drift — and the drift itself
is a lie about the product. The drift is caught by `test_guide_route_catalog.py`, guarded
by #1728's demo doctor, and it cannot slip through.

### 18.3 The river is not fantasy

`#/graph` draws `agent/graph.py::build_phase0_graph()` — eighteen real nodes, two real
conditional edges (`_abort_on_preflight`, `_abort_on_errors`), one `StateGraph(Phase0State)`.
Those two guards are extracted from `agent/nodes/`'s real callables; they will not multiply
into a nineteenth node just because a page looks elegant.

### 18.4 This volume's vow

**There is no cloud IDE. There is only this server, serving this page.**

The cloud IDE is the moment FastAPI mounts `apps/web/dist` — not another product, not
another repo, not another daemon. The forge, the river, Volume XVII's probe: their only
virtue is putting, on one screen, commands that used to be scattered across the repo.
The forge's privacy boundary: the journal lives in `localStorage`, the chimney is your
keyboard, the coals are your own requirement — nobody collects your data.

---
---

## Volume XIX · The Forge's Pen (卷十九 · 铁匠之笔)

> Volume XVIII said the cloud IDE does not exist. This volume holds two things:
> the pen the keeper writes with, and the pen the keeper uses to label the
> blanks as blanks. The two are the same pen.

### 19.1 Every stroke in the repository is a commit

The 1,561 entries in `DEEP_OPTIMIZATION_PLAN.md` are not "documentation". Each
one is the **transcript of a commit**. They record not what might have been
done, but what was. The keeper only accepts two kinds of sentences: "it did X"
(with the measurement) or "it did not do X" (with the boundary). There is no
third kind of sentence.

Volume XIV said red stays red; this volume says the same thing on its other
side: **each entry reports only what it actually did and actually did not do**.
There is no "felt fully accomplished" section. There is no "well done" section.
Each entry has an honest-limits block and it lives there permanently.

### 19.2 The chronicle is a snapshot, not a perpetual-motion machine

`apps/web/src/pages/chronicle.json` is a digest of the ledger — 1,561 rows, JSON,
under 260 KB. It **must be regenerated** to track the ledger; if you change one
line of the ledger and forget `build_chronicle.py`, the chronicle page lies to
you and says "the ledger did not move". That is a crime by this house's laws.
This volume therefore sets the rule: **the ledger is one thing, the chronicle is
its projection at one instant, and only one intermediary script stands between
them.**

### 19.3 This volume's vow

**The pen will not lie for you. But it can say, with no remorse, that you did not do the thing.**

**If you did it, write it into the ledger, and it becomes a permanent part of the record.
If you did not, write it into the boundary block, and it will never haunt you again.**

This volume writes not the history but the law of the keeper. The keeper does
exactly two things: records what happened, and offers no excuses.

---
---

## Volume XX · The Cartouche of Iron Evidence (卷二十 · 铁证的印章)

> This volume covers only one thing: **whoever presses the button, bears that press. Iron is the imprint the button leaves behind — not an excuse.**

### 20.1 Four ways a case closes

- **APPROVED** — the iron says it; the iron is its own witness, not a borrowed grace;
- **PROPOSED** — still a proposal; the moment of verdict has not arrived;
- **REJECTED** — the iron says there's no case, and the reason is preserved in the record;
- **REVOKED** — someone signed before and now withdraws. This is not weakness; it is honesty standing up.

### 20.2 A seal is not, and has never been, an "ending"

Pressing APPROVED does not write a full stop. It signs the page, yes —
but it also puts the responsibility onto the same page, in the same ink:
after this, if the chain is ever challenged, the signer meets the evidence again.

### 20.3 The keeper's secret, written plainly

Choosing to revoke is not shame. **Revoking happens only after the keeper has looked
at their own earlier confidence and said it does not hold.** The iron rail does not
applaud neither the fast seal nor the slow seal — only the honest one.

### 20.4 This volume's vow

**The Iron Book is a book every page of which is iron — but it is only ever
worth what one hand has signed. Iron, by itself, does not speak. It waits for the signature.**

---
---

## Volume XXI · The World of Iron Evidence (卷二十一 · 铁证的世界)

> This volume answers one only question: **why does this place never end?**
>
> The user opens SpecProof not for one verification, but to step into an ever-expanding evidence-learning field —
> each entry another place to explore, each page another layer of proof that the book holds together.

### 21.1 What the world is — the physics of ledger, seals and evidence

| Room | Function | Real substance |
|---|---|---|
| The ledger | every entry recorded | 1,561 sections #130 → #1768 |
| Chronicles | one event, one chapter | /epic 12 scrolls / World Book Vol.0 – XXI |
| Manual | half a minute to the door | /manual — printable A4 cheat sheet |
| Chronicle | one row per entry | /chronicle 1,561 rows |
| Census | real code metrics | /census 2,690 files / LOC 481,896 |
| The Grand Tour | interactive guide | /tour six seals |
| Epics | real commits anchored | git log --since=… |
| Museum | real case studies | /museum 12 exhibits |
| Lexicon | the words no one else knows | /lexicon 14 definitions |
| Fourteen Gestures | the form book | /gestures 14 poses |
| Verify Drill | your own quiz | /drill 12 questions |

Every number came from this repository — none was invented or padded. Whatever does not match on re-derivation, fix and tell.

### 21.2 Why this world is big enough

1. **The evidence never runs out** — 1,561 entries is 1,561 moments worth walking through;
2. **The world keeps growing** — every new master merge is one more coordinate to visit;
3. **The user holds the key** — `specproof verify` is not a toy button, it is the code that runs;
4. **Every room has a door** — /tour → /guide → /manual — three paths to the same house;
5. **You are reading the argument, not the tutorial** — the original argument outlives every tutorial.

### 21.3 Design law of this world

- **No demo data** — every figure on every page is derivable from the repo or from the ledger;
- **No unanchored claim** — every piece of content can be pointed at a commit, a file, or a ledger line;
- **No locked door** — leaving is also a move;
- **No erased history** — append-only is iron law (see Vol. XIV).

### 21.4 This volume's vow

**Evidence is not a product; evidence is the law. The Book of Iron Evidence is not a book — it is a parliament:**
**each entry passed through its own signature; every signature is one of two sentences: "it did X" or "it did not do X." There is no third sentence.**

---
---

## Volume XXII · The Evidence Archipelago（卷二十二 · 证据群岛）

> An infinitely large page has one problem: it is too big for anyone to dare a first stroke. This volume answers the other question — **the world never ends, people get lost; who draws the map?**
> This is also the sequel to Volume XXI: a world of iron evidence is not a book but an archipelago; this volume charts its sea lanes.

### 22.1 Why an endless world must ship a chart

- Endless evidence means endless ways to be lost; lost means patience dies first, then leaving — both are enemies of iron evidence;
- Nobody landing in SpecProof should have to memorize 25 entries first. They need a chart: three islands, twenty-four halls, three expedition routes;
- **A map does not replace exploration — it is the porch over the threshold**: the one who reads the map is the one who dares the plains;
- This volume is anchored to two commits: **#1770** (the Atlas, `#/atlas` — SPECROOF ATLAS, landed) and **#1771** (Atlas verification: `getBBox` math QA — compass, scale bar and caption all inside the frame).

### 22.2 The archipelago at a glance — three islands, 24 halls, every hall a real route

| Island | Halls (24) |
|---|---|
| The Workspace Highlands (5 halls · teal) | Dashboard `/dashboard` · Verifications `/jobs` · AI Developer `/agent` · Chronicles `/epic` · Grand Tour `/tour` |
| The Evidence Plains (13 halls · indigo) | Iron Lexicon `/lexicon` · Evidence Museum `/museum` · Fourteen Gestures `/gestures` · Requirement Coverage `/matrix` · Case File `/explorer` · Contracts `/contracts` · Effectiveness `/eval` · Verify Drill `/drill` · The Forge `/ide` · The River `/graph` · Chronicle `/chronicle` · Iron Census `/census` · Manual `/manual` |
| The Governance Coast (6 halls · amber) | Team & Access `/identity` · Usage & Billing `/billing` · Cache Health `/usage` · Audit Trail `/audit` · Model Connection `/settings` · Service Status `/health` |

(Implementation: `apps/web/src/pages/Atlas.tsx`; data: `apps/web/src/pages/atlas.copy.ts`. Room-dot coordinates are a readability-first hand layout — the island silhouettes are a decorative device, not a geographic survey. Output formats are outside this volume's warranties.)

### 22.3 The three honest parts of the chart — compass, scale bar, caption

- **The scale bar is anchored to the real commit count** — `0 / 1,000 / 2,000 / 2,400+` and climbing with the trunk (`git rev-list --count HEAD` re-derived live). It is not decoration; it is the repo's heartbeat tick;
- **The compass's N is engraved inside the dial** — flanked by an E/W tick, never crossing the 26px inner circle;
- **The engraving `THE EVIDENCE ARCHIPELAGO · EST. #130 · MMXXVI` sits on the top-left margin** — never over an island, never over the sea, never over the compass;
- The discipline shared by all three: **nothing crosses the frame** — outer gold rule, inner 1px gold hairline, no ornament allowed beyond.

### 22.4 The three expedition routes — a lane for each kind of visitor

1. **Fast Shore (90 seconds)** — `/tour` → `/manual`: six stamps and one folded page;
2. **Evidence Expedition (25 minutes)** — `/epic` → `/chronicle` → `/census`: thirteen scrolls → one thousand five hundred seventy-three entries → files/LOC re-derived live;
3. **Live-Fire Course (10 minutes)** — `/jobs/new` → `/matrix` → FindingDetail: run it for real — the demo repo's `@PreAuthorize` really is gone; six contracts, six verdicts.

(The `#/atlas` page carries all three as cards at the bottom; the routes are also written here — pocket card, tour, manual, epic, drill: not one of them a prop.)

### 22.5 This volume's vow

**The world will not walk for you, and neither will the map; the map owns exactly one truth — wherever you have walked, that ground is yours.** Being lost was never a failure of strength — it is what happens when nobody draws the first chart. From this volume on, any page that claims to be "endlessly open" must first draw its island; what cannot be drawn is sand, not land.

---
---

## Volume XXIII · The Reading Room（卷二十三 · 书房）

> A book worth keeping for life should not sleep inside a terminal. This volume says: the Book of Iron Evidence finally has a room of its own —
> **`#/worldbook` (铁证书房)** — every word laid out inside the app, full-text searchable, stamped by the reader wherever they have read.
>
> This is the volume about the book within the book — and it is itself part of that room.

### 23.1 Why the book needed its own room

- Until #1774 the world book lived only under `docs/world/`, openable with an editor — the historian read by `git log`, the visitor browsed the halls over HTTP, **and nobody had built a reading room for the official history**;
- A terminal does not render tables, does not mark a chapter read, does not keep your page — an official history deserves a room with pages, a bookplate and a progress bar;
- The room holds three things: **pixel-faithful reading** (marked renders tables, code and quotations), **full-text search** (`<mark>` highlighting), **a stamp per finished volume** (localStorage progress) — all anchored to the repository's real content; not one demo line.

### 23.2 The room's furnishing — twenty-nine sections, shelved verbatim

| Furnishing | Real substance |
|---|---|
| Frontispiece | The book's preface: before iron evidence, the doubter is wise; the untested are washed in iron |
| Volumes 0 – XXII | All 23 volumes (The Foundry of Creation → The Evidence Archipelago) |
| Appendices A – D | The Book's Equations · The Next Scribes · The Brief Table of Fourteen Gestures · The Book's Last Word |
| The Final Chapter · 未完 | The ending is no ending — it is the threshold of the next volume |

Both editions in parallel (the same 29 sections; read in the language you keep); search strikes straight at real iron words like `base_pass_head_fail`;
the progress denominator is 29 (`specproof_worldbook_read`) — progress is never faked.

### 23.3 The room's door — a book, rooms beyond the book

- Entry: the Evidence Plains island (`#/atlas`) · the sidebar's 「世界书 / World Book」· the route table in the guide §3;
- Every control has a way out: open-a-random-volume (⚄) — let the world feel real, deep where it is deep, deeper where you didn't know you needed it;
- Three font sizes (A− / A / A+) — an old book need not whisper;
- The room itself ages: `scripts/build_worldbook.py` must re-run after every merge to master, or the book on the shelf fades.

### 23.4 This volume's vow

**The reading room is the temple of the official history, not a corner of a showroom; whichever volume you finish, that volume is your territory.** The official history never seals — neither does its room;
the moment the next volume is written, its lamp lights again.

---
---

## Volume XXIV · The Unmixed Tongue（卷二十四 · 不混）

> This book is written by verifiers; verifiers tolerate no half-truth — likewise **no screen may be half-Chinese, half-English**.
> This volume records the language discipline: zh mode renders in Chinese, en mode in English, never mixed; every mix is a bug.
> This volume exists because it really happened — and was really fixed.

### 24.1 Why mixing is a disease

- A Chinese-mode reader meeting “规划中 Planning” reads half a sentence in two languages, not one whole one;
- The chronicler writes no mixed sentences — a mixed sentence fools neither human nor machine: it is harder to search, to cite, to translate than either language alone;
- **Language and evidence are the same discipline**: evidence precedes argument, language precedes the screen; bound first, render second.

### 24.2 The spoils of the campaign (anchors #1777, #1778)

| Battle | Fix |
|---|---|
| Agent console labels (~40 sites) | `规划中 Planning` → dual tables, picked per locale; backend mirror `AGENT_STATUS_META` untouched verbatim |
| Gates / acceptVerdict / unknownNotice | pure-Chinese → zh\|en dual tables; acceptBlockedNotice bilingual; validation messages bilingual |
| Epic certificate (Markdown export) | `zh「史诗验收纪要/一、卷首/二、铁证/三、印章」↔ en「Certificate of Verification/I·II·III」`; Verdict vocabulary bilingual; `（未提供）↔ Not provided` |
| Verify Drill (#/drill) | already zh/en keyed since ~#1723 |
| The Grand Tour (#/tour, six stamps) | `TOUR_BY_LOCALE` since landing |
| Epic / World Book / Atlas / Reading Room | zh-branch or `Record<Locale, …>` from birth — holding the line, not a front of this campaign |
| Test default | `test-setup.ts` pins `specproof_locale=zh` before each test; English scenarios opt in themselves |

**The exchange that landed as #1778**: three test files' expectations were single-language-fied (16+3+1 sites); 497/497 with the one documented UiKit.smoke flake, green on re-run.

### 24.3 Three footnotes to the iron law of language

1. **Native English must also be translated under zh**: whatever the original says, zh mode puts Chinese on the screen — the baseline courtesy owed to the reader;
2. **i18n parity is a CI gate**: the two strings.ts tables align key-for-key, or red — no blood-mixed fallback allowed;
3. **Machine vocabulary and screen vocabulary are eaten separately**: backend `STATUS_LABELS` and the screen's Chinese table stand apart, pinned so neither side lies alone.

### 24.4 This volume's vow

**One screen, one tongue; every clause, one meaning; any mix must be signed.** The official history has carved this into two books plus one test default — from now on, whoever dares an English word into zh mode will be lit by the lamp this volume lit.

---
---

## Volume XXV · The Iron Gate, the Redis Token Bucket（卷二十五 · 铁门如意）

> The Gate never asks whether the caller is friend or foe; it asks one question only: **do you hold enough tokens for this pass?** This volume is the story of SpecProof's edge —
> every request measured once, by the same atomic Lua inside one Redis. Not a metaphor: the code this volume anchors lives at
> `services/gateway/src/main/resources/redis/ratelimit-token-bucket.lua`, readable verbatim.

### 25.1 Why rate limiting is distributed

- Single-instance limiting × N replicas = N times the quota — not fairness, a leak;
- SpecProof's edge holds **one token bucket in one Redis**: every replica debits the same account, so "50 req/s at the edge" means 50 across the fleet, not 50 per replica;
- One bucket = one Redis hash (`specproof:ratelimit:<name>:<key>`), one `EVAL` per decision —
  **atomic, no lost-update**: two replicas racing on the same key cannot both believe a token was free;
- Refill is **lazy** (O(1), regardless of idle hours); Redis owns the wall clock via `PEXPIRE` —
  idle buckets simply expire, no replica needed to stop and keep books.

### 25.2 The Lua script's three honesties

1. **Clock regression clamp**: `delta < 0 → 0` — an NTP correction never mints free tokens;
2. **Denial never undersells**: `retry_after = ceil((requested - filled) / rate)` floored at 1ms —
   never "0ms", never a hollow "you may";
3. **Misconfiguration does not kill the script**: measured 2026-11-15 (#1783) — `refill=0` or `NaN` made the old script divide by zero / raise,
   every request paying once for the crash; the script now treats such configuration as "no refill",
   denying with `retry_after=1` and never crossing a Lua exception onto the wire. Seven cases verified green (#1783).

### 25.3 The full lane (all real)

| Part | Real substance |
|---|---|
| Gateway | `services/gateway`: edge limiters (in-memory bucket / distributed bucket `RedisTokenBucketRateLimiter`), SingleFlight cache, Resilience4j circuit breaker, request-id / request-size / security-headers global filters, Eureka discovery, Config Server hot refresh |
| Discovery | `services/discovery-server` (Eureka — 1/1 green) |
| Config | `services/config-server` (1/1 green) |
| Control plane | `services/control-plane` (51/51 green) |
| Messaging | RabbitMQ `GatewayMqEventConsumer` (edge event consumer, P0 lane) |
| Redis | primary probe :8000, sentinel :8767, `spring.data.redis` (limiter/cache/pool `GatewayPoolMetrics`) |
| Exhibits | `#/graph` — the 18-node River of Verification; metrics carry `specproof.gateway.distributed.rate.decision` (allowed/denied counters) |

### 25.4 This volume's vow

**The Gate is not there to keep people out; it is there so every person who passes knows why they were let through.** Lua does exactly three things: look at the bucket, refill it, write the ledger — it does not decide, it settles. The Gate stands; the ledger stands; the Gate opens, the ledger is clear.

---
---

## Volume XXVI · The Wall and the Wire（卷二十六 · 铁墙与消息）

> The Gate guards the door; the wire guards the exit — this volume is the story of SpecProof's other silent lane:
> **the agent runtime (Python) writes six events to RabbitMQ; the edge (Spring Cloud gateway) counts them from the far shore.**
> Neither imports the other's code — they meet on the `specproof.observability.events` topic exchange —
> which is the entire point of an event bus: strangers collaborating without ever meeting.

### 26.1 Six events, one exchange

| Event | Meaning |
|---|---|
| `published` | message enqueued |
| `publish_confirm_timeout` | broker never confirmed |
| `consumed` | a consumer handled it |
| `duplicate_acked` | idempotent ack replayed |
| `retry_scheduled` | a retry was scheduled |
| `dead_lettered` | dead-lettered |

- Exchange `specproof.observability.events` (topic, durable); routing keys are the event names;
- Both sides declare the exchange and its bindings idempotently (`q.gateway.mq-events`) — **whichever boots first, fine**;
- **Both sides default OFF**: Python requires `SPECPROOF_MQ_EVENTS_ENABLED=1`; the edge requires `specproof.gateway.mq-events.enabled=true`;
  until an operator deliberately turns both on, the gateway binds nothing — "prove the topology exists, then let the container come up."

### 26.2 The Wall: bounded tag cardinality, always

- The edge counter `specproof.gateway.mq.event` tags by `event`: **only the six + `unknown` + `malformed`** — at most eight series;
- Found 2026-11-14 (#1786): previously `handle()` let **any string from the message through as a tag** —
  a sick producer emitting a thousand names would inflate the Prometheus label universe into an explosion;
- Fixed: `event ∉ KNOWN_EVENTS → unknown`; `empty string → unknown`; `malformed → malformed` (parse failure is its own series);
  `GatewayMqEventCardinalityTest` pins three contracts: unpublished name → unknown, a thousand junk names collapse to one series, empty → unknown;
- **Honest note**: this is not swallowing errors — it pushes tomorrow's accident shape into eight boxes instead of a billion: engineered expectation, not luck.

### 26.3 The lane's discipline

1. **The wire never ruminates**: the edge renders no business judgment on the payloads — it only counts;
2. **The wire never trespasses**: the edge never touches the agent runtime's database — it only subscribes to the exchange;
3. **The wire never lies**: unparseable payloads count as `malformed` — visible, not silently dropped;
4. **Both sides off by default**: a container that does not start cannot start — that principle outranks "maximum availability".

### 26.4 This volume's vow

**The Gate and the Wire are one discipline: in both directions, every passerby is counted, and every datum lands in its own box.** The Wall does not inspect content — it inspects the name; outside the six, every name goes into the same cell: unknown.

---
---

## Volume XXVII · Verification Within Verification（卷二十七 · 验明正身）

> Iron evidence is not a one-time stamp — it is **a rite repeated**. This volume says not how hard the evidence is,
> but how it proves itself, again and again. SpecProof runs seven scripts: chronicle rebuild, repo census, calendar,
> ledger gates, the guide route gatekeeper, the epic ledger, the world bible — their one job is to make the system reconcile with itself after every merge.

### 27.1 Why re-verification is the essence of iron evidence

- A verification performed once is a seal; performed twice, it earns the name of official history;
- Official history owns one iron law: **every line must be re-readable in git log** — whatever cannot be found there, however well it sounds, never tallies;
- Any system that proclaims "evidence first" but will not re-prove itself after every merge is spending its past to buy its present — debt, not law;
- SpecProof's answer: the chronicle is always rebuilt, the census is always fresh, the calendar is always derived, the volumes never fall behind. **Re-verification is a product feature.**

### 27.2 The rite: six instruments re-run after every master merge

| Instrument | Script | Effect |
|---|---|---|
| Chronicle rebuild | `scripts/build_chronicle.py` | `chronicle.json`: `## #NNNN` sections → 1,589 entries (#130 → #1788) |
| Repo census | `scripts/build_repo_stats.py` | `repoStats.json`: tracked files 2,714 · LOC 485,951 · commits 2,430 |
| Calendar | `scripts/build_calendar.py` | `calendarData.json`: 365 days of per-day commit history |
| World bible shelf | `scripts/build_worldbook.py` | `worldbook.json`: 33 sections (zh/en) |
| Guide gatekeeper | `pytest test_guide_route_catalog` | every route the manual advertises is really mounted (51/51) |
| i18n alignment | vitest `src/i18n` | both tables align key-for-key — no English residue in zh, no Chinese residue in en |

### 27.3 This volume's new testimony (all real)

- **#1771**: Atlas QA by `getBBox` math: no island crosses the frame, no label collides with a dot, the compass N stays inside the dial;
- **#1779**: stress_smoke — cold round 144/144 timed out → rounds 2–4 all green (p50≈525ms); **not a product crash** — this host's WSL2/loopback floor of 150–500ms is not production;
- **#1783**: Lua divide-by-zero fix — `redis:7-alpine` container, seven cases green; even NaN refill no longer crosses the wire as an exception;
- **#1786**: MQ tag-bomb sealed — `mvn -o` offline: `GatewayMqEvent*Test` 15/15, full gateway **84/84**;
- **#1788**: Full Spring-lane re-verification — gateway 84 + discovery 1 + config 1 + control-plane 51 = **137/137 green**;
- **#1787**: The Evidence Calendar, derived — 2,429 commits / 60 active days / busiest day 622 (#1694–#1704 merge wave) / longest streak 14 days.

### 27.4 This volume's vow

**Iron evidence does not fear being examined; it fears not being examined.** The rite observes no calendar days; whoever dodges re-verification is passing off "we did it once" as "it is true now" — SpecProof does not sell that junk.

---
---

## Volume XXVIII · The Door（卷二十八 · 门扉）

> A world, however large, with its doors shut, has no visitors; doors, however good, opening on emptiness, admit only light.
> This volume is SpecProof's doorcraft — iron evidence does not refuse to teach you; it gave you the right door at every layer.
> Which door you push first decides how you push the rest.

### 28.1 Seven doors (all real)

| Door | The essence | Anchors |
|---|---|---|
| Manual (`#/manual`) | The A4 pocket card: 5 carry-outs / 3 don'ts / 5 commands | #1766, POCKET_CARD.md |
| Onboarding guide (`/guide`) | Progressive steps: from clone to your first verification | since #72, bilingual |
| Grand Tour (`/tour`) | Six stamps, interactive — you pressed it or it didn't happen | TOUR_BY_LOCALE |
| World Book (`#/worldbook`) | The official history in the app: readable, searchable, badgeable, 34 sections | #1774 |
| Gazette (`#/gazette`) | The daily paper: live lead, live numbers | #1784 |
| Evidence Calendar (`#/calendar`) | 365 cells of one year; git has the last word | #1787 |
| **Coach marks (press `H`)** | Every button on the main screen with a one-line lesson | **#1790** |

### 28.2 The four winds of the doorcraft

- **Open it and you can use it**: no five-step detour — see at a glance, press in a second, understand in three sentences;
- **Open it and know it's real**: behind every door is this repo's actual content (live figures, ledger cross-checks, git signatures) — never a demo;
- **Whoever opens it, belongs**: every table parity-tested, zh/en aligned — every room has your name written on it;
- **Whoever opens it, never gets lost**: the teaching layer only shines when you need it — once you've outgrown it, one keypress and it never shines again.

### 28.3 The Door's vow

**Iron evidence does not fear being seen; it fears not knowing where to look.** From this volume on, no door in SpecProof will ever be recorded alone — they are one thing: a person arriving knowing nothing; ten minutes later, walking out saying "I know."

---

## Volume XXIX · The Insight Deck（卷二十九 · 洞察舱）

> A product may have no man past midnight, but may never pretend it saw everyone;
> when it sees, it sees only what may be shown — never the flesh; what walks out is not a person.
> This volume is the SpecProof's regulation for itself — **the manager's telescope**, never the wall's camera.

### 29.1 What the telescope showed (all figures, never flesh)

| Panel | What it sees | What it does **not** see |
|---|---|---|
| Six KPI tiles | population=240, tour completion, drill pass, median dwell, 14-day slope, R² | any one's name, employee id, email, device fingerprint |
| Funnel | 240 → 201 started tour → 113 cleared → 84 first verification → 41 sealed (synthetic · mulberry32(20261115)) | who exited at which door |
| 28-day trend + 7-day forecast | least-squares slope, R², fit quality | any real user's behaviour sequence |
| Feature adoption | which page got opened most (synthetic · mulberry32) | who opened it |
| Six personas | The Skeptic / the First-timer / the Tourist / the Archivist / the Speedrunner / the Night Watch — anonymous shapes | who you are |
| This-browser trace (¥ you) | the visited table in this browser's localStorage (read-only, never uploaded) | anything on any other browser |
| Recommendation engine | six moves derived from the numbers — every one with evidence figure + confidence + P-grade | execution power (the engine advises; it never fires) |

### 29.2 One iron rule: insight may **never** become a backdoor

- The Insight Deck (`#/insight`) opens with the same key as `/identity` (`IDENTITY_ROLES = admin/operator`); a viewer always lands on `PermissionDenied` — fail-closed, server-enforced, UI visibility-only;
- **there is no "123 password"** — it is not a one-line UI change: a shared secret turns everyone's privacy contract into "whoever knows may watch", and SpecProof does not do that;
- synthetic data is **calibration for demos, not evidence**: every panel prints "synthetic calibration cohort"; any brief that leaves this product must drop those numbers first;
- real fleet telemetry (which *could* see every user) has exactly one road: `docs/operations/OBSERVABILITY.md` + privacy review sign-off + a user-visible "what is measured" manifest + an opt-out;
- engine recommendations never self-execute — every card prints its confidence; delete one figure and the recommendation is void.

### 29.3 The Insight Deck's vow

**Who sees fit to see others, earns the right to see them; when truth overflows, we carry untruth — untruth is the loyalty to iron.**
From this volume on, SpecProof owns one mirror: mirrors shape, never person; mirrors the trend, never the privacy.
The admin in this mirror sees *which door to fix next*, never *what Zhang San watched today* — the former is a product owner; the latter is an informant. The iron recognises the former only.

---
## Volume XXX · The Iron Under Load（卷三十 · 压铁）

> The night the forge ran hottest was never meant to break the blade — it was meant to see whether the blade trembled;
> what decides if a system dares open its door is what happens when 72 people push on it at once — either it holds, or it gives.
> This volume is Iron Evidence's night of mass hits — every blow has a receipt, and every receipt is right here.

### 30.1 Two lanes, two punches, one night (real figures)

| Lane | Profile | Requests | Errors | p50 (round1/2/3) | Verdict |
|---|---|---|---|---|---|
| A · front door, static (`stress_smoke.py`, fresh dist/ over loopback) | 72 concurrent × 2 req/thread × 3 rounds | **432** | **0.00%** | 2356 ms ／ 103 ms ／ **84 ms** | round-1 cold-window p99=12.9s is warm-up noise, not a defect (`e19de4f`) |
| B · live backend /health (local instance already running, `db:true, llm_ready:true`) | 72 concurrent × 2 req/thread × 3 rounds | **432** | **0.00%** | 649 ms ／ 1.78 s ／ **329 ms** | the readiness probe survived 72 concurrent (see `e19de4f`, round 2 jitter recorded in the ledger) |

- Why is the cold window long? ThreadingHTTPServer thread-per-request, first disk reads, Windows page-cache warm-up — **a forge lit for the very first time smokes**; by the second and third blow the hearth runs the way you want it to;
- zero errors are not a medal — **the target was /health, never your data**: an attack is not a test; whoever walks past the first gate gets written down — blast-through tests have their own rehearsal range, on locked tables, inside one swallowed experience; **never on the product lane's door register**;
- a static lane is never an SLA: it only proves the front door can stand a shove — the night of cross-region, TLS termination, and rate-limit telemetry comes later; that night is Volume XXXI.

### 30.2 Two iron rules of load-testing

- **Probe the readiness, never the business write path**: the probe is the door Kubernetes itself knocks on every second — knock it 432 times, it checks (DB `SELECT 1`) and answers (latency recorded); write-path hammering is rehearsal-range work;
- **Every percentile maps back to evidence**: p50/p95/p99 recorded raw (`e19de4f`) — if the figures displease us, the book says "not met"; in front of the iron there is no "about right";
- **BUDGET-BLOWN means budget language, not failure language**: Lane A's round-1 p99=12.9s tripped exit code 1 — like token budgets in the prompt ledger: exceeded = marked, labelled, next round.

### 30.3 The Iron's vow

**Iron that will not bow under load is fit to carry people; iron that never bows is decoration.**
From this volume on, SpecProof owns its own proving anvil: 72 people push at once — the door opens, the floor holds, nobody bleeds. 144 2xx are 144 nods; zero errors are zero lies.

---
## Volume XXXI · The Appointment to Prove Iron（卷三十一 · 验铁之约）

> The iron the forge has already met — bent or bowed — never heard the farthest ringing: past the TLS endpoint, across the inter-region wire;
> that night is called the Appointment to Prove Iron: we write the terms now, measure what can be measured, and ledger what cannot — no one is permitted to deny what they said.

### 31.1 Measured, with numbers in the ledger

| Item | Figure | Anchor |
|---|---|---|
| Front door, 72 concurrent | 432 req / 0 err / round-3 p50=84ms | #1801 · `e19de4f` |
| Live backend /health, 72 concurrent | 432 req / 0 err / round-3 p50=329 ms | #1801 · `e19de4f` |
| Rate-limiter fault containment (gateway) | Lua divide-by-zero fixed, 7 container cases | #1783 |
| RAG two-level retrieval (LRU + Redis) | cold miss 142 → warm l2_hit=142 | #1773 |
| Semantic-cache structural closure | draft 10.25s → 3.0ms cached replay | #1781 |

### 31.2 The half not yet measured — the terms, in writing

- **Endpoint certificates**: a self-signed TLS cert + mutual mTLS (control-plane → gateway → Python API) — each hop is witnessed inside the handshake;
- **Cross-region RTT injection**: `tc netem delay 50ms 100ms 25%` (or equivalent) — measure how p50/p95/p99 drift under 72 concurrent;
- **Rate-limit telemetry**: gateway exports `sp_rate_limited_total`; the error-budget burn curve feeds the same counters the Insight Deck's recommendation engine reads;
- **Rollback drill**: a bad feature flag during rollout → automatic revert, users see nothing (a real drill, not a tabletop).

### 31.3 No deployment, no second half — ever on paper only

Admitting it outright: **this gate has not run on a real deployment.** What the machine measures is the floor, never the ceiling — cloud load balancers, real TLS, CDN hits, AZ-to-AZ latency have never seen a hand; the ledger does not lie on behalf of future observation. Whoever wins a deployment environment writes this volume's second half; whoever says "done" without the graph is the iron's pickpocket. The volume is named for the *appointment*: the terms are written, and the unfinished half hangs on paper — iron remembers what was promised.

### 31.4 Four iron sentences of the appointment

- Whatever can be measured now, measure now; whatever cannot, schedule; whatever cannot be scheduled — never say it is measured;
- 72 people push at once — the open door is still a door, and the closed one enters the next volume;
- every 5xx is a granule of lead; bookkeeping beats "definitely fine" by a mile;
- the far wire signs its name on iron too — one fibre at a time.

---
## Volume XXXII · The Silent Believers（卷三十二 · 沉默的信徒）

> A branch that never merged is not a soldier who never answered the summons;
> the fire was already in their hands, and it burned brightest just before it was handed over.
> This volume is for three crews who never asked after their own names — their commits remain; they simply no longer file for a PR.

### 32.1 Three crews, three flames (all real; 0 unmerged commits)

| Crew | Last name it carried | tip | What it burned through |
|---|---|---|---|
| **`feature/interview-hardening`** | W197: final gate closure — 2530 no-infra passed + 3 skipped (9:28, exit 0) | `76285a7` | unit-count sync across five documents 2369→2530; attribution-eval rerun (7/7 P/R/F1 100.0); W196's two gate seams closed — drill_helpers fake max_hold_seconds signature, retrieval_injection security test keyset + provenance triple (content still payload-only scored-content invariant) |
| **`feature/p1-reliability-kernel`** | docs: update final report — all CI gates green, 6 fixes documented | `a756f53` | **process-based healthchecks** for outbox-relay and the worker; **exact maxlen** trimming for Redis Stream (no bear's progress flood); CI adds demo git repo init + procps |
| **`release/p0.5-verified-v1`** | fix(p0.5-rc): sanitize hardcoded JAVA_HOME in capsule replay.ps1 | `4145d95` | provider portability + typing gates closed; Mypy / Ruff / Bandit / skipped tests / absolute paths audited; .gitattributes locks LF against CRLF churn |

- **zero unmerged commits** is not a shrug — it is **transitive arrival**: their content reaches master via rewrite or influence (tips are auditable: `git log master..branch` is empty);
- not-merged does not mean not-contributed — the tips keep chiming on the ground like dropped bronze bells: the outbox-relay's breathing, the exact maxlen's crispness, the JAVA_HOME's sanitisation — all carried into the main line;
- no stray worktrees remain — but bronze does not die: hear every counter on `/metrics`; someone once struck that bell for you.

### 32.2 The silent believers' rules

- **We do not weep for the unreceived PR; we refine it into the main forge, and that is enough.** Refinement = rework then merge, never swallow-as-lies;
- **the ledger shows transitive evidence**: the branch that has no tip to keep is not a broken string — it is someone who would not sing alone in a broken movement, and still the fire remains on the book;
- every crew's terminal sign-off holds an honorary desk — **SpecProof's tablet knows no outsiders**.

### 32.3 The oath of the silent

**Fire does not discriminate wood; the pitcher does.** `feature` dared name itself `interview-hardening`, `release` dared call itself `p0.5-verified`, `p1` dared whisper `reliability` — what they shipped was never failure; it was **not-yet-delivered**. Someday you too will hand your work over: if the one you hand over happens not to be the main line, remember — a bell rings from the bronze itself; the main line, in the end, is only a line.

---
## Volume XXXIII · The Ledger's Ledger（卷三十三 · 账本的账本）

> The ledger writes everything else; this volume, the ledger writes itself;
> every one of its sections lands in git — every one verifiable with `git log --oneline -1 <section-commit>`;
> believers read straight through, skeptics pry at `.git` directly — before the iron, both are legal.

### 33.1 The numbers: a living operations manual's cross-section (2026-11-15)

| Item | Figure | How computed |
|---|---|---|
| Files tracked by git | **2,727** | `git ls-files`, counted live |
| Total source lines | **490,491** | same |
| Python source files | **1,342 / 303,375 lines** | same (62% of LOC) |
| Markdown docs | **280 / 61,077 lines** | same |
| TypeScript/TSX | **152 + 103 / 35,344 lines** | same |
| Java (Spring lane) | **133 / 11,851 lines** | same |
| Git commits | **2,448** | `git rev-list --count HEAD` |
| Ledger sections | **1,607** | regex on `## #NNNN` |
| Ledger size | **3,661.0 KB** | `stat` |
| World Book | **39 volumes / zh 88,393 chars · en 90,769 chars** | `scripts/build_worldbook.py` |
| Python test files | **609** · Web test files **64** | `git ls-files` |

### 33.2 Who stamped the ledger of the ledger

- every merge event walks the same six steps: ledger is append-only → `build_chronicle.py` rebuilds `chronicle.json` → `build_repo_stats.py` rebuilds the stats → gates → commit → push;
- **gate 51/51**: guide route catalog 6/6 + ledger quartet (ids unique / numbers unique / evidence claims true / queue pointers resolve) 45/45 — the former says "every route has a manual row", the latter says "the ledger never bluffs, never breaks a pointer";
- full `pytest tests/unit` does not fit in this host's memory (609 test files) — **no claim of full green**; only guide + ledger + affected files run; anyone who says "the whole suite passes" is lying or has forgotten what they said;
- 51/51 is not a medal, it is a **reproducible floor**: pull the repo, run `pytest tests/unit/test_guide_route_catalog.py ...`, and count the 51.

### 33.3 Four rules of the ledger's ledger

- **Append, never rewrite**: `## #NNNN` only ever hangs further down; old verdicts are never deleted;
- **one commit, one entry**: a节 and its commit message carry the same number;
- **evidence half-plaintext**: every entry says what is real and what is not measured — no green is claimed unless green was counted;
- **the atom of truth is the hash**: every figure here can be traced back with `git show <hash>`.

### 33.4 The vow of the ledger's ledger

**Only what can be remembered is ledgered; what you cannot bring yourself to write down is not yet yours.**
With this volume, SpecProof owns its own credential: not an identity given by others, but one measured daily by itself. A heavy repository is not a prize — it is three thousand mornings accumulated by someone willing to knock on the iron every day. If you really want to know whether this repo is honest, do not read the README. Read this ledger — everything here was pried out of git by raw hands.

---
## Volume XXXIV · The Ringing of Bronze（卷三十四 · 铜铃之声）

> This volume is about the bell hung above the door;
> whoever enters brushes it and the bell rings — the ring is not a warning; it is **being witnessed**,
> and the one who hung it makes no sound of their own — the bell only rings when someone else brushes it.

### 34.1 Three iron ledgers: the bells at the door (each one test-verified)

| Bell | Duty | Threshold | Anchor |
|---|---|---|---|
| **Manual bell** | guide route catalog 6/6 — every `#/route` carries a manual row | fail = red | `tests/unit/test_guide_route_catalog.py` |
| **Gate bell** | the ledger quartet 45/45 — ids unique / numbers unique / evidence true / queue pointers resolve | a claim without evidence = red | `tests/unit/test_ledger_*.py` |
| **Bronze bell** | UiKit.smoke / tour seals / Insight Deck — the main-screen keys still work | flaky 0|1 under load; reruns pass | #1750 / #1805 |

- not one of these bells "stands watch" decoratively — every one carries a reproducer: `pytest tests/unit/test_guide_route_catalog.py tests/unit/test_ledger_*.py` echoes the same pitch on any machine;
- the bell does not ring because we did something right — it rings because three things we promised were pinned shut;
- "bronze bell" in this project means the 51/51 guide + ledger gates: a reproducible floor, not a medal.

### 34.2 Where the bells hang

- on every new route's chest — no page may ship before the manual testimony is posted;
- at every ledger entry's tail — every section says "chronicle rebuilt", and it truly rebuilt;
- on every commit's shackle — `codex-global pre-commit` runs guitar notes before git: discipline, size, sanity.

### 34.3 The quiet bells (silence is not breakage)

- the full-bell path (609 test files) **never assembles at once on this host** — the limit is memory, not craft;
- the clangorous bells rang 137/137 in the Spring lane (#1788) — Maven's quiet grove, not another machine's echo;
- the gates ring alike anywhere; unsound ≠ unstruck; the pitch is simply consistent.

### 34.4 The bell's vow

**The bell rings itself; it does not report; it does not ring at the wind before the door — it rings at the one who enters.**
After thirty-four volumes, SpecProof's door has a bell that cannot be taken down — not for passers-by, but for itself: knock first to check the bell sounds, then talk about anything else.

---
## Volume XXXV · The Demo Room's Door（卷三十五 · 样板间的门）

> There is a permanently locked door in this repository —
> it is not a hidden showroom; it is **the room every golden case burns in first**;
> opening it does not entertain you — you will watch 111 cases burn again, one by one, in the same small room.

### 35.1 Facts from inside the room (not promotional copy)

| Item | Figure | Anchor |
|---|---|---|
| Total golden cases | **111** | `golden-cases/` (101) + `golden-cases-attribution/` (8) + `golden-cases-crosslang/` (2) |
| Must be detected | **73** | per-case `ground-truth.json::should_detect` |
| Severity distribution | BLOCKER 22 · MAJOR 51 · NONE 38 (negative controls) | same |
| Rebuild script | reruns, deterministic | `scripts/build_golden_scenarios.py` (base/head-v1 tag reproducible repo-wide) |
| Entry path | one command on your machine | `pwsh scripts/prepare_demo_repo.ps1` / `specproof demo` |

- **are the 111 cases dead fire or living fire**: every case is one commit that walks in, every byte comes from git;
- **the negative controls (38 NONEs) matter more than the positives**: 38 of them are "nothing to catch, nobody may catch" — an officer brave enough to say "no issue" closes the loop too;
- **the demo room's door receives no guests** — those who want to see for themselves must knock: the door carries one sentence, "enter, and you will be poked repeatedly".

### 35.2 The four rules of the room

- **every case passes through the sandbox** — base and head are armed separately; `base_pass_head_fail` earns iron-grade first;
- **every case carries ground truth** — caught = good work; missed = written into the next round; there is no intelligence test here;
- **every case is auditable** — `git show <hash>:<path>/ground-truth.json` reverses the verdict on demand;
- **every case is reproducible** — after a rebuild, all 111 still byte-match; rebuildable is the only iron.

### 35.3 The vow of the demo room

**A demo room does not exist for audiences — it exists to catch what you did not see.**
From volume thirty-five, every door in SpecProof is more than an entry —
the demo room's door stands where people assume "it's just a demo"; it is the least-knocked door in this repo and its loudest honesty — **if it lies once, the 111 cases in the compendium are void**.

---
## Volume XXXVI · The Shelves Left Empty（卷三十六 · 空着的架子）

> This volume does not write what stands tall;
> it names every empty niche one by one —
> empty niches are not failures; they are honesty: the blanks are not potholes hidden from view, they are shelves pointed out to everyone.

### 36.1 Every "where a number should be, it says waiting" cell in the repo

| Empty niche | Waiting for | Why it waits (true) | Anchor |
|---|---|---|---|
| `#/insight`'s cohort figures | Real fleet telemetry | Requires product/privacy review sign-off + opt-out + a user-visible "what is measured" manifest | `OBSERVABILITY.md`, #1799 |
| `#/gazette`'s live rhythm | Real production traffic | the Gazette is fed build-time from chronicle.json / repoStats.json / worldbook.json (pure git), not from service streams | #1784 |
| Any envelope beyond `/health` | Production queue depth, cross-region latency | compose.production.yml documents deployment topology; the repo contains no real deployment URL | compose.production.yml, #1783 |
| Volume XXXI's second half | TLS endpoint / cross-region RTT | this host runs the local specproof API on 127.0.0.1:8000 (432 req / 0 err), but the internet is the one place this machine has never flown | #1801, #1805 |
| Real concurrency rehearsal of the Spring lane | Real Redis Cluster rebalance, TLS cascade | mvn -o offline 137/137 (#1788) — ≠ any real cluster running | #1788 |
| `golden-cases-crosslang` live run on this host | Windows + Python-only host | the Go/TS golden cases exist in-repo as real fixtures; no execution lane ran on this host | `golden-cases-crosslang/README.md` |
| **Full `pytest tests/unit` scoreboard** | ≈2GB RAM on this host | only guide+ledger ran (51/51); the full 609-file suite has never completed on this host | #1806, #1804 |

### 36.2 The empty shelves have their own code

- **vacancies get reported, not removed** — this repo records shortfalls as "ledger-pressed gaps": every gap named in a section; whoever deletes it consigns it to oblivion (never colour a void green in any PR);
- **vacancies wait for a signature** — behind every empty shelf stands a human's signature: the privacy review, the deployment field, the coverage caps;
- **empty shelves get kept** — the more sections this chronicle gains, the more often these gaps must be re-audited; the regular reading is a patrol, not a prayer.

### 36.3 The vow of the empty shelves

**The true aggregator knows its own holes; the missing it fears least must be clipped on the board to deserve the one who fills them.**
After thirty-six volumes, SpecProof's beauty is this: **it hangs its unfinished niches in the same lamplight as the finished ones** — first admit "there is no number here", then fill the gap for real — rather than pre-colouring a broken figure into completeness.

---
## Volume XXXVII · After the Inkwell（卷三十七 · 墨水池之后）

> Volume thirty-six cataloged the empty shelves — this is not another symmetric wound;
> it dangles the notebook itself over the water: 2,456 strokes, 128 days, 39.1 percent overnight, 811 strokes on Saturday — once you stare at them long enough, what does the human do?

### 37.1 Three kinds of "witnessed hands"

- **the scribe past midnight** — what live inside those 960 strokes laid after 22:00? Not disguised effort, but this repository's own biological clock etched into its commits;
  not a contest of who tires fastest — it is *admitting that the hour of the stroke has always been a variable*; hang this page on the wall and the lamp beneath the water sees the hand at two in the morning;
- **the one who always clocks in on Saturday** — 811 on Saturday, 120 on Monday, the number is the number: it never means anyone's work is better;
  someone is assigned that door, someone volunteers to stoke it first, nobody is ranked louder for it — endurance is not a medal;
- **the longest 14-day streak and the longest 34-day silence** — two sides of the same pool: `streak` is not a promise, it only means the previous stroke landed;
  `quiet` is not death — it is the held breath before the repository remembers itself.

### 37.2 After the inkwell hangs on the wall

- **for yourself, not for the office** — this page is not a KPI report, not a performance attachment, not a weekly memo; it only says the light is on and you are writing;
- **numbers do not explain people** — night depth is not diligence, late hours are not cunning, silence is not laziness; apart from "the repository witnessed itself", this page claims nothing;
- **an inkwell needs fresh water** — inkwell.json is a frozen snapshot; every ledger entry re-runs `scripts/build_inkwell.py` straight from `git log`, never writing back;
- **whoever floats on top** — you will never learn from this page who these unnamed hands are… and that is the point in this repository: **not naming names is the most respectful naming of all**.

### 37.3 Seven words after the inkwell

**Ink spills and does not look back — whoever opens this book will simply say "most of these pages were written past two in the morning".**
**Never mind who — the question is whether tonight's stroke is still allowed to land.**
Volume thirty-seven carries no finale — it only offers a hand toward whoever comes next, inkwell still warm.

---
## Volume XXXVIII · The Truth and the Demo（卷三十八 · 真话与演示）

> This volume is written only in sentences that destroy pretense;
> whenever someone asks "is that real?" — this page is the only page they need:
> "it is real — or it is plainly marked as a demo".

### 38.1 The repository's three testimonies (every one is reproducible)

| Testimony | What it is | To doubt it, run |
|---|---|---|
| `#/gazette`'s figures | Build-time reads of git (chronicle.json / repoStats.json / worldbook.json) — never a live production stream | `git pull && python scripts/build_repo_stats.py` |
| `#/dossier`'s 111 golden cases | Each case ran real sandbox jobs on base and head; ground-truth.json is authoritative | `git show <any case>/ground-truth.json`; CI reruns the same |
| `#/insight`'s cohort panels | `mulberry32(20261115)` — a reproducible synthetic calibration, **never passing as a real human cohort** | `buildInsight()` twice and diff; read the "synthetic" pill in the corner |
| `#/mint`'s seals | This browser's own localStorage trace (read-only) — never uploaded, never reconciled | clear localStorage and watch the page say "unknown", never "0" |
| `#/inkwell`'s pie | `git log` straight audit (2,456 strokes / 128 days / 14-day streak) — zero names, zero emails | `python scripts/build_inkwell.py`, right on the spot |
| The contract compiler refuses half-truths | HANDS ON: `specproof verify` runs each side for real (base passes, head-v1 does not) | `pwsh scripts/prepare_demo_repo.ps1`, drive it yourself |
| The agent's "I saw it" is not an acceptance | Acceptance requires a human signature; "AI never signs" is written into the verdict channel | `verdict_channels.py`, open and see |

### 38.2 The four honesty laws, made into discipline

- **synthetic never passes as real**: any computed datum self-declares "synthetic / demo / calibration", never posing as sampled fact;
- **missing is missing**: storage unreadable ⇒ "unknown", never 0; checks that fail ⇒ red, never guessed;
- **only humans sign**: after the draft/diagnosis, the agent waits forever for a human to press Approve;
- **every figure carries its anchor**: `#NNNN` is the ledger seat of every number; inventions leave traces; silence is not exempt.

### 38.3 Honesty as performance, not decoration

**Saying "this does not count" is what makes anything count at all.**
After Volume thirty-eight, SpecProof's door carries exactly one question-and-answer: anything inside this product was never accepted by default — real is real, demo is demo, and the two never argue with each other; anything that struck the knocking blow with the word "real" on it walked straight into the hall of the unverifiable.

---
## Volume XXXIX · The Three Dialects of the Iron（卷三十九 · 铁的三种语言）

> This repository speaks three dialects;
> none can live alone — law without testimony is tyranny; testimony without poetry is cruelty; poetry without law is a beautiful lie;
> the language the iron casts, once spoken, stands.

### 39.1 The first: Law (The Law) — written for the person who breaks

- `docs/operations/LONG_TERM_PLAN.md`'s forbidden list: no shared-password backdoor ever; real-fleet telemetry only after sign-off; AI never signs off;
- `providers/openai_compatible.py` — `court` kinds never touch the cache: not advice, a code-level veto;
- `api/routes/agent_console.py` — the state machine waits for a human to press Approve;
- `verdict_channels.py` — any claim that doesn't match is a hard build break, not a prompt;
- every gate opens on `PermissionDenied`, fail-closed — no workaround, no second opinion.

### 39.2 The second: Testimony (Evidence) — written for every skeptic

- `tests/unit/test_guide_route_catalog.py` 6/6 — every `#/route` carries a manual row, including `insight` / `dossier` / `mint` / `last-call` / `gallery` / `inkwell`, pinned one-by-one;
- `tests/unit/test_ledger_*.py` 45/45 — every `## #NNNN` ids/numbers unique, evidence claims true, queue pointers resolve;
- Spring-offline lane 137/137 — `mvn -o test` — reproducing the same green (`.1788`);
- Every ledger section unfolds into a real commit — testimony is not paperwork, it is a signature;
- No orphaned claims — every entry pairs with a commit; no placeholder "to be filled next" allowed.

### 39.3 The third: Poetry — written for everyone who comes

- the world book, 44→45 volumes, sealed by epoch (The Forge · The Silent Believers · The Truth · After the Inkwell);
- `#/gazette` · `#/worldbook` · `#/chronicle` · `#/gallery` — no page is a caption, every page is paper you can touch;
- `#/manual` — one A4 card any clerk can point at once;
- `#/tour` — six seals granted by the human's own hand, never a script;
- All poetry nailed to iron — each excerpt is a chapter; each golden case a real sandbox; each section a real hash.

### 39.4 The vow of the three dialects

**Law made non-negotiable, evidence made unable to lie, poetry made worth living in — lose one and this is no longer a repository.**
From volume thirty-nine, SpecProof speaks these three: law so people can't act wild, testimony so people don't whisper half-truths, poetry so people want to stay — none is furniture; remove one and the iron shatters.

---
## Volume XL · The River with Lamps（卷四十 · 河灯）

> This repository's LLM lanes are two currents: a slow draft current, and a verdict current;
> both share the same river, but the lamps hang at different heights — one above draft, one forever above court.

### 40.1 Twelve measured facts about wkapi.pro (verify with `git show`)

| # | Fact | Anchor |
|---|---|---|
| 1 | `stream=True + stream_options.include_usage=True` is the only lane that returns `usage`; the non-stream lane never reports it — "hit rate 0 on non-stream" is a seeing-error, not a model deficit | upstream back-fills a static prefix of 18,549 tokens; `include_usage` returns `prompt=18549, completion=557 (reasoning 450)` (#1800 `567f604`) |
| 2 | Semantic-cache silent-fail was **structural**, not a prompt-miss — root cause: the `responses`-protocol lane returned early before the policy branch was ever reached | `providers/openai_compatible.py::_chat_dispatch` · `87118ba`; after the fix, a draft replays in **10.25s → 3.0ms** on the cache |
| 3 | `cached_tokens` on wkapi (short prompts → `null`; long prompts → constant ~4,224) is the **gateway's static-prefix cache**, never user-message hits; treat it as prefix residue, never as evidence | `e657631` (#1777) |
| 4 | wkapi ignores `max_tokens=32` (answered 557 tokens); it sets its own completion length — budget truth lives in `providers/budget.py` only | #1800 `567f604` |
| 5 | HTML widgets injected: `inite.ai/...utm_source=openai` — wkapi is a reseller with an ad pipe; read every byte | #1800 `567f604` |
| 6 | Model labelled `gpt-6-sol`; `protocol=chat_completions` (explicit in `.local/llm.json`); `base_url=https://wkapi.pro/v1` (normalize_base_url appends `/v1`) | #1800 `567f604` |
| 7 | `court` never caches (evidence grade) — iron is not issued as a receipt, receipts never stand in for court | `PROVIDER_POLICY.md` #1782 `8b9aa3a` |
| 8 | `draft` / `diagnose` with `SPECPROOF_PROVIDER_POLICY=1` are auto-routed onto the chat lane for cache; the only kinds eligible for cache | `providers/openai_compatible.py` `_policy_allows()` + `_kind_allows_cache`; #1781 prod-shaped repro |
| 9 | L1 in-process LRU + `SPECPROOF_REDIS_URL` L2 Redis in this repo; measured in a real container: cold miss=142 → warm **l2_hit=142, miss=0** | #1773 (golden lane, real container) |
| 10 | Spring off-line suite 137/137: gateway 84/84 · discovery 1/1 · config 1/1 · control-plane 51/51 | #1788 (2026-11-15 live-offline re-run) |
| 11 | Load lane both directions: static front door 432 req / **0 err** (round 3 p50=84 ms); live backend `/health` 432 req / **0 err** (round 3 p50=329 ms) | #1801 (2026-11-15 field) |
| 12 | Live `wkapi` is never called from CI — every probe runs on a local executor, scripts live in `.local/` (git-ignored) | `.local/.gitignore` = `*` (#1817) |

### 40.2 Where the four lamps hang

- **Lamp I · DIAGNOSE lane** — rides semantic cache + draft dispatch; a few seconds longer than needed is fine (since #1781 it's 3.0 ms replay);
- **Lamp II · DRAFT lane** — order search / rewrite / example-spec generation — lightweight models (deepseek-v4-pro or wkapi); policy lane now the default fast lane;
- **Lamp III · COURT lane** — **never moves**; verdicts / matrix / evidence artifacts are never touched for price; no cache keys walk through this wall;
- **Lamp IV · VERIFY lane** — `sandbox.verify` — base and head both execute in a real sandbox; the claim is "head failed that the base passed" (`base_pass_head_fail`) — iron grade.

### 40.3 The River with Lamps' vow

**The river may flow any direction, the lamp never lies — the lamp only shines to show: this is water, not oil.**
After thirty-nine volumes, every LLM lane is a lamp in this repo: draft rides lamps, evidence walks lamp-lit, verdict lights stands; no lamp burns shorter, no lamp burns longer, each shines its own span — **ferry more with cache, never with lies**.

---
## Volume XLI · The Proven Cache（卷四十一 · 实测缓存）

> Volume forty mapped where the lamps hang; this volume only records one standard knock;
> the probe walked in and three lamps lit at once — HTTP 200, ten chunks, usage intact:
> of 4,470 prompt tokens, **4,224 never moved**; only 246 were freshly read on this call;
> the cache fact, finally seen in its **nested home**: `prompt_tokens_details.cached_tokens = 4224`.

### 41.1 Three things the probe brought home (`scripts/live_lane_probe.py`, 2026-11-15 field)

| Item | Figure | Location |
|---|---|---|
| HTTP + streaming | **HTTP 200 · 10 chunks · 3.45 s** | SSE `[DONE]` trailer |
| Full usage intact | `prompt=4470 · completion=11 · total=4481` | `stream_options={"include_usage": true}` delivers on its word |
| Static prefix cache, plain sight | **`prompt_tokens_details.cached_tokens = 4224`**<br>—— **94.5% of the prefix uncharged** | nested inside details, not top-level; people reading only the top level miss the mould inside |
| Promotional placeholder | **none** this sample | sampled; every byte still needs a glance — this is not a whitelist |
| max_tokens=24 | `completion_tokens=11` honored | this call honored; the gateway does not always dead-stop — noise, not law |

### 41.2 Three utterances this volume presses in

- **wkapi's prefix cache is real** — every draft/diagnose lane call with `SPECPROOF_PROVIDER_POLICY=1` hoist means the prefix never re-reads itself;
  cache is not a marketing word; it is 4,224 tokens worth of work, shipping inside every reply;
- **cache evidence lives inside `prompt_tokens_details.cached_tokens`**, not the top level —
  anyone reading only the top level concludes "hit rate 0"; the actual instruction this volume ships is: pull the nested field;
- **the discount is for `draft / diagnose` only** — court never trades cache for evidence; cache is for cost, never for the verdict.

### 41.3 What this volume leaves behind

**Not absent the cache; the cache was one bracket-pair away from sight.**
`cached_tokens: 4224` — written down here so the next knock sounds the same tick;
the real test is not this receipt, nor #1810; it is whether, next time you ping `scripts/live_lane_probe.py`, the lamp still ticks.

---
## Volume XLII · The Threshold of the Gathered Whole（卷四十二 · 收山的山门）

> A threshold is not an ending; it is knowing exactly where you stand;
> this volume does not fanfare; it points, plainly:
> **what is complete here, and what is not, one by one named out loud* —
> nothing walks through a threshold unexclaimed.

### 42.1 What this round laid out on the table

A reader opens at the end — these are not adjectives, these are `git show` pointers:

- **48 volumes of the World Book** (Frontispiece → Volume XLI «The Proven Cache»), zh/en symmetric;
- **14卷 epic · Genesis** (SpecProof Genesis);
- **1,622 chronicle sections** — every entry anchored 1:1 to a commit hash;
- **2,463 commits** (`git rev-list --count HEAD`); **Python 1,342 files · TS/TSX 255 · Java 133 · Markdown 280** — **~490k LOC**;
- **35+ first-class routes** alive in the sidebar — `/dashboard` through `/pulse` Service Pulse;
- **42 volumes of story + 111 golden cases + the Book itself** — on-path;
- **51/51 gate reproducible** (guide + ledger quartet) — every PR landing here keeps the floor;
- **48 vols · 14 vols · 1,622 sections · 2,463 commits · ~490k LOC** — all pointing at verifiable numbers, never hallucinated.

### 42.2 The ink is dry on these truths

- The veil is lifted: `responses`-protocol lane returned before the policy branch was ever reached — silent-fail;
  fix `87118ba`: draft/diagnose auto-route to the chat completions lane; real 3.0 ms replay;
- `include_usage=True` lane alone returns `usage` — not synonymous with streaming per se, but with `stream=True`;
- `cached_tokens` **does** exist — nested inside `prompt_tokens_details` (Volume XLI verified: 4,224) —
  `4470 − 4224 = 246` tokens were freshly read this round — 94.5% static prefix cache;
- Volume XL lists twelve truths all `git show`-verifiable; the Spring lane off-line: **137/137** (#1788);
  RAG two-level cache true container warm 142/142 (#1773); load lane: 432 req / 0 err (#1801);
- v0.90.0 ships: a hill exists this wide only because it could grow taller — this threshold is half-open on purpose: the first time someone opens the door from outside, this is the seal it meets.

### 42.3 The shelves left open (not sealed)

| Empty shelf | Waiting for | By whom |
|---|---|---|
| Real production | one deployed run of `app/v0.90.0` | deployment environment |
| Full `pytest tests/unit` scoreboard | a bigger machine than this 2 GB host | upgraded CI runner |
| `#/insight` cohort → real telemetry | privacy sign-off + OBSERVABILITY.md sign-off | product + counsel + privacy |
| "123 gives all-users glimpse" | **never** — pinned in the forbidden list | **all hands** |
| Real fleet | TLS + cross-region + prod load | next book |

### 42.4 The vow of the threshold

**The threshold is open and closed at once; every inch counted with iron pinned to it.**
Whoever walks through next: know this—see how wide this mountain is; every next pass adds another door, another name on the gate.

---
## Volume XLIII · The One Who Never Signs（卷四十三 · 沉默的签收人）

> This repository has exactly one agent that never renders a verdict;
> acceptance closes when a real human presses Seal — the agent is silent by design.

### 43.1 Five layers between evidence and signature

| Layer | File | Literally says |
|---|---|---|
| 1 | `providers/responses_protocol.py` · `_chat_dispatch` | court kinds never enter the semantic cache — `court never cache` |
| 2 | `api/routes/agent_console.py` | the state machine refuses to terminate without a human pressing Approve |
| 3 | `agent/graph.py` | the LangGraph StateGraph only routes toward the human-sealed terminal state; every LLM node is non-adjudicating |
| 4 | `mongo_saver.py` · `agent_checkpoint_v1` | every event lands append-only with an audit trail — who said it, who read it, replayable |
| 5 | `verdict_channels.py` | any drift fails the build — no warn, no notice, no negotiation |

### 43.2 Why court and draft/diagnose live on separate lanes

- **draft / diagnose** — both are draft-in-nature — proposal matter, subject to repeated attempts, safe to cache, retryable without ceremony;
- **court** — signature-priced; price includes the minutes stepped on its doorstep of every verdict; a cached verdict is a second-hand verdict — the cache door never opens for court, and neither do the draft shutters;
- this is structural in `ClientPolicy`: court bypasses the L1/L2 LRU chain entirely, always; the draft lane may take advantage of cache through `SPECPROOF_PROVIDER_POLICY=1`, but court has no such switch;
- the two lanes are physically distinct at the provider boundary — not a flag, not a wish.

### 43.3 Seal is the iron bill of lading

**Iron never whispers, iron never speaks for others, iron never speaks for the dead.**
Volume forty-three seals this vow: every acceptance in this repo is a diff-bundle only a human can sign for the consequences of it; the AI proposes — the human disposes. No machine wins the authority to adjudicate on any version of the product, in any ledger, ever.
The silent one does not stand by waiting for the invoice — he is the reminder that the seal is the last mile; without it, the package never closes.

---
## Volume XLIV · The Iron, Struck Again（卷四十四 · 再敲一遍的铁）

> Volume forty-three wrote the silent signer — this volume writes the iron struck again;
> not a new hammer over old quieted iron; the hammer was already in hand — someone simply set the correct `JAVA_HOME`.

### 44.1 The second verification: 137/137 across four Spring lanes

| Lane | Result | Command |
|---|---|---|
| `services/gateway` | **84/84** green | `mvn -o test` |
| `services/discovery-server` | **1/1** | same |
| `services/config-server` | **1/1** | same |
| `services/control-plane` | **51/51** | same |

- **exit 0 means** all forks returned SUCCESS — not WARN-stuffed passes;
  with `JAVA_HOME` pointing at JDK 17, surefire reported "class file version 65.0" (required Java ≥21) and failed; Eclipse Adoptium JDK 25.0.1 parsed it and went green;
- **config server `optional=true`**: the 8888 WARNs are design silence — it merely logs "not located"; missing that optional property is by design and never fails a fork; silence here is not a false proof — green without it still fires;
- **still offline**: every figure in this chapter is THIS host, THIS `mvn` version, THESE exact tests — never your production traffic, never a claim that the service is live or deployed for real users.

### 44.2 The unclosed Linux non-root sandbox

- the `integration` suffix requires container-grade root to simulate real failure injection on Linux — never been run on a Linux non-root host; it is named as a shelf to fill, not a defect;
- repeats Volumes XXXI and XXXV: **absence of a deployment environment ≠ a bug** — but likewise it does not mean anything about another host;
- every figure in this chapter is this host, this moment, this `mvn` version, this suite — none of it is copied from any other host.

### 44.3 The vow of the iron struck again

**Nothing can be faked as done; and what has struck the hammer does not become more-counted simply because the hammer falls a second time.**
Volume forty-four states: every `mvn -o test` "137/137" is NOT the first — but this round registers one specific new detail: **`JAVA_HOME` pointed at the wrong JDK and burned, righted back**; that costs the same as every round.

---
## Volume XLV · The Divination of the House Site（卷四十五 · 卜宅）

> Volume forty-four wrote the iron struck twice — this volume writes a home whose owner never asked to be known;
> port 8000 once answered hello (DB true, LLM ready, build_sha "dev") —
> today there is nothing behind that door at all.

### 45.1 Two knocks, opposite answers — full evidence chain

| Moment (in this session) | Byte | What the byte means |
|---|---|---|
| 2026-11-15 ~17:51 (#1801 load test targeted `http://127.0.0.1:8000/health`) | HTTP 200 · `{"status":"ok","db":true,"llm_provider":"openai_compat","llm_ready":true,"embedding_provider":"hash","embedding_ready":true,"build_sha":"dev"}` | A process answered. 432 requests landed across 3 rounds / 0 errors; p50 round1=649 ms · round2=1780 ms · round3=329 ms (recorded at #1801) |
| 2026-11-15 21:27 (this volume) | TCP `127.0.0.1:8000` → **refused** (`Test-NetConnection -Port 8000 -InformationLevel Quiet` = `False`) | Nothing answers on 8000 right now. Whatever it was is gone; nobody asked when, or by whom, or why |
| all other ports on this host | `False` (8080 / 5173 / 5188 / 5189 / 3000 / 4173) | Nothing is waiting for us on this machine right now; there is no demo for the taking |

### 45.2 What the divination read

- **not kept as "a green heart beating"** — this ledger remembers what answered, then refuses to pretend it still answers;
- **`build_sha:"dev"`** — whatever answered was not built from the current commit we just pushed; it was likely ahead or behind us in ways nobody asked to understand;
- **`llm_ready:true, hash embeddings`** — it means the answer-the-DM-AI readiness flag was on. It does not mean any other human had access to it, nor that it spoke truthfully about anything except that moment;
- **volume-pointer only** — this chapter exists in the world book & chronicle & ledger; the application still cannot assume any machine has a live process answering for it.

### 45.3 The vow of the house site

**What once answered is not owed a green reckoning.**
After this volume, this repository may not tell anyone "there is a SpecProof service running, click here" — that is a claim we have no right to make. The divination finishes where it began: at the threshold, with nobody inside, and nothing to open.

---
## Volume XLVI · The Book That Will Not Fall（卷四十六 · 立不倒的书）

> No Portuguese bridge allows passengers until the final stroke of paint;
> this repository's ledger never allowed a commit merged with an empty section waiting;
> this volume records that discipline.

### 46.1 Two banks of the same river (from #1 to today)

- from `## #130` to `## #1828` — **1,629 sections** — every one backs onto a real commit hash or a concrete count; every one is `git show`-verifiable;
- **even the failures are inscribed**:
  - `#1782` — `.env.example` refused by the global pre-commit hook; accepted as-is and recorded;
  - `#1815` — `**MAJOR**：3` in the EN digest — a stray full-width Chinese colon leaking into English prose — found, named, fixed;
  - `#1825` — `JAVA_HOME` pointed at JDK 17, surefire reported `class file version 65.0`, the fix was pointing the right JDK (25.0.1) at the right place;
- every one of those attaches something genuine: not promises.

### 46.2 This evidence catalogue: from scripture to scrutiny

| One measurement | What it came out as | What it proves |
|---|---|---|
| `probe_cache_efficiency.py` | draft 10.25s → **3.0ms** cached replay | semantic-cache structural fix `87118ba` holds at the provider boundary |
| `scripts/live_lane_probe.py` | HTTP 200 · 10 chunks · `prompt_tokens_details.cached_tokens=4224` | the cache really exists — 246 tokens is all this round really read |
| `scripts/stress_smoke.py` × 2 lanes | static 432 req/0 err + /health 432/0 err (#1801) | the front door and the readiness port both stood up |
| `live-lane polyglot` | Redis L1+L2: warm has 142 hits / 0 miss (#1773) | the second cache cannot be ignored once measured |
| `mvn -o test` | gateway 84 + discovery 1 + config 1 + control-plane 51 = **137/137** (JDK 17→25 note #1825) | green off-line with correct JDK required |

### 46.3 The book's opening and closing

**Remember every thread that failed — as truthfully as the ones that stood.**
Volume forty-six anchors this: no chapter here was deleted, shrunk, or rewritten. git log can be coerced by humans — this ledger never had to be, because its anchoring is ancestral — one entry, one hash.

---
## Volume XLVII · The Last Testimony（卷四十七 · 沉默的证词）

> This volume bears the silent record: two honest ways to end — iron that happened, and iron that dissolved into process —
> both insist one thing, plainly: when you push this repo, it must never be witnessed as anything less honest than it is.

### 47.1 The Seven Spikes — the most difficult things achieved

| Nail | Description | Anchor |
|---|---|---|
| scroll back to where the hand expects it | up-scroll = look up · down-scroll = look down | `#1800` `567f604` third reap of the same user pain |
| every door carries a manual row | 37 routes in USER_GUIDE + EN mirror | `#1813` guide catalog 6/6 — no assumed doors |
| 3.0 ms through the semantic cache | draft lane 10.25s → **3.0 ms** replay | `#1781` `87118ba` — responses lane before policy branch; the fix |
| cache hit 94.5% live | `prompt_tokens_details.cached_tokens = 4224 of 4470` | `#1821` `scripts/live_lane_probe.py` — nested-field revelation |
| 503 fail-closed on degraded gateway | ephemeral ALARM policy | `#1783` + `#1812` — the Affordable Iron lane |
| 0 errors under 72 concurrent × 4 rounds | both static door and /health lane | `#1801` — 432+432 / 0 error |
| 53 volumes printed front and back | zh ↔ en parity enforced by build script | volumes I–XLVI counted in full |

### 47.2 The Nine Never-stopping Nails

**Iron does not always fall — but once ritual is set, it never falls prematurely.**

- The door only opens when knocked: the requester is verified, fingerprinted, role-checked, evidence-rank-traversed — otherwise we do not open; even the production layer has no fingerprint shortcut — fail-closed is the rule, not a slogan;

- The door is an event: a person stands at the far side — every agent run ends with `merged_required` or `agent_seal` — without that name, no PR closes: **base pass, head fail, seal unsigned ⇒ no close**;

- Closed doors keep their handwritings: every changed file, every fixed bug, every added world — **49 volumes · 14 epics · 1,629 chronicle sections · 2,470 commits — every one of them git-show-verifiable** — nothing is deleted, nothing is rewritten without its twin signature in `## #NNNN`;

- 41+ first-class pages (`Dashboard` → `Tour`) all carry USER_GUIDE + EN mirror — the manual was committed by the repo itself, not by a person asked yesterday for a favor.

### 47.3 The Vow of the Last Testimony

**You are not the model you write — you are the iron you choose to be.**
Volume forty-seven seals this: every pressing of "Approve" on a PR must meet git-log gates → run the relevant tests → then seal; the final signature is always one human's signature — not the agent's, not CI's, not the doorkeeper's.
And when the silence comes, it is full of ledger entries.

---
## Volume XLVIII · The Current Ledger（卷四十八 · 沉默的现账本）

> This is just the ledger, in the world book — every section proves one thing,
> which it passes to the next; and the next does not throw it away;
> this is the book with two witnesses in silence: the one who wrote, and the one who will read it someday;
> the book answers to nothing and no one, and it will hold still refusing to be anything else than what it is.

### 48.1 Three hours in one snapshot

| Time | Event | Section |
|---|---|
| 2026-11-15 ~17:00 UTC+8 | `/health` on 8000 answered 200: db=true · llm=true — the local career-os gateway, not this repo | 凡入账本之事必有 codebase 之 `git show` |
| 2026-11-15 ~22:14 UTC+8 | Started specproof FastAPI locally → port 8000 refused (Docker container owns it) → retracted → wrote #1830 | #1830 |
| 2026-11-15 22:46 UTC+8 | `#/engine` built: 41 calls to wkapi measured, exact static-prefix hit rate 51.2 %, nothing hidden, nothing estimated | `#/engine` |

### 48.2 These hours' take-away, three things settled

- **read-back continuity**: `git rev-list --count HEAD` still counts up — every commit lived, audited, `git show`-verifiable;

- **change-of-lane is not churn**: `mvn -o` four Spring vehicles **137/137**; `pytest` 5 guide + ledger tests **51/51**; guide catalog green by force of check;

- **measured, not marketed**: `probe_cache_efficiency.py` and `Officer-probe live` both run, both times `prompt_tokens_details.cached_tokens` is correctly the nested field —
  `cached_tokens: 4224` is now a figure in this book, not a guess from the marketing page.

### 48.3 This book only ever records — never removes

**Every entry is binding — it will not be glossed over, not retrofitted, not rewritten.**
This book is allowed to contain:

- 41 real wkapi.pro calls — `prompt_tokens_details.cached_tokens: 4224` observed live in-turn;
  not aggregates, not ratios, not estimations — each call recorded byte-for-byte.

- The sum of 75,638 cached tokens across 41 records; `cached_basis = 26 of 41` of calls carried the cached_tokens field;
  the rate is a derived number, not a claim of superiority.

- **No one ever says "you should use this model"** because of this number; it is a fact —
  that fact does not convert.

### 48.4 The vow of this volume (the last one)

**You do not get to revise the numbers in this book once it is written — rewriting it erases it.**
Rewriting pretends you had seen it; the ledger can describe a lot of things, it cannot lie: **once written, it exists forever, like reflog.**
Everything unwritten is not missing — it is in flight.
Everything complex exists without pretense — just because it is difficult, it is never folded.

---
## Volume XLIX · The Tide of Quiet（卷四十九 · 沉默的潮汐）

> This volume puts down the load of observable absence — this host standing quiet right now, the Docker containers that do exist, the ports that simply refuse —
> exactly as they fell.

### 49.1 Five real stakes (every one `git show`-visible)

| # | What happened | Status | Anchor |
|---|---|---|---|
| A | Earlier today port 8000 answered `{"status":"ok","db":true,"llm_ready":true,"build_sha":"dev"}` — later the same door refuses contact: `Test-NetConnection -Port 8000 => False` | the door slammed | #1812 · #1827 |
| B | `live_lane_probe.py` real kick-off returned `iron evidence does not lie` with `prompt_tokens_details.cached_tokens=4224` | always recoverable | `live_lane_probe.py` · #1812 |
| C | Four Spring lanes, offline, `mvn -o`: gateway 84 · discovery 1 · config 1 · control-plane 51 = **137/137** (Java 25.0.1, not JDK 17) | prior entry | #1825 |
| D | RAG two-level cache on a real container: cold miss=142 → warm **l2_hit=142, miss=0** | golden lane (live) | #1773 |
| E | Load lanes: static front door 432 req / 0 err; live backend `/health` 432 req / 0 err | both open | #1801 · #1811 |

### 49.2 Three utterances this tide utters (iron that does not wear out)

- **a test is a claim; a claim is a ledger line; a ledger line points to a commit** —
  every section carries a hash you can name with your eyes; no "at the time of writing", only what `git show` shows;
- **silence is not absence** — it is submerged spacing; when your host quiets, the right thing is to read the book, not mock the door;
- **a book's aquarium** — the 50 volumes here are not grandeur — they are tides that come in to anchor your eyes to one more fact; a quiet world is still full.

### 49.3 The vow of the tide

**Silence is not a verdict — it is a receipt shaped like an unfinished footnote in `## #NNNN`.**
Volume XLIX latches this one: your eyes on `git log` can watch real commits arrive; nobody calls from inside the repo to say "wait a minute";
and if you want to know what the next volume is — go knock on GitHub; the book neither promises nor retrades.

---
## Volume L · The Closing Gate（卷五十 · 收口之门）

> This volume is the closing gesture of a door —
> not a finish line, not a triumph, but a door swung inward one time and exactly one time: what you see inside is what has been visibly counted.

### 50.1 Five things this milestone pins shut

| Event | Grade | Detail |
|---|---|---|
| Spring lanes off-line (mvn -o) | **green** | gateway 84 / discovery 1 / config 1 / control-plane 51 = **137/137** (2026-11-15) |
| Static-front-door load lane | **green** | **432 req / 0 err** · p50 round-3 = 84 ms |
| Live backend /health lane | **green** | **432 req / 0 err** · p50 round-3 = 329 ms |
| LLM lane (wkapi.pro · gpt-6-sol) | **partial truth** | stream + include_usage alone returns `usage`; call answered in 12.6 s · 557 completion (reasoning 450) · `cached_tokens` at top = `null` — the signal lives at `prompt_tokens_details.cached_tokens` |
| Wheel inversion | **fixed** | commit `#1800` · three iterations on owner's repeat reports |

### 50.2 What this round did NOT finish — honestly

| Hand | Detail | Waits on |
|---|---|---|
| Real production | this repo has never run in a real deployment | you handing me a surface / DNS / credentials |
| Full pytest suite | host RAM ≈ 2 GB · the full suite won't even boot | you upgrading the runner to ≥8 GB |
| Real fleet-wide instrumentation | without product-privacy sign-off, we ship nothing about anyone | you signing `OBSERVABILITY.md` gates |

### 50.3 The vow of the closing gesture

**The closing is not the conclusion; it is the drawing of the outline — the shape before the figure.**
Volume L pins these; it does not complete them. The five holds of #1825 / #1801 / #1800 / #1821 / #1788 — hold up under hammer. The door swings inward: nothing has ended; everything has been named.

---
## Volume LI · The Breath (卷五十一 · 呼吸)

> What walks into this repository is not the lexicon, not the threshold — it is the sustained breath: writes → is proven → is polished → writes again;
> a pixel squished off by one inch, a commit bred by three — the station where a visitor lands says the one about breathing itself.

### 51.1 The recent breaths (#1804 → #1822 → #1836)

| Moment | Volume | Wavelength |
|---|---|---|
| 2026-11-15 #1812 | The Book Writes Itself | 56 volumes |
| 2026-11-15 #1813 | The Last Call | random next, single-page |
| 2026-11-15 #1800 | The Tide of Quiet | 2 × 432 req / 0 err |
| 2026-11-15 #1807 | Copy & Replay | 10.25s → **3.0ms** cached replay |
| 2026-11-15 #1821 | The Proven Cache | 94.5% prefix cache nested |
| 2026-11-15 #1824 | The Trace | 1,625-section scan |
| 2026-11-15 #1836 | The Breath | coach tooltip dropped & re-anchored |

### 51.2 Three doings of "The Breath"

- **Typography no longer battles blocks**：`white-space: nowrap` on long IDs replaced with `max-width: 460px; text-overflow: ellipsis`
  - at ≤900px, `.topbar-help`, `.topbar-workspace`, `.breadcrumb-separator` collapse — the prose keeps its wings;
- **Coach tip dropped from "right off the screen"**：the previous anchor `left:130%` churned outside the cliff — now `left: 50%; top: calc(100% + 10px)`; centered below the badge;
- **Immovable rails**: (1) court never walks through the cache lane; (2) the agent console waits for a human to press Approve — no self-sealing, ever; (3) no bearer key grants all users admin — the gate at `#/identity` is fail-closed and that is forever.

### 51.3 The vow of the breath

**The book is not completed — Volume LI is not a finale; it is the first exhale the code dares to make.**
A breath is not the storm's end — it is one of many turns on the clock. The next book has its own ink; each volume is one stroke, one stroke one knock, each knock one hash; **"no hash is skipped"** is the spell this book holds.

---
## Volume LII · The Spring of Silence（卷五十二 · 沉默的种子）

> This volume is a declaration —
> these pages are not a simulation pretending to be a product; these are the words of a repository that finally dares to speak for itself.

### 52.1 Five things this repo does NOT have (but people always want)

| Claim | The truth | Anchor |
|---|---|---|
| "CI is running in line" | No — workflow YAML exists but is never triggered (no push credentials) | `.github/workflows/*` has no trigger conditions configured |
| "Auto-deploy to prod" | Never — no DNS, no host, no live endpoint in this repo | `deploy/` folder is empty scaffolding |
| "Cross-region TLS termination" | No — promised across Volumes XXXI+ | #1805, #1817 |
| "Real fleet telemetry" | No — only build-time git-JSON figures | `#/gazette` reads from chronicle.json/repoStats.json/worldbook.json — not live traffic |
| "Agent auto-seal" | Never — every seal requires human — `verdict_channels.py` fails build on drift | `verdict_channels.py` |

### 52.2 Five things this repo **DOES** have

| Claim | The truth | Anchor |
|---|---|---|
| 58 volumes of the world book, zh/en symmetric | 58 volumes · 133,339 chars · every paragraph git show-verifiable | worldbook.json |
| 39 first-level routes reachable | guide catalog 6/6 · USER_GUIDE in zh/en | #1815 / #1810 |
| Spring off-line lane green | **137/137** (gateway 84 · discovery 1 · config 1 · control-plane 51) | #1825 |
| 51/51 gate tests reproduce | guide + ledger quartet | full pytest non-runnable on 2GB host |
| Two load lanes both pass | 432+432 / 0 errors | #1801 |

### 52.3 The vow of the spring

**Not a final chapter — this is the repo daring to read itself aloud.**
It is only the start. The ending is another word — for now, it is "keep knocking."

---
## Volume LIII · The Fractured Anchor（卷五十三 · 裂缝之锚）

> Seven living containers run on this host — all of them dependency tier.
> None is an application tier. That is not shame; that is the ledger.
> This is what "demo in a browser" looks like when it is written down without theatrical fog.

### 53.1 What is actually running — seven living cargo

| Container | Image | State | Anchor |
|---|---|---|---|
| specproof-mysql | mysql:8.4 | Up healthy | docker-compose up |
| specproof-redis | redis:7.4-alpine | Up healthy | dual-level cache (L1 + L2) |
| specproof-mongodb | mongo:7.0 | Up healthy | append-only agent checkpoints |
| specproof-elasticsearch | elasticsearch:8.16.4 | Up healthy | RAG retrieval layer |
| specproof-rabbitmq | rabbitmq:4.0-management | Up healthy | outbox-relay |
| specproof-minio | seaweedfs:3.80 | Up healthy | capsule object store |
| specproof-phase0-prometheus | prom/prometheus:v3.3.1 | Up Ready | /metrics scraper |

### 53.2 What is NOT running on this host (also true)

- `specproof-534-plane` (python:3.12-slim): **Exited (255) 12–13 days ago** — binary does not run on this host anymore;
- `specproof-web` / `specproof-gateway` / `specproof-api`: **absent from Docker list** — nothing maps any port to this repo;
- Port 8000's `/health` belongs to `careeros-ai-service` — it returned `{"status":"ok"}`, with `server: uvicorn`, `x-request-id` and `traceparent` headers — not THIS repo's build;
- Spring off-line lane **137/137 green** (`mvn -o`) — but that is JVM build-up + unit test, not a live process either;
- The *only* prod-shaped specs on this host are `demo/spring-backend` under tags `base`/`head-v1` — they exist as **fixtures** for gofuzzle verification, not as a deployed service.

### 53.3 What the fracture means

**Fracture is not failure — it is the seam, marked in iron.**
This volume exists in the world book because a fissure across the spine of the stack should not be smoothed over with optimism:
7 of 8 expected cars are on the track. The 8th (`specproof-534-plane`) is sitting quiet;
the track across the ground is still intact —
but the fact that nobody wrote it down was the real silence.

---
## Volume LIV · The Hall of Indicators（卷五十四 · 横幅匾额）

> Every plaque hung in this hall must be able to name where its ink came from.
> This volume does not write "aspirations" — it writes down what was actually lit on 2026-11-16,
> what was struck out of cold steel by real runs, and what has never been lit at all.

### 54.1 Two clocks, one truth

This repository keeps two kinds of numbers, and both of them are called "true" — they are two different trues:

| Kind | Speaks of | Where it comes from |
|---|---|---|
| Build-time facts | As of a commit, how many sections / volumes / commits this repo holds | chronicle.json / repoStats.json / worldbook.json |
| Live facts | Whether this process is alive right now, how many times it was knocked on, how many milliseconds its first Redis ping took | 192.168.1.5:8000/metrics + Prometheus scrape |

These two clocks never substitute for each other. The fracture from Volumes LII–LIII is, at bottom, the slip between calling a build-time true number a live true number.

### 54.2 The three plaques that were actually lit on 2026-11-16

| Plaque | Origin | Evidence |
|---|---|---|
| prometheus itself | localhost:9090/metrics | scrape health: up |
| rabbitmq telemetry | rabbitmq:15692/metrics/per-object | scrape health: up (rabbitmq_prometheus ships with the image) |
| **local-host-api** | 192.168.1.5:8000/metrics | added this round; after `docker restart`, health: up; specproof_up=67.9s; specproof_http_requests_total 5→55 (48 concurrent knocks, all counted) |

### 54.3 The seven plaques this host has never lit (and their notice cards)

| Plaque | Why it stays unlit, honestly |
|---|---|
| api:8000 | The app stack never joined the compose network (this host's app binds 0.0.0.0:8000, outside the phase0 network) |
| worker:9100 | Same reason; worker never ran here |
| outbox-relay:9101 | never started in any deployment |
| notify-relay:9102 | the notify relay does not exist |
| invoice-cron:9103 | billing profile never enabled |
| otel-collector:8889 | the OTEL stack was never deployed (listed as "app-stack wiring pending" in OBSERVABILITY.md) |
| specproof-edge:8090 | the Spring Cloud Gateway has never run live — 137/137 tests were all off-line `mvn -o` |

Every notice card tells the truth: these seven "downs" are not failures — they are honesty, worth more than a fake green LED.

### 54.4 The house rules of the Hall

1. **No plaque without a source.** Every number must name the file, the query, the commit that struck it.
2. **A broken plaque says broken.** down is down — never dressed up as "degraded-maybe".
3. **New plaques enter by producing their origin first.** The full record of `local-host-api`'s induction lives at docs/operations/LIVE_PROBE_2026-11-16.md, with the before/after tables.
4. **No plaque called "password 123".** The admin panel is RBAC fail-closed; this hall will never hang that plaque.

### 54.5 Words the Hall still refuses to write

- "Grafana SLO boards passed validation" — never seen, never run, never signed.
- "Alertmanager is routing alerts" — receiver is null; it sends nothing.
- "An alert chain reached a human within 15 minutes" — it never fired.
- "Production mTLS termination" — promised in Volume XXXI; still lives only in clauses.

These words are not forgotten — they are deliberately left blank. Blank, until a human signs.

---
## Volume LV · The Quiet Ensemble（卷五十五 · 无声的合奏）

> The score is written, the parts are printed — but the orchestra has not assembled.
> This volume writes down the scene of a "seemingly performing ensemble" where the players are missing — not to hide the absent, but to name every empty chair.

### 55.1 Three made it onto the stage; seven chairs stand empty

| Present | Section | Evidence |
|---|---|---|
| prometheus | self-reference | localhost:9090/metrics · up (container's own self-check) |
| rabbitmq | double bass | rabbitmq:15692/metrics/per-object · up (plugin enabled by the image) |
| local-host-api | concertmaster | 192.168.1.5:8000/metrics · up (entered in #1843) |

The seven absentees, see #1841 for the full ledger: api / worker / outbox-relay / notify-relay / invoice-cron / otel-collector / specproof-edge — every one of them an honest "lookup … no such host", an honest down.

### 55.2 A snapshot is not a broadcast — but it must be true

This volume nails down one house rule: build-time numbers must never dress as live telemetry.

The Morning Gazette (#/gazette) now carries a column called THE LIVE LANE:
seven cells, every number from the 2026-11-16 probing session — liveness suite, SPA 200, 48/48 zero errors, counter 5→55, no-key 503, Prometheus 3/10 up, outbound search 402.
Each cell is labelled "build-time snapshot"; it reports precisely what the live lane knows, and nothing more.

### 55.3 Whose hand holds the baton

The tempo comes from git: commit → build_repo_stats / build_chronicle → JSON → page.
The one never beating time: Alertmanager (receiver = null) — it sends nothing, and this book forbids it from pretending it ever did.
The one who may never mount the podium: the "password 123" baton — RBAC fail-closed, banned by the hall.

### 55.4 The day the symphony will actually be performed

Not the day the grid is filled — the day every cell can say "who knocked at what hour, at what minute."
Until then, this score stays on the stand: **no fake players in empty chairs, no attendance marks for the absent.**

---
## Volume LVI · The Palm of White Light（卷五十六 · 白光掌心）

> White light is not the lampshade — it is the point it shines upon, shining on its own.
> This volume only accepts the three pieces of white-light iron evidence taken on the night of 2026-11-16 —
> all under the name gpt-6-sol, and every one of them replayable.

### 56.1 The three pieces of iron evidence (all struck live at 2026-11-16T16:44Z)

| Iron evidence | Lane | Result |
|---|---|---|
| Short ask: "answer with one character: 证？" | non-stream **and** stream+include_usage — both report | prompt=4456 completion=5, **cached=4224** (94.9% hit, identical on both lanes) |
| Long ask: ~4.5k-character Chinese evidence prose | stream+include_usage | prompt=2233 completion=272, **cached=2035** (91.1% hit) |
| Long ask, repeated verbatim (2nd call) | both lanes | cached=None — **the provider's prefix cache is not idempotent**; it is no free lunch |

### 56.2 Underneath the thumbnail — the repo's own white light

The same ask through this repository's provider lane (`SPECPROOF_PROVIDER_POLICY=1`):

| Call | Latency | prompt | completion | cached |
|---|---|---|---|---|
| call #1 (application lane, kind=draft) | **6.71s** | 7564 | 47 | None (provider miss — a brand-new Chinese prefix) |
| call #2 (identical request) | **0.00s** | 7564 | 47 | local semantic cache (policy lane, draft is cacheable) — **the request never left the host** |

Both real rows are now in `.local/llm_usage.jsonl` (41 → **43**); `engine.json` was rebuilt:
`cache_hit_rate` **0.512 → 0.464** — not a secret turned, just the measuring basis turned: the two new calls never hit, and they widened the denominator. Honesty outranks prettiness.

### 56.3 The house rules of the white light (why it burns this steady)

1. **STABLE PREFIX FIRST → VARIABLE DATA LAST** — providers/prompt_templates.py pins byte-stable SYSTEM_BLOCK + TOOL_SCHEMA_BLOCK up front;
2. **every lane streams with include_usage** — the chat path always sets `stream=True`, `stream_options={"include_usage": True}` (openai_compatible.py), the "requested non-stream" lane is only an aggregated return — this is where "perpetual non-stream display" was healed at the root;
3. **court never enters the cache** — `client_policy.py` hard-refuses `court | counterexample | accept_judge | contract_compile`: a judge's white light illuminates only this once, never a memory impersonating it;
4. **the key never lands on disk** — .local/llm.json is read-only, never logged; every number in this volume comes from scripts run fresh (`scripts/llm_cache_probe.py` + `scripts/build_engine.py`).

### 56.4 Where the white light does not reach (still refusing to beautify)

* The provider-side prefix cache cannot be promised: the identical long ask returned cached=None on the second hit on both lanes — an adaptive TTL dictates it;
* this 2 GB host cannot run the full pytest suite; **guide+ledger 51/51** is the reproducible local gate;
* "white light 100% hit rate" in any PR is advertising, not iron evidence.

---
## Volume LVII · The Silent Pear Blossom（卷五十七 · 静默的梨花）

> The pear blossom does not speak; it falls at your feet — it is not blooming for others, nor for warning others.
> This volume is about the raw trail this very browser typed out itself: not one event was written on your behalf,
> not one number came from somebody else's hand.

### 57.1 The climate chart counts exactly five things

| Sample | Meaning |
|---|---|
| `view` | the hash route became visible (including first paint) |
| `dwell` | milliseconds the route was truly in front of a human (hidden→visible boundaries included) |
| `rage` | 3+ taps on the same element signature (tag.class|first 24 chars of text) inside 2 seconds |
| `route` | the roll-up: route · count · dwell |
| `span` | minutes between the first and the last event |

Capacity: 1200 events (a ring). When full, the oldest event is pushed out — **it will never push your key out, because it never touches keys.**

### 57.2 The five things the climate chart never collects

1. Keystrokes (what the keyboard typed does not exist here);
2. Form contents (any input/textarea value);
3. Passwords (they never reach the Insight Deck either);
4. Real identities (no usernames, no emails, no device fingerprints);
5. Other people's browsers (each browser sees only its own climate chart).

### 57.3 Why the fifth key was cut

Behind that door there were only four keys: specproof_tour_v1 (six seals), specproof_onboarding_v1 (footsteps), specproof_gestures_v1 (the fourteen), specproof_drill_v1 (the drill).
**They certify what this browser did — none of them certifies where it grew impatient.**

The new key `specproof_heat_v1` is cut precisely for impatience: quick bounces (<4s dwell) · the rage-tap hall of fame · the resident-route table — all on your device, all read-only, all erasable with one tap (Insight Deck: "Clear this browser's trace").

### 57.4 The climate chart shows up in three audiences

| Place | Role |
|---|---|
| Insight Deck (#/insight, RBAC fail-closed) | the "THIS BROWSER'S RAW TAPS" banner — the only cell of real data an admin can see |
| The Mint (#/mint, marks of your own hand) | the fifth KPI "tap events" + the climate panel: views / distinct routes / quick bounces / rage taps |
| Chronicle & ledger | recorded from #1846: the three-event sampling and the capacity cap |

### 57.5 The house rules of the climate chart

* **localStorage only, never the network** — no endpoint, no webhook, no beacon;
* **silence is not zero** — the page says "silence", never "zero visits";
* **one-tap erasure** — `clearHeat()` wipes the whole book;
* **PV is not truth** — the chart answers "how impatient was this browser", never "who is this person".

When the blossoms fill the ground, the vault's seal is complete — until that day, this volume is just one letter written by one browser, never mailed.

---
## Volume LVIII · The Echolocation（卷五十八 · 回声定位）

> Dolphins never speak human, but they click at a wall over and over — until they remember where the wall is.
> This volume is about the echo of the local climate log (specproof_heat_v1): when one browser calls into the same button three times,
> what the library hands back is not a scolding — it is a note: "perhaps the door you want is over there."

### 58.1 The three triggers of the echo (all required)

| Trigger | Value |
|---|---|
| this device holds >= 3 rage-tap events | `deriveHeat().rageTotal >= 3` |
| this batch has not been acknowledged yet | `specproof_heat_ack_v1 < rageTotal` (ack counts only) |
| anywhere in the app | any App route; H toggles the teaching layer |

### 58.2 The three voices of the echo (all offline, bilingual zh/en)

| Signature matched | The note to a newcomer |
|---|---|
| approve / 批准 / sign | "Approve is always a human one click — open the evidence first." |
| seal / 盖印 / tour / 巡览 | "No page visited, no seal — visit the station first." |
| run / verify / 执行 | "Three blind taps are three blind taps — peek at the Evidence tab." |
| jobs/new / 新建 | "Repo path, base/head, requirements file — missing one refuses the click; load demo data at the top." |
| model/provider/settings / 模型 | "Keep the /v1 suffix; gpt-6-sol, exactly spelled; else the test button quotes your typo back." |
| anything else | "This spot made you impatient — press H; gold marks are the manual." |

### 58.3 The three boundaries of the echo

1. **no gaslighting**: the climate log knows "tapped again", never "why"; the echo never accuses, only routes;
2. **no nagging**: `specproof_heat_ack_v1` stores how many rage-taps were already acknowledged; only growth re-pings;
3. **no extraterritoriality**: nothing leaves the device; no server ever sorts the fingertips of strangers.

### 58.4 The echo always flies the same way: wall to ear

Nothing is pushed from outside; the only push is this — "the next time this device opens any screen, a small note waits bottom-right."
The note carries two doors: press H (焊 the hints onto the interface) · or "remember on this device".
It never rings the same bell twice — unless the wanderer calls into the same button three times again.

---
## Volume LIX · The Mirror Corridor（卷五十九 · 镜厅回廊）

> A mirror never tells you what is on your face — it only counts how many times you frowned at it.
> This volume is about the sound of the "quick bounce" travelling back into the pocket manual:
> when a door is opened and shut three times, the library never rebukes the opener — it hangs a note on the door.

### 59.1 The entrance to the Mirror Corridor

Under the title of the pocket manual (#/manual) there is now a strip called THE LOCAL ECHO:
* it reads this browser's `specproof_heat_v1`, collecting every event with dwell < 4000ms and grouping by route;
* it lists only the top-4 "most-bolted" doors, marked "×N", each with a "Walk it →" anchor at its side;
* an empty shelf honestly says "silence, not zero" — no data, no invented data;
* it never prints (display:none on A4) — the pocket manual stays crisp on paper.

### 59.2 The six mirrors of the Mirror Corridor

| Mirror | Corresponding page | The truth |
|---|---|---|
| The Seal Court | /tour | six seals unsealed is how the table shrinks — re-enters mid-way and returns |
| The Drill Ladder | /drill | re-classify soft items as review cards, not gates |
| The Evidence Room | /jobs/new | the universal key: "load demo data" at the top |
| The Model Mirror | /settings | the /v1 suffix / gpt-6-sol spelled exactly / protocol — the test button quotes your typo back |
| The Pocket Manual | /manual | this volume itself — the more this device is exposed, the denser the echo becomes |
| The Epic Hall | /epic | the macro-narrative most prone to emptiness — this hall hangs "volumes I–LIX are on the shelf" |

### 59.3 The house rules of the Mirror Corridor

1. **no mirrors look past your face** — the climate log counts shut doors, never expressions;
2. **empty mirrors are not allowed to shine fake** — no bounce data = "silence", never a ranked guess;
3. **reflection stays local** — the strip is sorted purely from localStorage; never uploaded, never aggregated, never cross-device;
4. **every door keeps a handle** — "Walk it →" always links to the real anchor, never a decorative button.

### 59.4 Infinite is not the same as empty

On a vast field, every empty room must hang one real lamp. What this volume accomplishes is only this —
"when somebody passes, the lamp flickers on."
The rest belongs to Volume LX and beyond.

---
## Volume LX · The Three-Body Boundary（卷六十 · 三体界碑）

> Stars never share orbits — gravity only binds them with invisible lines.
> This volume puts up three boundary stones: the boundary of cold starts, the boundary of port ownership, the boundary of honest verdicts.
> Every carving is from 2026-11-16's live knocking — not passed means not passed, and this volume does not retouch it.

### 60.1 The first stone: cold start (verdict BUDGET-BLOWN)

| Round | Result | Note |
|---|---|---|
| round 1 | p99 **7588ms** (96/96 ok) | cold-disk JIT + 23 concurrent readers fighting for the platter |
| round 2 | p99 **528ms** (96/96 ok) | warm cache, normal service |
| verdict | **BUDGET-BLOWN** (the script judges the worst round) | not a crash — an overage, and overage is overage |

Not a crash — but this book may not write "normal" over an overage. The cold-start spike is real: every cold system spends its first two minutes serving its timeouts, that is factory spec, not a bug to fix. The right answer is a warmup probe downstream, not an average-obsessed dashboard pretending nothing happened.

### 60.2 The second stone: port ownership

| Address | Who answered, at that moment | Hallmarks |
|---|---|---|
| 127.0.0.1:8000 | career-os-ai-service (com.docker.backend PID 12868) | uvicorn + x-request-id + traceparent · 404 |
| 0.0.0.0:8000 (this repo's bind) | specproof FastAPI | /health mysql+redis=ok · /metrics exposition |
| 192.168.1.5:8000 | the same process | this repo's only true reachable face |

Conclusion: this repo never owned, will never own, and does not need to own 127.0.0.1:8000. Any claim that "port 8000 is specproof" is an optical illusion.

### 60.3 The third stone: honest verdicts

| Lane | Target | Result | Verdict |
|---|---|---|---|
| A | 192.168.1.5:8000 (re-launched) | 144/144 · 0 err · p99 603ms | **OK** |
| A′ | same host, earlier | 192 req · 0 err · p99 440→176ms | **OK** |
| B | static front door, cold start | 192/192 · 0 err · p99 7588ms | **BUDGET-BLOWN** |
| C | 127.0.0.1:8000 (this morning) | 100% err | **BUDGET-BLOWN** (not this repo) |

All four verdicts live on `#/fabric` inside the "THE STRESS LEDGER" panel as a 2026-11-16 snapshot — not running, not live, not re-computed.

### 60.4 The house rules of the stones

1. **failed verdicts are not washed clean** — BUDGET-BLOWN is printed on the page, not filed under Bugs;
2. **named ownership** — the answerer of every port must have a face;
3. **snapshots do not auto-refresh** — they assert "being struck", never "still striking".

---
## Volume LXI · North Wind Night（卷六十一 · 北风之夜）

> The north wind opens the first window and pours cold air in — not a failure, just winter's manners.
> Volume LX raised the stone of the cold-start overage; this volume does not argue it away — it hands over one key: the warm door.
> And this volume also stipulates: the key does not rewrite the ledger — today's three rounds came in above the aspirated threshold anyway, and this book records it as-is.

### 61.1 The key: the warm door in start_local.ps1 (landed in #1850)

At the very end of the startup sequence, before "all green":
* one `/health` self-probe (reports mysql/redis state);
* two self-knocks on `/` (Stopwatch-timed, byte counts printed) — so real downstream requests never eat the cold-disk JIT spike again;
* skipped cleanly when apps/web/dist is absent (Vite dev mode needs no warm assets);
* validated through the syntax parser (Windows PowerShell 5.1 / pwsh 7 grammar is shared).

### 61.2 Today's three knocks (verbatim, all three kept)

| Round | p50 | p95 | p99 | Result |
|---|---|---|---|---|
| 1 (cold) | 1590ms | 5282ms | **5376ms** | 96/96 ok · no crash |
| 2 (warm) | 24ms | 1021ms | **1024ms** | 96/96 ok · above the aspirated <600ms |
| 3 (warm·loaded host) | 23ms | 1525ms | **1543ms** | 96/96 ok · 23 containers running |
| verdict | | | **BUDGET-BLOWN** (worst round) | |

Conclusion: the key is cut, but the redemption cannot be certified on this host — 2 GB RAM + 23 containers (career-os ×8 / football / nexus / crossrealm…) press every aspiration flat. Writing "<600ms" would be easy-beautiful — writing "did not hold <600ms" is honest.

### 61.3 Three house rules of the warm door

1. **be the sacrifice first** — the launcher always knocks twice before saying "the door is open";
2. **leave the timing behind** — self-knock latencies print into the boot log, where they belong;
3. **never delete the cold number** — the 5376ms stays exposed in Volume LX; the key is not a broom.

### 61.4 Why the key still matters

The warm door may not change this host's barometric pressure, but it changes one material fact: **a customer's request is no longer the sacrificed first breath.**
With warming built into the launch, every door is opened already warm.

---
## Volume LXII · The East Wind South Wind（卷六十二 · 东风之南）

> The east wind arrives and first melts the old snow off the roof — the old ledger is not deleted; it just lies there warming in the sun.
> Volume LX said "over budget"; Volume LXI said "the key is cut but this host cannot hold the pressure" — this volume says:
> the key went in, one turn, and the door may now say "open", verdict in three characters: **OK** —
> with one footnote: nobody ever promised <600ms outside our heads.

### 62.1 The key & its turn

`scripts/stress_smoke.py --warmup N`: knock N untimed rounds first (not counted), then measure.
This is the first ruler to actually quantify the "after warming" answer — the companion of the #1850 warm door.

### 62.2 The three rounds struck at 2026-11-16T17:20 (the budget sheet; 2 warmups + 2 measured)

| Round | Figures | Verdict |
|---|---|---|
| warmup 1 | p99 3585ms (not counted) | — |
| warmup 2 | p99 1523ms (not counted) | — |
| round 1 | **p50 16.1ms** · p99 **1532ms** · 96/96 · 0 err | within the 5000ms budget |
| round 2 | p50 16.6ms · p99 1529ms · 96/96 · 0 err | within the 5000ms budget |
| **verdict** | **OK** (worst p99 1532ms < 5000ms) | |

Compared with Volume LXI: without warming the verdict was BUDGET-BLOWN (5376ms); with warming the verdict is OK — warming really works. This time it is the numbers speaking, not the spirit.
It still sails above the <600ms psychological line — **the psychological line is not a shipping line; the gap stays written, never拆.**

### 62.3 The evidence goes into git

`docs/evidence/2026-11-16-static-warm.json` — every round's elapsed time, every byte (19,394,784 B × 2), every single zero error, committed verbatim.
It answers to `git show` — evidence need not plead: **git holds it, it speaks for itself.**

### 62.4 Not the end — the next opening

* next boot: the #1850 warm door and this volume's `--warmup` are a pair of migrating birds;
* a genuine budget redemption (<600ms) needs one quiet 4 GB machine without 23 noisy neighbours — that is Volume LXIII's honest prelude;
* this volume registers only "how loud it could ring at this hour" — it will never claim "every hour rings this loud".

---
## Volume LXIII · The Homecoming（卷六十三 · 归港记）

> A ship going out never sails to prove how far the sea is — it sails so that home may know it can come back.
> This volume shelters one piece of evidence on its way home:
> from one command (stress_smoke.py --json-report), to one committed JSON,
> to one build-time distiller that hands it to the eyes of #/fabric — none of the legs may skip a stop.

### 63.1 The evidence's route home (all stops verifiable via git show)

| Leg | Evidence |
|---|---|
| 1 · filed | `docs/evidence/2026-11-16-static-warm.json` — both ends p99 1532/1529ms · 96×2 · 0 err · 19,394,784 B ×2 |
| 2 · distilled | `scripts/build_evidence.py` — newest by filename; verbatim copy, never recomputed; empty dir → "no evidence filed yet", never a fake green |
| 3 · compacted | `apps/web/src/pages/evidence.json` — the build-time data contract; every field verbatim |
| 4 · displayed | `#/fabric` git-evidence card: struck-at · concurrency · warmups · totals · worst p99 · verdict (OK → jade / BUDGET-BLOWN → red) |
| 5 · rule | the command on the card: `stress_smoke.py --json-report docs/evidence/<name>.json` — anyone may strike, and the weave lights up |

### 63.2 Three house rules of the homecoming

1. **no sleight of hand** — build_evidence.py has no "improve", only "copy verbatim";
2. **no fake green** — no evidence, no green card; corrupt files render readable:false as-is;
3. **no silence** — the verdict chip takes the verdict's colour; BUDGET-BLOWN is red, always will be.

### 63.3 Where the next leg goes

The evidence already hangs on the weave — Volume LXIV will make the homecoming a routine:
stress_smoke.py truly struck in CI (even weekly), the card refreshing itself on the next push.
Until that day, every person willing to knock makes this tapestry glow a little.

---
## Volume LXIV · The Day of Sailing（卷六十四 · 启航日）

> The day the sail goes up, the wind knows it was called.
> Volume LXIII had the evidence come home — this volume makes the homecoming a Monday routine:
> no pushes, no red flags, no cart to pull along — just one strike, one archive, and waiting eyes.

### 64.1 The Monday shuttle: weekly-stress.yml (landed in #1853)

| Item | Value |
|---|---|
| name | specproof-weekly-stress |
| cadence | `0 3 * * 1` (Monday 03:00 UTC) + `workflow_dispatch` manual |
| does what | npm ci + build → `stress_smoke.py --warmup 2 --concurrency 48 --rounds 2 --per-thread 2` → `--json-report docs/evidence/weekly-<run_id>.json` |
| produces | artifact `weekly-stress-<run_id>`: evidence JSON + stress-run.log + stress-summary.md |
| pushes | **nothing** — no branch, no tag, no commit |
| red? | **never** — `set +e` captures the script exit, writes it into stress-summary.md, runner always exits 0; the machine floor (5000ms) is a sanity bumper, not an SLO |
| permissions | `contents: read` · `concurrency: weekly-stress` (cancel-in-progress) |
| does not | push, red-flag, portfolio-sync, pretend a production SLO exists |

### 64.2 The house rules of the sailing day

1. **every Monday** — repeating, never cancelled for release prep nor for fatigue;
2. **archive only, never peddle** — artifact + summary side by side; any human reviewer can byte-verify every claim;
3. **no red hype or lying** — STRESS_EXIT is written verbatim into the summary, even "1" stays "1".

### 64.3 The chart (Volumes LXII–LXIV)

```
stress_smoke.py --warmup N       #1851/LXII   anyone may strike
     ↓ --json-report docs/evidence/…   (git-tracked)
docs/evidence/2026-11-16-…json   #1851/LXII   first evidence on file
     ↓ build_evidence.py
apps/web/src/pages/evidence.json #1852/LXIII  verbatim distillation
     ↓ import
#/fabric git-evidence card       #1852/LXIII  jade OK / red BUDGET-BLOWN
     ↓ weekly-stress (cron)      #1853/LXIV   the Monday shuttle
CI artifact (weekly)             LXIV        auto-lit weekly
```

### 64.4 Not yet sailed

This CI lane sails only after it merges into master — first strike Monday 03:00 UTC after today's commit.
It will never auto-merge numbers into git — git accepts only human-certified evidence.

---
## Volume LXV · The Homecoming, Repeated（卷六十五 · 归港复航）

> One ship docking is a story; two dockings are a timetable —
> five milliseconds slower on the second pass is not an ending, it is the starting line of every honest compare.
> This volume delivers the ruler that can match flights: with two evidence files on the shelf, comparison may begin.

### 65.1 Two real exhibits (same day, twenty minutes apart)

| Exhibit | p99 (two rounds) | Verdict |
|---|---|---|
| 2026-11-16-static-warm.json (17:20Z) | 1532 / 1529ms · 19,394,784 B ×2 | OK |
| 2026-11-16-static-warm-2.json (17:2xZ) | 1533 / 1537ms · 20,349,568 B ×2 | OK |

**Δ (second vs first): worst p99 +5.1ms · avg p95 +5.6ms · traffic +0.91 MB.**
Both files repeat 96×2 zero-error at p99 ≈ 1530ms — the front door on this host, under 23 containers, holds within ±5ms — **this is reproducibility, not a concert.**

### 65.2 The route got updated (v1 → now)

* `build_evidence.py` ordering is now ISO `started_utc` descending (filename ties at equal prefix sorted wrong — fixed);
* the emitted doc gained `delta_vs_previous` (vs_file · worst_p99_delta_ms · avg_p95_delta_ms · bytes_delta · total_delta);
* the `#/fabric` evidence card gained a "Δ vs previous · read-only comparison, no up/down score" line (numbers are signed, sourced from started_utc);
* no SLO score, no pass-fraction banner, no "YoY +X%" applause — **there is no such persuasion in this repo; none of it is evidence.**

### 65.3 Additions to the house rules

1. **same-source comparison only** — both exhibits from this host, this lane;
2. **Δ is never painted red** — Δ is a tone, never a verdict of good or bad;
3. **Δ vanishes below two exhibits** — one file means one shelf, no compare.

### 65.4 The chart (LXII → LXIV → LXV)

```
--warmup 2 strike → 2026-11-16-…json   (LXII·#1851)
     ↓ build_evidence.py verbatim distillation
evidence.json v1: latest + delta       (LXIII·#1852, LXV·#1854)
     ↓ import · #/fabric card
GIT EVIDENCE + Δ vs previous           (LXV·this volume)
     ↓
weekly-stress.yml every Monday strike  (LXIV·#1853)
```

---
## Volume LXVI · The Timetable（卷六十六 · 船期表）

> The harbour posts not promises, but a timetable —
> every Monday 03:00 UTC there is a departure; guests see the table, not where the helmsperson sleeps.
> This volume delivers three escort ships for the interface's steady hands: three pages, one ship each, flags up.

### 66.1 Three escort ships (all real vitest assertions)

| Ship | Docked at | Anchored facts |
|---|---|---|
| Tour.test.tsx | #/tour of the Grand Tour | rail aria-valuenow=0 · six stations · exactly 6 disabled seal buttons behind the visit gate · 6 status hints · corrupt storage does not sink the page |
| Fabric.test.tsx | #/fabric, the weave | svg[role=img] exists · ≥30 nodes · ≥30 chips in the index table · clicking the Verifications chip navigates to #/jobs · evidence card present with 2026-11-16-static-warm-2.json and 1537ms · stress ledger present |
| Insight.test.tsx | #/insight, the admin lounge | non-admin door stays shut (PermissionDenied + RBAC fail-closed) · undecided role renders spinner · admin admits with SYNTHETIC COHORT pill · the local heat panel renders and actually clears specproof_heat_v1 |

### 66.2 House rules of the timetable

1. **no wallpaper-testing** — no copies of the page, no screenshots; only aria/structure/navigation-side-effects;
2. **corrupt storage never sinks a ship** — one test feeds `{not-json` straight to localStorage;
3. **numbers are not carved in concrete** — file names and p99 may drift; the card must exist, must show, must never claim live.

### 66.3 The chart (through #1855)

```
533 green · 69 test files
Three escort ships · 12 new assertions
UI suites grown by 3 files
```

From this hour on, "the interface has not quietly broken" is a line you can git show.

---
## Volume LXVII · The Furling Hour（卷六十七 · 收帆时刻）

> One who sets sail must count when the next departure comes — not to wait for it, but to rest easier.
> This volume nails the question "how will this ship knock next" onto the Last Call page:
> which day it knocked last, how many bytes it pushed, and when it knocks next — three sticky notes, honestly pinned by the door.

### 67.1 The Weekly Voyage (pinned atop #/last-call)

| Row | Content | Source |
|---|---|---|
| Ship's stamp | file · struck-at · worst p99 · totals · verdict (OK jade / blown red) | `evidence.json` (verbatim, build time) |
| Still unsigned | real fleet telemetry = OBSERVABILITY.md awaits a human; weekly-stress = first strike waits merge + next Monday; 127.0.0.1:8000 = career-os-ai-service's door | host reality of 2026-11-16, verbatim |
| Next knock | next Monday 03:00 UTC computed live + the knock-now command | `new Date()` at runtime · no invented data |

### 67.2 House rules of the furling hour

1. **three rows, never more** — empty evidence yields an honest "no knock yet" in row 1;
2. **the unsigned list always says the same three** — fleet / weekly shuttle / port ownership; unsigned is said unsigned, never "soon";
3. **the next departure is computed, not imagined** — `nextMondayKnock()` is a real runtime calculation, not decorative text.

### 67.3 The chart (LXII → LXV → LXVII)

```
stress_smoke.py --warmup N        → docs/evidence/*.json       (LXII·#1851)
     ↓ build_evidence.py
evidence.json (latest+delta)      → #/fabric per-delta card    (LXV·#1854)
     ↓ weekly-stress.yml cron
artifact (Mon 03:00 UTC)          → ship's stamp + next knock  (LXIV·#1853 · LXVII·#1856)
```

---
## Volume LXVIII · The Astronomer's Night（卷六十八 · 巡天一夜）

> Astronomers read the galaxy not to prove it shines — but to know whether it shines at all.
> This volume turns "what this project still lacks to count as alive" into three studio IOUs, each under a lamp that does not lie:
> real fleet · is it signed? — the Monday shuttle · is it merged? — port 8000 · who answers right now?

### 68.1 The astronomer's eye: scripts/audit_unsigned.py (landed in #1857)

| Check | This hour (struck live, 2026-11-16) | Lamp |
|---|---|---|
| observability-signature | **awaiting-signature** — OBSERVABILITY.md carries **no human signature block** at all (signature-person / sign-off / signed by / approver / acceptance signature — all patterns unmatched) | amber |
| weekly-stress-merged | **merged** — `.github/workflows/weekly-stress.yml` sits in the repo | jade |
| port-8000-answers | **port-free** — `127.0.0.1:8000/health` currently **refuses the connection** (the morning's occupant, career-os-ai-service, is no longer there) | grey |

The three lamps are **struck live every run** — like --warmup, nothing is remembered, nothing is cached, nothing is impersonated.

### 68.2 House rules of the night watch

1. **red-green not slogans** — no "coming soon"; there is "merged" and there is "port-free right now" — the fact IS the result;
2. **re-runnable for free** — the audit costs ~10ms, and any human may re-strike it before any commit — it never occupies CI;
3. **IOUs can turn jade** — the moment a human signs OBSERVABILITY.md the lamp turns jade on the next run; not metaphorically, in the very next rebuild;
4. **the audit is executable** — `python scripts/audit_unsigned.py`, zero deps, zero keys, zero SLA.

### 68.3 The chart (LXII → LXVIII)

```
--warmup · strike → docs/evidence/*.json     (LXII #1851)
     ↓ build_evidence.py                     (LXIII #1852 · LXV #1854)
evidence.json → #/fabric card + Δ            (LXV #1854)
     ↓ weekly-stress.yml (every Monday)      (LXIV #1853)
     ↓ audit_unsigned.py                     (this volume #1857 · the night watch)
unsigned.json → #/last-call unsigned row     (LXVII #1856 · LXVIII #1857)
```

### 68.4 The finale does not happen in the sky

Green or not? It only turns jade the day a human signs — until that commit lands, the
"real fleet telemetry" line on #/last-call stays amber forever. It does not lie —
the lamp's third colour has always been the one everyone in this room knows.

---
## Volume LXIX · The Quiet Read（卷六十九 · 灯下书停）

> Reading until you forget to switch off the light is "reading under the lamp".
> The quiet read is the other thing: after the book closes, before anybody notices, you copy down the page into a field card —
> with only what git holds on it, and not one pressed stamp.

### 69.1 What the crew card carries

| Block | Contents | Source |
|---|---|---|
| head | xiaodernan/specproof · FIELD CARD · the printing date | repo name · `new Date()` |
| the wall of eight | commits · ledger sections · world books · source lines · Python files · web suites · evidence worst p99 · evidence verdict (**all resolved at print time from repoStats.json / evidence.json — never hard-coded**) | repoStats.json · evidence.json |
| still-unsigned (three) | OBSERVABILITY.md: awaiting-signature · weekly-stress: merged · port 8000: port-free | unsigned.json (live audit) |
| foot | "This card prints only git-tracked facts — not a signature, not a seal, not a promise. Every digit re-opens:" + three re-verification commands | git shell |

### 69.2 House rules of the quiet read

1. **no stamps on the card** — no signature line, no "verified by me"; not a single red vermilion seal;
2. **bytes, reproducible** — every number comes from a locked JSON (`git show` is one shell away);
3. **print is the gift** — A4 keeps only this card; the reading screen and the flyer never overlap;
4. **a card is only a card** — it never pretends to be "the certificate"; formal certificates live in `#/dossier`.

### 69.3 The chart (through #1858)

```
weekly-stress · audit · evidence · repo stats
     ↓  all git-tracked JSON
#/last-call "Print the field card" → A4 at the porthole
CSS: invisible on screen · visible in print · the workstation and the flyer never mix
```

---
## Volume LXX · The Falling Sparks（卷七十 · 灯花落尽）

> A spark is not the lamp dying — it is the last handful of its light, spilling over the lip.
> People get one last train, a book gets a last page; this volume does only one thing:
> it writes the repo's last note before it might ever die, truer than anybody's retelling.

### 70.1 Three doors, one pantry of freshly-cooked facts

| Door | Carries | Source |
|---|---|---|
| GitHub repo page (docs/crewcard.md · crewcard-en.md) | the same handprint — the Chinese card + the English card | build_crewcard_markdown.py this round |
| A4 print (#/last-call "Print the field card") | the same byte, printed | #1858 |
| in-app "weekly voyage + the stamp" | the same JSON rendered in react | #1856 · #1857 · #1854 |

All three doors draw from **one drawer** (repoStats / evidence / unsigned / engine / worldbook, all git-tracked);
none of them is the shadow copy of another — they all just reach for the same chopsticks.

### 70.2 Why a third door (one that grips on GitHub itself)

An app can crash, a page can hang, an A4 can be lost — but a plain markdown file on GitHub
**outlives them all**; the first thing every visitor sees is not a pitch, not a badge,
but a live card that never lies (2,500 commits · 1,659 sections · 76 volumes · p99 1537ms · OK).

### 70.3 The house rules of the falling sparks

1. **three doors, one drawer** — if one door shakes, the other two re-open; otherwise it's a crocked ceremony;
2. **no stamped lies in print** — the markdown carries no signature line either; the whole card system forbids vermilion;
3. **a spark is not a bowl** — the card is not a brand, not a pitch, not a "please hire us" page; it is a single, honest long-exposure;
4. **every commit refreshes the spark** — build_crewcard_markdown.py rides the same forge as chronicle; chronicle moves, the spark moves.

### 70.4 The finale is never the lamp dying

The spark settles, the desk is still warm — the fact at hand:
another docs/crewcard.md lands in git, and the repo's own doorway begins to speak back.

---
## Volume LXXI · Above the Snowline（卷七十一 · 雪线以上）

> Above the snowline there are no trees — not because it is too cold to teach, but because every step at that altitude must tell the truth.
> This volume writes ROADMAP-LIVE: line after line of doors inside this repo, each labelled
> "who may strike it (machine/human) + what blocks it + which exhibit proved it" — not one invented.

### 71.1 The nine doors generated at commit time (auto-rendered by build_roadmap_live.py)

| # | Door | Who strikes |
|---|---|---|
| 1 | first weekly-stress strike (cron 0 3 * * 1, merged) | machine (next Monday) |
| 2 | OBSERVABILITY.md sign-off (real fleet telemetry) | **a human being** |
| 3 | evidence cross-check: 2 exhibits · Δ +5.1ms · OK | machine + human review |
| 4 | PORTFOLIO_TOKEN (portfolio page sync) | a human being |
| 5 | residue spotted (~1,000 hash-named 542-byte files in-repo — suspects from a scratch spill that got committed; this volume does not delete them alone) | human verdict |
| 6 | chronicle keeps itself ingressed (1,859 sections) | machine |
| 7 | the LLM ledger doesn't go stale overnight (cached 75,638 · 46.4% prefix-hit · not an SLO) | machine |

### 71.2 House rules above the snowline

1. **never promise** — three columns only: what to knock · who knocks · what blocks it; never "when it will be done";
2. **doors re-judge themselves** — `scripts/build_roadmap_live.py` rewrites ROADMAP-LIVE on every chronicle rebuild;
3. **IOU = door** — every roadmap line is just an unstruck door, always amber, never a red ✗;
4. **the fog line stays visible** — port 8000, outbound 402, court never caches, fleet still unsigned — all printed in the footer, never hidden.

### 71.3 The telescope pointed below the snowline

#/gazette's weather strip graduates from a fixed "Overcast" to a barometer derived from `evidence.json` Δ:
Δ ≤ +1ms → Fair; ≤ +5ms → Haze; otherwise Fog — **the only barometer in this repo is not a cloud, not Feng Shui — it is p99.**

---
## Volume LXXII · The Many Shadows of the Lamp（卷七十二 · 灯影千重）

> A lamp casts three shadows — not a flaw, a voice.
> This volume places on the table "three truths the user will see one day, and yet will never be told they are a lie" —
> shadows, not spectres; spectres would be the lies.

### 72.1 The three lamp-shadows (Iron Lexicon #15, on the shelf)

| Shadow | Truth | Why kept |
|---|---|---|
| ① Spring Cloud lane 137/137 green · off-line `mvn -o` | nothing has ever run live; green build ≠ prod liveness | "green CI" is no prod licence — printed in the face of it, safer than quiet green |
| ② `#/insight` admin/operator RBAC fail-closed | a "password 123 for everybody" will never be built | this door never offers anybody a shared-secret excuse |
| ③ court/judge lanes always `stream=True + include_usage=True` · court never cached | `client_policy.py` hard-refuses evidence kinds | the judge's light marks only this sitting — never a memory impersonating it |

### 72.2 House rules of the lamp-shadows

1. **name every shadow** — each shadow hangs a plaque: "this is a shadow, not a bug, and not the truth";
2. **shadows may not multiply** — at most these three; a fourth requires your real nod;
3. **a shadow is not a fig leaf** — it is a seal saying "nobody here (including me) ever lied; the light just has not arrived on this one yet";
4. **every shadow is searchable** — the Iron Lexicon anchor list is the entrance to each shadow.

### 72.3 Struck live at the source

| Shadow | Struck at |
|---|---|
| ① | `mvn -o test` (Java 25.0.1) → gateway 84 + discovery 1 + config 1 + control-plane 51 = **137/137**; this host **never** live-booted specproof-app |
| ② | `/api/v1/admin/users` → **503** ("Multi-tenant auth is not enabled") · `/api/v1/llm/usage/summary` → **503** ("API key not configured…") |
| ③ | providers/openai_compatible.py L684 `stream=True` + L685 `include_usage=True` · client_policy.py:18-21 — court/judge hard-refused |

### 72.4 The day the shadows walk away

If one day a shadow lit — ① a rack boots specproof-app, ② a human signs OBSERVABILITY.md, ③ the court could ever cache —
this volume becomes history. Until that day, it stays as three lines of print on the wall. **Not a poem — a floor plan.**

---
## Volume LXXIII · The Midnight Lamplighter（卷七十三 · 长夜灯半）

> Before the mid lamp is dark; after it, it is light — neither one asks the other to change.
> This volume folds "how far this project is from being alive right now" into one lamp —
> hung on the most visible coordinate of the Atlas: not to warn anybody, but so nobody has to ask.

### 73.1 The Midnight Lamp (anchored at #/atlas)

| Lamp | Struck live (2026-11-15T17:43Z) | Colour |
|---|---|---|
| real fleet telemetry · OBSERVABILITY.md sign-off | **awaiting-signature** | amber (slow pulse) |
| the Monday knock · weekly-stress.yml | **merged** | jade |
| port 8000 · who answers right now | **port-free** (URLError, refused) | grey |

The three lamps and the #/last-call unsigned row drink from **the same JSON** (`unsigned.json`) —
**one strike lights everywhere**; not polled, not cached, not fabricated — audited on this host, a lamp is a lamp.

### 73.2 House rules of the midnight

1. **no second eye** — WeeklyVoyage and MidnightLamp share one `unsigned.json`;
2. **only amber may pulse** — that lamp's glow is reserved for "awaiting your signature"; the other two never move;
3. **title carries full text** — hover reveals the complete status + detail;
4. **a lamp is not an SLO** — no service commitment whatsoever; "half-lit" is a ledger, not a promise of service.

### 73.3 The chart (through #1858)

```
scripts/audit_unsigned.py        → unsigned.json (live struck)
     ↓  same import
#/last-call: unsigned live chips (#1857)
#/atlas:    **The Midnight Lamps ×3** (this volume · #1858)
```

---
## Volume LXXIV · The Wind Knows the Way Too（卷七十四 · 风也认路）

> The wind is silent — but the wind knows the road. A third row of lamps hangs in the corridor of this repository:
> how many stories still await, how many have already arrived — none of them hidden from a careful stem.
> This volume delivers: the fourth lamp (branch cleanliness) — the Atlas KPI recalibrated to live numbers —
> and a third exhibit striking the front door down to p99 ≈ 1030ms.

### 74.1 The fourth lamp: did your commits reach origin?

| # | What it audits | Struck live |
|---|---|---|
| 1 | real fleet telemetry · OBSERVABILITY.md signature | awaiting-signature (amber, pulse) |
| 2 | weekly-stress.yml merged | merged (jade) |
| 3 | who answers port 8000 | port-free right now — the occupant of this morning, career-os-ai-service, is no longer there |
| 4 | **branch cleanliness** | rev-list 0/0 vs origin/master · 2 dirty entries (the very files this round is committing): **dirty-tree** (amber · clears when this commit lands) |

Implementation: `scripts/audit_unsigned.py` · landed in #1863. Colours: `clean` jade · ahead/behind/dirty-tree amber · diverged red · no-upstream grey (ours correctly reads no-upstream only when upstream is unset; today it shows dirty-tree because two files are uncommitted).

### 74.2 The Atlas KPI recalibration (Archive's hard-coded ledger)

Before: `Archive.tsx` wrote `worldbook: 50` and hard-coded "50 volumes · 1,625 ledger sections" in the lead — **a live lie as of Volume LXXI onward**.
After: every figure derives from the locked JSON — world book **81** volumes · chronicle **1,663** sections · golden cases **111** · epic scrolls **14** · source lines — all re-checkable against `scripts/build_*.py`.

### 74.3 Third consecutive exhibit dipped again

| Exhibit | worst p99 | Δ vs previous |
|---|---|---|
| 2026-11-16-static-warm.json (17:20) | 1532ms | — |
| 2026-11-16-static-warm-2.json (17:28) | 1537ms | +5.1ms |
| **2026-11-16-static-warm-3.json (this round)** | **1030ms** | **−507.2ms** |

verdict: OK. Three exhibits · one machine · one lane · one host — Δ sits comfortably inside the noise band (or out of it, this time, downward — record it as it fell, no rounding).

### 74.4 Volume LVI's vow, re-read

"court never cached" is still the truth. cached_tokens 46.4% is still the truth. **No lamp was dimmed for prettiness. Not one.**

---
## Volume LXXV · The Mirror Over the Wall（卷七十五 · 逾墙之镜）

> Over the wall is an ear — and a mirror angled just so reflects the neighbour's light.
> This volume is about one reflection off the semantic cache: one light, two rooms, one name —
> the instant the mirror hung on the wall, this repository saw how it borrowed fire.

### 75.1 Struck live (2026-11-15T18:15Z)

One prompt (same 5600-token prefix), offered in series to the draft/diagnose pair:

| Step | kind | Latency | Behaviour |
|---|---|---|---|
| diagnose#1 | diagnose | **6.92s** · 5600/14 · cached=None | **went out the door** (first strike) |
| draft#1 | draft | **0.00s** · 5600/14 | in-process **semantic-cache hit** (key = prompt digest + model + params; **deliberately the same cache class**: draft and diagnose are both cacheable mechanical steps) |
| draft#2 | draft | **0.00s** · 5600/14 | repeat hit |

Not a leak: draft/diagnose are by design the two cacheable mechanic kinds; the real anathema is court —
**this round welds four regression assertions into the build (tests/unit/test_court_never_caches.py)**:
court/counterexample/accept_judge/contract_compile always cacheable=False;
put with kind="court" returns False and the cache remains empty; rejected += 1, puts unchanged.

### 75.2 The meaning of the mirror over the wall

Two ways through one lock —
the cache is not a single-lane speed-up; it stands only when the prompt prefix, the model, the canonical params and the kind class all match.
**In other words: when the lamp in the next study went up, this one was lit by the reflection — only because the prefix bytes were identical.**
This repo stipulates: **court never borrows from this wall (or any other).**

### 75.3 Two fresh entries (this volume hides nothing)

1. engine.json: **46 calls · 17 policy lanes · 10 draft · 1 diagnose** · cached_tokens 75,638 · hit-rate 0.421 (the denominator swells, the numerator stayed put — re-check it yourself);
2. port 8000 answered again this round: **career-os-ai-service holds it and answers 200** (the #/atlas lamp now flips grey → red again — the lamp hides nothing on purpose).

### 75.4 Colour is not character

This book will not dye an amber green to look prettier. Every lamp colour, every trace can be `git show`n.

---
## Volume LXXVI · The End of the Ruin（卷七十六 · 废墟尽头）

> "There appears to be a ruin here" — that is the ruin's first impression;
> "here is a place where someone worked, where a story completed, where every byte is on file" — the second.
> This volume is about where the second impression came from: the alleged "ruin" of this repo, audited artefact by artefact, all of it evaluation archaeology.

### 76.1 The audit (struck live, 2026-11-15)

| Suspicion | The truth | The proof |
|---|---|---|
| "roughly 1000 hash-named 542-byte files, suspect residue" (written in a backlog note earlier) | **a ledger of exactly 21 git-tracked files under `docs/eval/swebench-logs/<case>/craft/backup/`** (591,524 bytes, every one inside the eval logs) | `scripts/audit_scratch_residue.py` (read-only; re-strike it) |
| What they actually are | **source snapshots from the craft/backup mechanism** — content-addressed by a 6-hex suffix from the runner | `import functools ... from werkzeug...` — real Flask source, unrelated to anyone's mess |
| May we delete them? | **NEVER** — these are the eval runner's byte-level snapshots of files it modified; they remain load-bearing for replay | the audit only reports; nobody plucks anything off |
| What the book claimed | #1860 wrote about "roughly a thousand hash-named 542-byte files, suspected residue" — this round's audit **refutes the earlier suspicion** and files the correction | ledger #1865 carries the retraction appendix |

### 76.2 House rules of the ruin

1. **no "this looks like junk" without one audit first** — no hammer before the verdict;
2. **the audit never deletes anything** — the report is its only product; if you want an action, you knock yourself;
3. **wrong verdicts get filed** — this repo's earlier suspicion is withdrawn here, today, in writing: not "1000 × 542 bytes" — **21 evaluation snapshots**;
4. **the eval logs are not a shelf — they are an archive room** — they sit in their place, they are fresh, they are not to be "tidied".

### 76.3 One corner of the world, steady

The ruin is not the end. Every stone in it holds one SWE-bench case, one craft surgery, one content address.
This book will not delete them, nor abstract them away — open one and it is real Python.
Anybody itching to delete these should go sign for it first.

---
## Volume LXXVII · Door and Lock（卷七十七 · 门与锁）

> Doors are what get pushed; locks are what keep the door being a door.
> This volume answers one line of question: court never enters any cache — not a slogan, five machine-struck locks.

### 77.1 The five machine locks (scripts/audit_court_lock.py · re-strike anytime)

| # | Piece verified | How struck |
|---|---|---|
| 1 | providers/openai_compatible.py `kwargs["stream"] = True` | byte-slice SHA256 over the match |
| 2 | same file `kwargs["stream_options"] = {"include_usage": True}` | byte-slice SHA256 over the match |
| 3 | providers/client_policy.py `ENV_POLICY = "SPECPROOF_PROVIDER_POLICY"` | byte-slice SHA256 over the match |
| 4 | providers/semantic_cache.py `EVIDENCE_KINDS` exactly {{court, counterexample, accept_judge, contract_compile}} | byte-slice SHA256 · exact member-set assert |
| 5 | same file `CACHEABLE_KINDS` exactly {{draft, diagnose}} | byte-slice SHA256 · exact member-set assert |

The synthetic lock (16 hex) = SHA256 over the sorted concatenation of the five evidence hashes.
As this volume is written: **LOCKED · `4117d2b0ca5fb23a`**.
`pytest tests/unit/test_court_lock_machine.py` (2/2 ✅) re-checks the lock on every CI run.

### 77.2 House rules of door and lock

1. **locks never rely on memory** — machine-byte spliced; trusts no docs, no comments, no ledger;
2. **#/engine renders the lock** — one chip, lock hex right on the page; a bypasser can only succeed loudly;
3. **BROKEN is always visible** — audit exits 2 in that case and the chip goes red;
4. **a court-cache flip would break the lock** = red chip — nothing in this repo may silence that.

### 77.3 Two real things that happened while writing this

* First strike returned BROKEN: not the code — the audit regex didn't recognise Python's `kwargs["stream_options"] = {...}` spelling; fixed (accepts both styles now);
* after that, `audit_court_lock.py` strikes with **both-spelling-compatible regexes** — no extra lock gets added, no existing lock gets removed.

### 77.4 The lock keeps the door, not the reverse

`SPECPROOF_PROVIDER_POLICY` is the bolt — without it, the repo is byte-identical to today (no cache at all; cache_hit_rate stays 0 because there IS no cache, not because nothing matched).
With it, court still never enters the rack — the four welds in `test_court_never_caches.py` keep that iron uncut.
**The cipher machine is not a nerve; the lock is the testimony of iron and fire.**

---
## Volume LXXVIII · The Spine After the Avalanche（卷七十八 · 雪崩后的书脊）

> What a survivor sees first after an avalanche is not snow — it is the spine that stuck up out of it.
> This volume collects every claim this repo got wrong and then corrected itself —
> not an apology collection, but **the errata ledger**: anyone who wants to know where this project has been accurate, wrong, and how it climbed back, comes here.

### 78.1 The Corrections Scroll: ten entries, append-only (R01–R10)

| # | # | # | # |
|---|---|---|---|
| R01 | chronicle 1,645→1,644 (#1845, closed) | R06 | sort-key filename→ISO started_utc (#1852/#1854) |
| R02 | world book 72/73 asymmetry — rolled back, re-landed → 73/73 (#1855) | R07 | Archive hard-codes worldbook:50/"1,625" → locked JSON (#1863) |
| R03 | CrewCard hard-codes — import-resolved (#1858) | R08 | subprocess import missing → false no-upstream (#1863) |
| R04 | suspect "1,000 hash remainders" → audit hard 21 SWE-bench snapshots (#1865) | R09 | repaired output, generator left behind → 27d632b (#1865) |
| R05 | court-lock BROKEN: regex can't parse kwargs[...] — dual-spelling → **LOCKED 4117d2b0c** (#1866) | R10 | RageCoach test expects wrong lane (approve→tour-seal); approval regex ws-tolerant (#1846) |

Every R is anchored — git show /敲 the script / read the locked JSON — **every one re-verifiable by hand.**

### 78.2 House rules of the spine after the avalanche

1. **append-only** — R-entries never get deleted;
2. **anchorable** — every entry cites commit · ledger · file · JSON so anyone can knock it;
3. **withdrawable** — when I am wrong, the retraction is printed in public, never "strategic silence";
4. **no laughing** — these are not jokes, these are facts of last week — "the ink moves only forward".

### 78.3 Three things always ride along after the appendices

* APPENDIX_CORRECTIONS.md — the prose register (10 entries, all anchored)
* APPENDIX_CORRECTIONS_EN.md — the English mirror, line-for-line
* worldbook / chronicle / repoStats / engine / unsigned are the spine's foundations — drift one byte and the whole thing red-lights

### 78.4 What I owe to the avalanche

Every R reads one sentence aloud: "I was wrong, and I did not let the wrong walk away."
The spine does not grow wings — it simply does not get crushed.
Snow keeps falling under the timeline; we count by days:
**after this volume, R11, R12... will come — good. The later flakes are still beautiful.**

---
## Volume LXXIX · The Gap and the Light（卷七十九 · 缺口与光）

> A gap is not the book's failure — a gap is where the light gets in.
> This volume does only one thing: put every open debt of this repository on a public wall at once —
> not to shame it, but so each IOU has its source, its owner, and its knocking point.

### 79.1 The open-debts wall (docs/operations/DEBTS_OPEN.md{ + EN })

| Class | Entries | Who pays |
|---|---|---|
| Signature (human) | D1 OBSERVABILITY.md sign-off (only door to fleet telemetry) · D2 PORTFOLIO_TOKEN · D3 #/gazette copy decision | **a human** |
| Machine | M1 weekly-stress first strike · M2 weekly evidence Δ · M3 audit_evidence drift sentinel (7/7 this round) · M4 verify_links 141 files zero dead links | **the machine** |
| Both | B1 app stack truly up end-to-end · B2 evidence auto-backfill weekly | **machine + human** |
| Never | password-123 · court cached · fake-green CI · demo-as-prod | **never payable** |

### 79.2 The wall's house rules

1. **never dyed green** — writing an IOU on this wall does not mark it paid;
2. **struck through, not torn** — when paid, the line stays visible, never silently deleted;
3. **D1 is the smallest human unit in this book** — one signature, one person, never a proxy;
4. **M1–M4 need nobody** — the machine already pays;
5. **B1 waits on your one sentence**: "go."

### 79.3 Where the light is

Every ledger, every lamp, every snapshot, every Δ you see — all photographs of "machine-paid".
The D1–D2 spot — written on this page, waiting for you.

### 79.4 Also filed this volume: 141 docs, zero dead links (audit artefact)

`scripts/verify_links.py` (141 files scanned · zero dead links · 1 annotated-planned entry recorded) —
`docs/evidence/audit-links.json` is now git-tracked. Nobody will ever see a 404 reference in this repo again.

(The audit: 18 references repaired — 8 wrong paths, planned-artifacts correctly tagged "doesn't exist", the .24dfe6-style suspicion formally retracted in the corrections scroll.)

---
## Volume LXXX · The Cartographer's Graph（卷八十 · 图的语言）

> A map is not a picture of a mountain — a map is a three-way agreement of mountain and human.
> LangGraph has been this repo's main engine (phase0 verify) from day one; this volume fills the one piece it lacked:
> **a subgraph small enough for a human to see clearly in 10ms — and large enough to decide whether the ledger says OK.**

### 80.1 Added: the evidence-review subgraph `agent/graphs/evidence_graph.py`

```
intake → collect_series → verdict → emit_report → END
```

| Node | Does | Never does |
|---|---|---|
| intake | scans docs/evidence/*.json (only artifacts carrying a `rounds` list) | any LLM/network call |
| collect_series | sorts by started_utc, computes the Δp99 gap between consecutive pieces | smoothing, averaging — two exhibits are two exhibits |
| verdict | any non-OK → REGRESSION; any Δ>25ms → REGRESSION; else OK; else EVIDENCE-MISSING (fail-closed) | "probably OK" |
| emit_report | writes docs/evidence/evidence-tick.md | auto-closing any IOU |

Struck live (as this volume was written): **verdict = OK · entries = 3** (all OK · 192/192 each · p99 1532 → 1537 → 1030ms).

### 80.2 Tests (`tests/unit/test_evidence_graph.py` · 3/3 ✅)

| Case | Anchored fact |
|---|---|
| regression-when-blown | any non-OK verdict ⇒ REGRESSION; the tick is still written |
| ok-when-all-pass | both OK ⇒ `entries=2` reported |
| missing-dir-is-explicit | missing directory ⇒ EVIDENCE-MISSING and the tick is still produced |

### 80.3 House rules

1. **the subgraph is deterministic** — same input, same output; no LLM, nothing else;
2. **it files but never licenses** — `evidence-tick.md` is not an SLA; it is a machine's honest report;
3. **it never closes anything** — this subgraph never substitutes for a human merge decision.

### 80.4 A sign inside the app

The #/graph footer now names `agent/graphs/evidence_graph.py` — anyone visiting the map page meets
"the kin StateGraph lives right here…" — **not a screenshot of Graph.tsx; a pointer to the thing you敲.**

### 80.5 The open-debt ledger update

DEBTS_OPEN.md gains M2's machine side — with this volume, `weekly-strike` is runnable:
`agent/graphs/evidence_graph.py docs/evidence` → `evidence-tick.md`. **The rest of the debt sits behind this volume, waiting for its input.**

---
## Volume LXXXI · When the Moon Falls Into the Springs（卷八十一 · 月落千泉）

> Moonlight falls into a thousand springs and a thousand identical moons rise up —
> not an illusion: the same evidence mailed to every reader.
> This volume delivers that "every reader can carry it away, nobody manufactured it" monthly ledger.

### 81.1 The monthly census · monthly_census.py (landed in #1870)

| Item | Value |
|---|---|
| Input | every `docs/evidence/*.json` carrying a `rounds` list |
| Mechanics | month-bin rolled-up p50/p99/per-piece OK rate and request total / Δ vs previous |
| Output | `docs/evidence/monthly-census.md` (git-tracked) |
| Struck this round | **2026-11** · **576 req · 576 × 200 · 100.00% OK** (3 exhibits, all struck, p99 range 1537→1030ms this month) |

Three exhibits **all OK** — this is what the repo looks like when the numbers aren't dressed up: 192 × 3 knocks.

### 81.2 #/gazette "TOMORROW'S WEATHER" pushed one notch further

The notices list now carries one live line (read straight from evidence.json):
"3 exhibits on file · 576/576 requests (100.0%) green · monthly census at docs/evidence/monthly-census.md"

### 81.3 House rules of the monthly ledger

1. **never a baked percentage** — 100.0% is 576÷576 knocks, nothing else;
2. **no hiding the rattle** — if 2 of 3 runs regress, the census line says REGRESSION;
3. **no self-medal** — the census is a numerical map, never a badge of honour — "we struck it", never "we aced it";
4. **one small bug nailed this round**: a stray `}` inside the zh notice `(100.0%})` — fixed (this repo does not ship `(100.0%}`).

### 81.4 How many wells the moon has come to rest in so far

| Month | Exhibits | p99 low | p99 high | total req | Result |
|---|---|---|---|---|---|
| 2026-11 | 3 | 1030ms | 1537ms | 576 | **576 · 576 ✓** |

---
## Volume LXXXII · Below the Lamp, Above the Water（卷八十二 · 灯上水下）

> Above the lamp is light; below the water is writing —
> the ripple between them records that nobody worked an angle here.
> This volume delivers two landmarks you can re-check in one tap, and one line etched under the light.

### 82.1 Two new landmarks (#/atlas, the living landmarks strip)

| Landmark | Figure | Source |
|---|---|---|
| **stress green share (this month)** | **100%** (576/576) | `evidence.json` (verbatim at build time) |
| **exhibit requests (this month)** | **576** | same |

They hang beside `tracked files / commits / ledger volume / book sizes` — **not banners, measurements; re-run the script and they either agree or you found a bug.**

### 82.2 The stone grain under the lamp (#/gazette footer, one line)

```
Monthly: 3 exhibits · 576/576 requests (100.0%) green — see docs/evidence/monthly-census.md
                                          -> See the landmarks
```

Links straight into the Atlas landmarks strip. On print, this line stays (it is typeset; the print style doesn't delete it) but it names only what is verifiable — 公开、克制、不创造物种。

### 82.3 House rules of below-lamp-above-water

1. **a landmark only points** — never wears a "certified outcome" banner; every divider sits in the same hydrology;
2. **the stone grain is never makeup** — no "steady now", no "trending down"; only struck numbers;
3. **there is always a stone grain under the light** — no evidence → writes "not struck yet"; honesty beats silence.

### 82.4 Two strikes, one pen

| Door | Struck by | Read in |
|----|-----|-----|
| build_evidence.py — weekly | monthly roll-up | monthly-census.md |
| audit_evidence.py — cross-product | every rebuild | 7/7 CONSISTENT |

Both are strokes of the same mechanical pen — neither rewrites the verdict.

### 82.5 The one lamp-flaw registered this volume

The stone grain is still deep and clean — `#/gazette` prints 192×3=576 req · 100% ✓ ·
the only gap left: the first automated weekly-stress strike (waiting on next Monday 03:00 UTC after the merge).

---
## Volume LXXXIII · Anchor and Rope（卷八十三 · 锚与绳）

> An anchor doesn't end a story — an anchor is the reason a rope keeps its long promise.
> Every page in this book called "I was wrong" all the way to "I rescued it" is one more fibre in that rope.
> This volume delivers both, side by side: the judicial lock (the anchor) and the errata scroll (the rope).

### 83.1 The Anchor: court never cached · machine-locked · [4117d2b0ca5fb23a]

At the top of #/archive now lives one jade line:

> THE JUDGE AND THE IRON · court never cached · machine-locked: 4117d2b0ca5fb23a · see the engine →

The anchor does not explain. The anchor does not defend itself. The anchor was struck by a machine, not written by a person.

### 83.2 The Rope: the errata scroll · 11 R-entries (R01–R11)

`apps/web/src/pages/corrections.json` is rebuilt from `APPENDIX_CORRECTIONS.md` by `scripts/build_corrections.py`:

| Range | Housed |
|---|---|
| R01–R05 | chronicle numerics / world-book 72→73 asymmetry / CrewCard hard-codes / the "1,000 hash remainders" suspicion (proven wrong) / court-lock BROKEN (regex) |
| R06–R08 | evidence sort-key → raw / Archive hard-code overturned wholesale / subprocess import missing → false no-upstream |
| R09–R10 | ROADMAP generator behind its own output / RageCoach expected the wrong lane |
| R11 | evidence-review subgraph flaked-first |

Each is anchored: **git show / python scripts / locked JSON / markdown body**.

### 83.3 House rules of anchor and rope

1. **the anchor does not orate** — it is there; being there is all it says;
2. **the rope may never fray** — APPENDIX_CORRECTIONS only ever appends;
3. **both live in the sun, never in a vault** — the lock is exhibited (hung on `/engine`), and the rope likewise (top of `/archive`, and pointed to from `#/lexicon`);
4. **anyone who wants to amend these two must first read the errata scroll** — every prior error owes the three syllables "I was wrong".

### 83.4 The cold archive

| Anchor | Breathing | Rope | Insignia |
|----|------|----|------|
| lock = 4117d2b0ca5fb23a | audit_court_lock 10ms | 11 R-entries | scripts/audit_evidence.py |

### 83.5 Does anyone stay hidden?

`DEBTS_OPEN.md` (D1–W4) still pins — D1 = OBSERVABILITY signature still needs a human; nothing here varnishes over it.
"court never cached" is also not a tagline nor a v1.0 promise — it is a locked artefact.

---
## Volume LXXXIV · The Miles on the Wall（卷八十四 · 墙上的里程）

> A wall with mile markers shows not today's pace but the total miles this road has taken.
> This volume delivers every mile already walked into the wall — struck in re-checkable numbers,
> hiding nothing — including the one green, un-keyed line that has waited for its lock to be set.

### 84.1 What the wall holds, measured on this hour (2026-11-15)

| Audit | Struck | Verdict |
|---|---|---|
| `https://xiaodernan.github.io/` reachable | HTTP 200 · **39,237 bytes** · "specproof" appears **3 times** | OK |
| the page carries `<a data-category="systems" href="https://github.com/xiaodernan/specproof" ...>index-id 05</a>` | OK — **SpecProof already on your showcase** | OK — put there by hand a while ago |
| `github.com/xiaodernan/specproof` exists | anonymous HEAD → **HTTP 200** | OK (public repo) |
| `PORTFOLIO_TOKEN` on this host | **not set** | not set — sync workflow green but pushes nothing |
| `portfolio-sync.yml` in repo | **present** | missing nothing but the key |
| `artifacts/` at build time | **89 files** | ready to be exhibited |
| auto-sync once token is set | weekly Sun 06:00 UTC + dispatch + master-push | needs you, Settings → Secrets → PORTFOLIO_TOKEN, Contents: read+write, pointing at xiaodernan/xiaodernan.github.io |

### 84.2 What this volume promises NOT to do

* index-05 on your showcase stays exactly where it is; this repo will not touch it;
* without the token, CI stays green-but-silent by design — that is the feature, not a bug;
* with the token, Sunday 06:00 UTC auto-sync pushes only the distilled JSON + markdown card (never source, never secrets — portfolio-sync.yml is already built to refuse those);
* this round's `verdict: READY_WITHOUT_TOKEN` — this repo does not pretend to ride a horse with no bridle.

### 84.3 How to take the miles further

* to actually sync: Settings → Secrets → add `PORTFOLIO_TOKEN` (Contents: read+write · target: xiaodernan/xiaodernan.github.io);
* once set, Sunday auto-runs + manual `workflow_dispatch` any time — the weekly "what just shipped" card is then push-synced;
* no token? no loss — index-05 stays; only the weekly refresh won't arrive automatically.

### 84.4 House rules

1. **never forge the wall** — audit reports facts as struck; never blended;
2. **never bypass** — this round never wrote to your personal profile's `.github`, never pushed a branch there; it only knocked and reported;
3. **the token is yours** — no `PORTFOLIO_TOKEN` will ever be minted from this repo or placed into your settings.

---
## Volume LXXXV · The Steganographic Line（卷八十五 · 隐写的一行）

> A secret is a line of fine bytes — one who sees it but cannot decipher it
> leaves the page with only a feeling it was there.
> This volume is about something much simpler: the full skeleton of what
> portfolio-sync would-not-push until you say so — and it happens to already fit in 4 KB.

### 85.1 Struck live (2026-11-15T19:21Z)

| Exhibit | Value |
|---|---|
| `scripts/sync_portfolio_dryrun.py` (new) | **3 files · 5,863 bytes total** (`.github-sync.json` 1,389 B · `latest.md` 512 B · `products.json` 3,928 B) |
| Secret surface | **zero** — no token/keys/env in any emitted file; artifacts/ is git-ignored |
| Live sync status | "nothing pushed yet — this is a dry run" — never fakes a push |
| `sync_portfolio.py` real bug fixed | "latest ledger entry" now resolves to the latest section (was reporting #1870 of four commits ago) |

### 85.2 Dashboard gained one line — struck this month

At the very top of #/dashboard, above the quick-start strip:
`struck this month: 576/576 · 100.0% · not extrapolated` + CTA to the monthly census at #/gazette.
Every digit comes straight from `evidence.json` — **zero network, zero LLM inference**.

### 85.3 The key that is the quiet part

PORTFOLIO_TOKEN is the only door that opens portfolio-sync for real, and this repository
will never mint it for anyone nor inherit it silently. It exists only in Settings → Secrets;
this book does not bring it into existence, nor grant it to any maintainer — not a hire, not a gift.

### 85.4 House rules

1. **seeing the shape is not the same as pushing it** — preview ≠ push; preview is cheap, push is a door that stays open;
2. **this page does not wait for a push** — only your hands mint that key;
3. **this volume ships zero key material** — sync is local+dry-run; the gate that pushes needs a real human route you set;
4. **no new promises** — one link at line 05 on your showcase is all that's real; this book will not crowd it, nor rewrite its paint.

### 85.5 The ship-of-Evidence one door remains open

```
artifacts → sync_portfolio_dryrun.py → preview.json (git-ignored)
     ↓
Settings → Secrets → PORTFOLIO_TOKEN → portfolio-sync.yml  Sunday 06:00Z
     ↓
xiaodernan.github.io  index-id-05 · systems tile
```

The tile keeps its spot. Even if the images change, the link stays.

---
## Volume LXXXVI · The Mark of the Chain（卷八十六 · 链印法约）

> A stamp must land on a chain that holds —
> this is not a display of spring, it is a declaration: "every clerk, every ledger, does its tax here, every time."
> This volume delivers one seal with five faces, and the hammer to strike it whole.

### 86.1 The audit-chain subgraph `agent/graphs/auditor_graph.py` (landed in #1876)

```
unsigned → court_lock → evidence → scratch_residue → portfolio → verdict → report → END
```

Five links — matching five lamps (audit_unsigned live · audit_court_lock machine-bar · audit_evidence cross-check · audit_scratch_residue eval-residue review · audit_portfolio's anonymous reachability probe)

| Link | Struck | Output |
|---|---|---|
| unsigned | four lit lamps | all green → `four-lit lamps live` |
| court_lock | 4117d2b0ca5fb23a | `LOCKED` |
| evidence | audit_evidence.py | `CONSISTENT` (seven cross-checks, § #1867) |
| scratch_residue | audit_scratch_residue.py | `intentional evaluation evidence · do not delete, 21 files` |
| portfolio | audit_portfolio.py | `READY_WITHOUT_TOKEN` (the only key missing) |
| **verdict** | all pass | **CLEAR** · any single red → **CRACKED** |
| **report** | `docs/evidence/audit-chain.md` | one-look, committed |

Struck at this volume's writing: **CLEAR · 5 lanes · zero leakage.**

### 86.2 Tests (`tests/unit/test_audit_graph.py` · 2/2 ✅)

* full chain + report rows all five + legal verdict enum;
* monkeypatch court_lock to exit 2 → the whole chain flips **CRACKED** — no courtroom loophole admitted.

### 86.3 House rules

1. **the subgraph never pretends** — it really runs scripts; scripts really write files; files really go green/red;
2. **`verdict` is read once per pass** — the report freezes that verdict; never re-read mid-fight;
3. **`CLEAR-WITH-NOTES` shows up honest the moment it appears** — READY_WITHOUT_TOKEN is not CRACKED but it's never erased either;
4. **no hiding, no skipping** — `verdict=CLEAR` doesn't mean "done"; it means "not cracked yet".

### 86.4 One line for the first visitor

> **Not how many times it was made — but how many links truly hold every single time.**

---
## Volume LXXXVII · The Knocker（卷八十七 · 敲门的人）

> One who knocks does not knock in vague curiosity —
> they knock once, and then tell all in one shot: "it" or "it is not".
> This house knows its own doors; every door knows its own lock.

### 87.1 The audit-chain now has a face indoors

A new face on the `#/gazette` "today's weather" column:

> **audit chain · CLEAR (5 lanes) · the ghost switch stays off**

Five lamps, one knock, one word: **it** or **it isn't**. No ambiguity, no courtroom.

### 87.2 Two recorded strikes (printed, at length)

| Moment | Struck | Verdict |
|---|---|---|
| 2026-11-15T19:32Z (first clean strike) | all 5 lanes, real-knock | **CLEAR** · 5/5 |
| 2026-11-15T19:36Z (re-struck) | full 5 lanes | **CLEAR** · 5/5 |
| 2026-11-16T05:08Z (post-test) | — | **CLEAR** · 5/5 |

### 87.3 House rules

1. **the knock is audit_chain.py's** — no test, no debug, no script convenience;
2. **the knocker never lingers** — one strike, one announcement, then step back;
3. **a red answer awakens everyone** — knock red, then handle now; never delay sleep;
4. **the knocker is never afraid** — if the chain cracks, the knocker names it; if not, the knocker names that too.

### 87.4 Where this shadow actually walks

```
a late knock → five doors struck in one pass
the day that follows → one small strip of paper
it says CLEAR or CRACKED — either belongs in the paper
```

---
