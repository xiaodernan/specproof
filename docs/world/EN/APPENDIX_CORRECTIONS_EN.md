# The Corrections Scroll · 更正卷轴

> Every walk-back, every fix, every instance where I contradicted myself, all on this single page.
> It is not an indictment — it is a re-entrant handler for auditable failure:
> every correction carries its ledger number, its anchor, and a verifiable figure for the revision.
> Whenever this repository cites anything, it must not route around this page.
>
> Rules: ① the scroll appends, never deletes; ② every entry names its commit / ledger anchor;
> ③ anyone who wants to quote this repository must read this page first.

## Entries

| # | Wrong claim (time) | The correction | Withdrawn / fixed | anchor |
|---|---|---|---|---|
| **R01** | chronicle read 1,645 sections in #1845 dispatch (2026-11-16T13:2xZ) | the actual count is 1,644 | edited inline in the same ledger entry (#1845) | DEEP_OPTIMIZATION_PLAN §#1845 |
| **R02** | bilingual world book went askew: "zh 72 / en 73" (only EN got Volume LXVI at #1855) — the ZH side was skipped by an over-broad duplicate check matching "船期表" | both language bibles carry the same library; the detector must match heading boundaries, not a word | rolled the EN append back; re-detected with full heading; both landed at **73 / 73** | DEEP_OPTIMIZATION_PLAN §#1855 + git history |
| **R03** | CrewCard markdown shipped hard-coded "commits 2,499 · ledger 1,658 sections" (#1858) | every commit moves the count (+1); any printed number goes stale by construction | every number now resolved from locked JSON at generation time | §#1858 |
| **R04** | ROADMAP-LIVE item 5 charged "roughly 1,000 hash-named 542-byte files, suspect scratch" (#1860) | the real inventory: **21 git-tracked files (591,524 bytes), all under `docs/eval/swebench-logs/*/craft/backup/` — SWE-bench runner's content-addressed source snapshots** | `scripts/audit_scratch_residue.py` landed; the paragraph formally withdrawn at #1865; ROADMAP-LIVE item 5 re-rendered | §#1860 → withdrawn at §#1865 · `docs/evidence/audit-scratch-residue.json` |
| **R05** | the first `scripts/audit_court_lock.py` strike returned "verdict: BROKEN · lock c2ebdc0b…" (2026-11-15T18:24Z, #1866) | **not a repo bug — the audit's regex could not parse Python's `kwargs["stream_options"] = {...}` spelling** | both spellings accepted (kwargs[...]= and JSON-style); re-struck → **LOCKED · lock `4117d2b0ca5fb23a`** | §#1866 · `tests/unit/test_court_lock_machine.py` |
| **R06** | `build_evidence.py` chose "latest" by reverse-sorting **filenames** (2026-11-16T17:5xZ, #1852 v1) | same-prefix names reverse-sort wrong (`.json` beats `-2.json`) — highlighted the wrong exhibit | sort key changed from filename to ISO `started_utc` (lexicographic order = time order) | §#1854 |
| **R07** | Archive.tsx hard-coded `worldbook: 50` and "50 volumes · 1,625 ledger sections" in the page copy (live a long time; fixed in #1863) | **all of it was fiction by then**; the build chain had moved past 50→81 and 1,625→1,664 | every figure imported from locked JSON; KPIs re-derived at build time; one KPI tile added (Epic Scrolls) | §#1863 |
| **R08** | `audit_unsigned.py` first struck "branch-cleanliness: no-upstream" (2026-11-15, #1863 launch) | `subprocess` was never imported — the exception was silently swallowed by `except`, falling through to a silent empty string and the placeholder "no-upstream" | `import subprocess` at module scope + docstring bumped to four lamps; re-struck → correct: dirty-tree → post-commit clean | §#1863 |
| **R09** | the #1865 commit repaired the ROADMAP-Live **output** but not its **generator** `build_roadmap_live.py` | re-running yesterday's commit would regress the same wrong claim (item 5) | follow-up commit `27d632b` aligned both — ROADMAP-LIVE and its producer | git show 27d632b |
| **R10** | RageCoach tests expected `"Sign & seal"` → approve; rulemap actually owned it as tour-seal (the `seal` keyword wins) | the rulemap intentionally places seal-related signatures under tour-seal; expectation was written for the wrong lane | test expectation changed to tour-seal; the approve rule made whitespace-tolerant (`批\s*准`) | #1846 · `apps/web/src/ui/rage.test.ts` |

## House rules of the scroll

1. Entries never get deleted, only appended;
2. After every rebuild, `python scripts/audit_evidence.py` compares worldbook.json · chronicle.json · repoStats.json · engine.json · unsigned.json byte-for-byte — any drift is an automatic red and a new R-entry;
3. This page is not an apology page; it is the ledger of my own outright mistakes — every one of them shipped with its coordinates so you can re-knock it yourself.
