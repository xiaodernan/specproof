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
| Full `pytest tests/unit` | **Unpaid** — local memory fell to ~1.8 GB; only the ledger four + the new gate ran (51/51); this line is kept on the record, not whitewashed |
| `toneMap.ts` / `errorHints.ts` Chinese residue | **Unpaid** — locked by the severity-vocabulary parity test; needs its own work item before translation |
| Volume XV inside the app (`/epic` still shows six scrolls) | **Unpaid** — the book grew to fifteen volumes; bringing XV into `Epic.tsx` is the next commit |

### 15.5 For the next reader

* If you are a **user**: start at `#/tour`, stamp all six seals — you will know this system better than 90% of the repo's readers;
* If you are a **contributor**: pick any plot in 15.1, read Volume XIV first, then move —
  "what done looks like" is already written above; **the acceptance bar is not in your head, it is on this page**;
* If you are the **keeper**: new convention — every time a debt is paid, add a line beside 15.4;
  merge into master, and every page of this world is an archaeological layer of commits.

### 15.6 This volume's vow

Unfinished is not failure — unfinished is the map.
Every plot of open land has a name; every name has a "what done looks like."
That is the whole secret between "a vast world" and "one real commit at a time."

**Volume XV keeps no good news — it keeps IOUs, the map, and the relay baton.**
