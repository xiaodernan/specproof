# SpecProof · FIELD CARD

> xiaodernan/specproof · generated at 2026-11-16 14:14 UTC
> This card prints only git-tracked facts. It is not a signature, not a seal, not a promise.

## The wall

| | |
|---|---|
| commits | 2,587 |
| ledger sections | 1,724 |
| volumes (zh/en) | 137 / 137 |
| source lines | 512,163 |
| Python test files | 618 |
| web test files | 78 |
| ledger bytes (KB) | 3898.3 |
| latest chronicle | #1925 |

## Stress evidence

| | |
|---|---|
| evidence | `2026-11-16-static-warm-11.json` |
| worst p99 | 2253.8 ms |
| verdict | BUDGET-BLOWN |
| Δ vs previous | +28.1ms |

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

