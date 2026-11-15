# The Open Debts · 欠条墙

> Every open debt in this repo, one page — what is owed, who owes it.
> **An IOU here never gets dyed green.** States are struck by `audit_unsigned.py` and `verify_links.py`;
> human-signatures wait for exactly one human and never for a proxy.
>
> Rules: the wall lists only honest things — never "things I think we'd have".
> New IOU = append; a paid IOU = struck through and left visible, never quietly deleted.

## 1 · Signature-class (a human owed)

| # | Debt | Who pays | How it lands | Open for |
|---|---|---|---|---|
| D1 | **OBSERVABILITY.md sign-off** — the only entry to real fleet telemetry | a human signature | one signature ⇒ `audit_unsigned.py` flips jade, `#/last-call` lamp follows, D1 struck through | all repo lifetime |
| D2 | **PORTFOLIO_TOKEN** (Settings → Secrets → xiaodernan/xiaodernan.github.io, Contents: read+write) | a human (this repo's owner) | once set, portfolio auto-sync runs every 72h — never red, never fake-pushes | since portfolio-sync landed |
| D3 | **`#/gazette`'s "TOMORROW'S WEATHER" copy decision** (evidence Δ barometer copy, not cloud/wind/divination — p99) | a human (product decision) | one line of copy rewrite; this entry waits on product call | since written |

## 2 · Machine-closable (no human needed)

| # | Debt | How the machine pays | Trace |
|---|---|---|---|
| M1 | **weekly-stress.yml's first automated strike** | next Monday 03:00 UTC cron; artifact archived; never red-flags | `.github/workflows/weekly-stress.yml` |
| M2 | **weekly evidence Δ** (p99 vs previous) | `build_evidence.py`, each rebuild; `#/fabric` evidence card renders it | `scripts/build_evidence.py` |
| M3 | **evidence drift sentinel** — byte-level cross-file check | `audit_evidence.py`, every rebuild; **this round: 7/7 CONSISTENT** | `scripts/audit_evidence.py` |
| M4 | **link health across docs** — 141 docs scanned | `verify_links.py` every re-run; today: **0 dead / 1 annotated-planned** | `scripts/verify_links.py` · `docs/evidence/audit-links.json` |

## 3 · Needs machine + human (both)

| # | Debt | Machine side | Human side |
|---|---|---|---|
| B1 | **app stack end-to-end `docker-compose` truly up** (production.yml + observability) | machine ready: `Dockerfile.api` / `Dockerfile.worker` (8/7 infra healthy on this host); the socket answers 404 from another project today | the decision: which host really runs it |
| B2 | **evidence auto-backfill into git** (extract Δ from weekly artifact) | pipeline exists — missing last mile script | the product decision: is weekly auto-commit-to-PR ok |

## 4 · Never-owed (forever public)

- **"password 123 for everybody"** — never exists, never will, in any wording;
- **court never cached** — never in any release, tag, fork, or excuse;
- **fake-green CI** (faked deploy, staged prod, tampered telemetry) — never;
- **demo data impersonating production** — never.

---

*D1–D3 wait on the human; M1–M4 wait on the machine; B1–B2 wait on both. D1 and D2 are the only two standing human actions in this whole book.*
