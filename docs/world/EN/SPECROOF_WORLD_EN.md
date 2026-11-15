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

This is not allegory — `experiments/differential.py`, the contract compiler, `apps/web/src/pages/Matrix.tsx`,
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
