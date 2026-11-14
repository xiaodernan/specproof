# SpecProof Pocket Card · 30-Second Onboarding

> Print it (A4, single side). Keep it next to the keyboard. The full manual is
> `docs/operations/EN/USER_GUIDE_EN.md`; this page is only the
> "what must be in your head before you open the door".
> 中文版：[POCKET_CARD.md](./POCKET_CARD.md)

---

## The five things to carry out the door

1. **This is acceptance, not authoring.** You bring base, head and a spec; SpecProof returns iron evidence — not vibes, not adjectives.
2. **Read the red before you read the green.** A BLOCKER may not be waved through for having been "considered"; UNVERIFIED is not PASS.
3. **Cache hit rate is an observational metric, never a contract.** `null` from the gateway is shown as "—", and the dash is honest; it is never zero-filled.
4. **The worktree is yours.** The demo repo (`demo/spring-backend`: `base` = reference implementation, `head-v1` = deliberately removes `@PreAuthorize`). One changed line, that one line IS the case.
5. **30-second self-check first**: `python scripts/demo_doctor.py` — six checks; green before you trust the demo, WARN means look before you accept.

## The three don'ts

1. **Don't trust "we considered it"** when the gate is red. The gate is the gate; consideration is not a verdict.
2. **Don't trust a 96.5% hit rate** — it was the gateway's 4224-token constant (#1723), not your prompt's hits.
3. **Don't read silence as absence.** A crashed checker sets the related criteria to UNVERIFIED — never PASS.

## The four commands you may run verbatim

```bash
python scripts/demo_doctor.py                      # self-check (no Docker, no network)
curl -s http://127.0.0.1:8081/health               # Control Plane — webhook core (RUNBOOK §1)
curl -s http://127.0.0.1:8090/actuator/health     # Edge gateway, actuator profile (RUNBOOK §3)
specproof verify --repo demo/spring-backend \
  --base base --head head-v1 --spec demo/requirement.txt \
  --depth FAST --no-llm                            # deterministic check, no LLM
python scripts/sync_portfolio.py                   # rebuild portfolio data (rebuild only, never pushes)
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

- `/health` maps the dependencies (mysql / redis / rabbitmq / minio / smtp);
- Run the same spec twice — the findings fingerprint must match; if they don't, the toolchain is lying and you go look;
- Full triage: `docs/operations/RUNBOOK.md`;
- Every ledger entry ships the command and the output; words like "maybe" live in prose, never in the ledger.

**Evidence before people.**
