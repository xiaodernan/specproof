# SpecProof vs 只看 Diff 基线 (Go/No-Go #14)

- 基线模式: deterministic diff-reader
- 案例数: 12

| Case | Ground truth | Baseline verdict | Baseline contracts |
|---|---|---|---|
| case-01-auth-bypass | should-detect | PASS | AUTH-01 |
| case-02-transactional-removal | should-detect | PASS | TRANSACTION-01 |
| case-03-clean-pr | negative | PASS | — |
| case-04-duplicate-email | should-detect | PASS | UNIQUE-01 |
| case-05-token-invalidation | should-detect | PASS | TOKEN_INVALIDATION-01 |
| case-06-schema-break | should-detect | MISS | — |
| case-07-duplicate-event | should-detect | PASS | EVENT_ONCE-01 |
| case-08-transaction-split | should-detect | PASS | TRANSACTION-01 |
| case-09-multi-security | should-detect | PARTIAL | AUTH-01, TRANSACTION-01 |
| case-10-comment-only | negative | PASS | — |
| case-11-refactor-rename | negative | PASS | — |
| case-12-add-javadoc | negative | PASS | — |

## 对比 (同一 case 集合)

| Metric | SpecProof | Baseline | Delta |
|---|---|---|---|
| Recall | 100.0% | 87.5% | +12.5pp |
| Precision | 100.0% | 100.0% | +0.0pp |

Go/No-Go #14 (+25pp recall): **FAIL** (+12.5pp)