# SpecProof Pocket Card — 30-Second Onboarding

> Print it (A4, single side). Keep it next to the keyboard. The full manual is
> `docs/operations/EN/USER_GUIDE_EN.md`; this page is only the
> "what must be in your head before you open the door".
> 中文版：[POCKET_CARD.md](./POCKET_CARD.md)

---

## The five things to carry out the door

1. **This is acceptance, not authoring.** You bring base, head and a spec; SpecProof returns iron evidence — not vibes, not adjectives.
2. **Read the red before you read the green.** A BLOCKER may not be waved through for having been "considered"; UNVERIFIED is not PASS.
3. **Cache hit rate is an observational metric, never a contract.** `null` from the gateway is shown as "—", and the dash is honest; it is never zero-filled (#1723).
4. **The worktree is yours.** The demo repo (`demo/spring-backend`: `base` = reference implementation, `head-v1` = deliberately removes `@PreAuthorize`). One changed line, that one line IS the case.
5. **30-second self-check first**: `python scripts/demo_doctor.py` — six checks; green before you trust the demo, WARN means look before you accept.

## The three don'ts

1. **Don't trust "we considered it"** when the gate is red. The gate is the gate; consideration is not a verdict.
2. **Don't trust a 96.5% hit rate** — it was the gateway's 4224-token constant (#1723), not your prompt's hits.
3. **Don't read silence as absence.** A crashed checker sets the related criteria to UNVERIFIED — never PASS.

## The five commands you may run verbatim (all real in this repository)

```bash
python scripts/demo_doctor.py                      # self-check (no Docker, no network)
python scripts/build_chronicle.py                  # rebuild apps/web/src/pages/chronicle.json (ledger → JSON)
python -m pytest tests/unit/test_ledger_section_ids_are_unique.py \
  tests/unit/test_ledger_section_numbers_are_unique.py \
  tests/unit/test_ledger_evidence_claims_are_true.py \
  tests/unit/test_ledger_queue_pointers_resolve.py # the ledger four gates
python scripts/provider_smoke.py                   # real LLM smoke (wkapi.pro / gpt-6-sol)
python scripts/sync_portfolio.py                   # rebuild portfolio data (never pushes)
```

## Five words you will meet in the report

| Word | What it means | What you do |
|---|---|---|
| **base_pass_head_fail** | Regression introduced by the change | look, fix, check the capsule |
| **UNVERIFIED** | Evidence gap — not a pass, not a fail | never merge it as green; get more evidence |
| **BLOCKER** | Merge blocked | fix it or produce new evidence; prose won't move it |
| **capsule** | Replayable evidence bundle | your forensic kit when it breaks later |
| **NEEDS_REVIEW** | The evidence cannot settle it | a human reads this line |

## When something breaks

- `python scripts/demo_doctor.py` tells you whether the demo repo's tags/diff/requirements are intact;
- `npm --prefix apps/web run build` (or `npx tsc --noEmit`) tells you whether the web app compiles;
- The full Python unit suite **will not** finish under constrained local memory — trust the specific gate, not "all green";
- Every ledger entry ships the command and the output; words like "maybe" live in prose, never in the ledger.

**Evidence before people.**
