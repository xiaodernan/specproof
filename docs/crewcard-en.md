# SpecProof · FIELD CARD

> xiaodernan/specproof · generated at 2026-11-15 18:21 UTC
> This card prints only git-tracked facts. It is not a signature, not a seal, not a promise.

## The wall

| | |
|---|---|
| commits | 2,507 |
| ledger sections | 1,666 |
| volumes (zh/en) | 83 / 83 |
| source lines | 500,704 |
| Python test files | 610 |
| web test files | 69 |
| ledger bytes (KB) | 3788.0 |
| latest chronicle | #1865 |

## Stress evidence

| | |
|---|---|
| evidence | `2026-11-16-static-warm-3.json` |
| worst p99 | 1030.1 ms |
| verdict | OK |
| Δ vs previous | -507.2ms |

## Unsigned (live audit)

| | |
|---|---|
| real fleet telemetry · sign-off | awaiting-signature |
| the Monday knock · weekly-stress.yml | merged |
| port 8000 · who answers right now | port-free |

```
git log --oneline -1 && python scripts/build_repo_stats.py && python scripts/audit_unsigned.py
```

Every digit re-opens: chronicle.json · repoStats.json · evidence.json · unsigned.json · engine.json (all git-tracked).
LLM ledger: openai_compat · wkapi.pro · stream+include_usage; cached_tokens 75,638 (42.1% prefix-hit, not an SLA)

> This card carries no keys, no secrets, no signatures — this repository never writes an `sk-…` into any git-tracked file.

