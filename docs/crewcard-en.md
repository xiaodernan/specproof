# SpecProof · FIELD CARD

> xiaodernan/specproof · generated at 2026-11-16 14:25 UTC
> This card prints only git-tracked facts. It is not a signature, not a seal, not a promise.

## The wall

| | |
|---|---|
| commits | 2,588 |
| ledger sections | 1,725 |
| volumes (zh/en) | 138 / 138 |
| source lines | 512,522 |
| Python test files | 618 |
| web test files | 78 |
| ledger bytes (KB) | 3900.3 |
| latest chronicle | #1926 |

## Stress evidence

| | |
|---|---|
| evidence | `2026-11-16-static-warm-12.json` |
| worst p99 | 10049.2 ms |
| verdict | BUDGET-BLOWN |
| Δ vs previous | +7795.4ms |

## Unsigned (live audit)

| | |
|---|---|
| real fleet telemetry · sign-off | signature-block-found |
| the Monday knock · weekly-stress.yml | merged |
| port 8000 · who answers right now | port-free |

```
git log --oneline -1 && python scripts/build_repo_stats.py && python scripts/audit_unsigned.py
```

Every digit re-opens: chronicle.json · repoStats.json · evidence.json · unsigned.json · engine.json (all git-tracked).
LLM ledger: openai_compat · wkapi.pro · stream+include_usage; cached_tokens 75,638 (42.1% prefix-hit, not an SLA)

> This card carries no keys, no secrets, no signatures — this repository never writes an `sk-…` into any git-tracked file.

