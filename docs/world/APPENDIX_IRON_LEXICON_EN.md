# Iron Lexicon · SpecProof Glossary

> This dictionary is not a set of definitions; it is the **inspector's tab index** — every entry can be pointed at a precise location in the repository.
> Every entry comes from code that has already landed and really run — nothing invented.
> If you read this dictionary in English: also read `SPECROOF_WORLD.md`.

---

## Z

### `cold floor` — thickness of the frozen prefix
> World-iron context: measured by `lane_cache_probe.py` (2026-11-18T06:46Z, 13/13 strikes ok across five lanes). The 4.8 % cold floor is the structural bill for the byte-frozen prefix (codex + covenant binding + lane preamble) — not a cache fault; warm strikes pin at 93.9–94.0 %.
> Located: `scripts/lane_cache_probe.py` · `docs/evidence/lane-cache-probe-2026-11-18.*` · ledger `#1995`.
> Sense: this is not a bug, it is an invoice — do not paint it a verdict.

### `dual-value drift` / 双值缝
> World-iron context: the seam where one fact exists as two numbers in two ledgers at once. At the instant scroll #196 landed (07:17Z tile read 1,791/196 while #197 had not landed), later at 07:51Z (tile read 1,792/197). The `#1997` gazette epigraph itself pointed at this seam; no human named it first.
> Evidence: `docs/evidence/gazette-feature.md` ("现场瓦片验收记 1791、196 卷") · ledger `#1997` §2 · Scroll CXCVIII §198.2 · Scroll CXCIX §199.2.
> Sense: the seam is not an error — the seam is time. When your eyes see two numbers, open the ledger; do not pick one to shame the other.

### `epigraph` — front-page echo / TODAY'S ECHO
> World-iron context: `scripts/gazette_feature.py` hands the newest ledger section (`## #NNNN`) verbatim to aizzz; the model may print at most 280 CJK characters / 220 words; anything past the mechanical gate does not land. Output: `gazette_feature.json`, rendered directly beneath `#specproof-live` on the io page; recorded as "as model-written".
> Evidence: `apps/web/src/pages/gazette_feature.json` (2026-11-18T09:38:24Z) · ledger `#1997` · Scroll CXCVIII.
> Sense: word ceilings, the mechanical gate, non-verdict — not an exhibit, not a ruling.

### `fact pack` — the machine-struck brief
> World-iron context: the `docs/latest.json` that `scripts/build_latest.py` produces — commits / scrolls / chronicle / exhibits / strike all derived inside the repository this minute; a shallow clone self-destructs (`fetch-depth: 1` once emitted `total_commits=1`); `latest_strike` falls back to the last `## #NNNN` in the ledger.
> Evidence: ledger `#1981` (shallow-clone history) · `#1993` (the fallback patch) · `#1994` · `docs/operations/DEEP_OPTIMIZATION_PLAN.md`.
> Sense: machine-struck accounts may be shown to pages; no strike reaches a page without a strike first.

### `inline derivation` — deriving from the same tree
> World-iron context: `sync_portfolio.py`'s fact pack is derived inline at HEAD (world-bible `## ` count + ledger `#NNNN` count + `git rev-list` / `ls-files`) — it does not re-use `docs/latest.json` with its bot re-strike cadence; it removes the one-strike lag inherent to latest-json's path filter; the sync workflow now checks out `fetch-depth: 0`.
> Evidence: ledger `#1996` §1 · `.github/workflows/portfolio-sync.yml` · `scripts/sync_portfolio.py`.
> Sense: anything that moves with HEAD, read yourself right now, don't wait for someone else to finish reading.

### `LIVE SHIP` — the live window
> World-iron context: `index.html#specproof-live` on the io page; fetches `./data/specproof-sync.json` (+ products + gazette), renders head · scrolls · chronicle · exhibits · strike · changelog; machine-struck end-to-end; no human hand edits a single digit.
> Evidence: `#1994 / #1996 / #1997 / #1998` live-verification records · `.github/workflows/portfolio-sync.yml` (every master push re-strikes the payload).
> Sense: numbers on the homepage come from exactly two sources — the machine-struck fact pack, or the older value the machine refused to write up (the latter never reaches the wall).

### `parallel copies` — 复份
> World-iron context: multiple parallel sessions (parallel agents / repo probes / bot re-strikes) pointed at the same repository, each writing its own account: CÆSURA 《摆旁的灰》 line KI-677~680, the io page's ORACLE strip, nexus-content sync, `SPECPROOF_EXHIBIT_COPILOT_PROXY` — all are instruments of 复份.
> Evidence: `git log --date-order --oneline -20` · ledger `#1994`, `#1997` (rebase-and-merge wrap-ups recorded there).
> Sense: duplication is not an error; but each copy must write its own account, sign the commits it made, and leave others' landings untouched — RMH (rebase-merge-hand) means keeping the base, pushing your layer, never settling the bill for someone else's dinner.

### `strike` — to strike / to probe
> World-iron context: the only language this repository honors — every LLM call, every probe, every build, every CI run is a strike; numbers must land in `docs/evidence/*`; unstruck, untrusted, unwritten.
> Evidence: the whole `docs/evidence/` directory · ledger `#1995` onwards · any "they say / should be" belongs in no ledger.
> Sense: a strike is a strike; it is not more authoritative for being re-cloned and re-run, nor weaker for admitting what it saw.

### `warm-up rotation` — hot/cold line rotation
> World-iron context: at dig #1, tester & security were already warm (an earlier same-prefix probe had written the line), explorer was cold; at dig #2, explorer was warm and tester rotated cold. Same cache key, distinct cache lines — different prefixes hold different slots. Not disorder; merely pre-warming.
> Evidence: `docs/evidence/lane-cache-probe-2026-11-18.md` addendum rule 4 · ledger `#1995`.
> Sense: rotation of warm/cold lanes is not cache failure; it is what happens when you guess slots instead of knowing them.

---

## The Seal — Verify

> Verified does not mean "wanted to pass"; it means **the evidence passed on its own**.

Every iron-evidence entry is verified, every volume a re-verification.

*If you find "all done" somewhere else, first look at the matrix for the unverified cells —*
*the iron matrix verifies before it certifies.*
