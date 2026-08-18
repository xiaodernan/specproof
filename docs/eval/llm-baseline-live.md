# SpecProof vs 只看 Diff 基线 (Go/No-Go #14)

- 基线模式: LLM (diff + requirement)
- 案例数: 12

| Case | Ground truth | Baseline verdict | Baseline contracts |
|---|---|---|---|
| case-01-auth-bypass | should-detect | MISS | UserController.changeEmail |
| case-02-transactional-removal | should-detect | MISS | com.specproof.demo.service.UserService.changeEmail |
| case-03-clean-pr | negative | PASS | — |
| case-04-duplicate-email | should-detect | MISS | UserService |
| case-05-token-invalidation | should-detect | MISS | Case 05: Token Invalidation Broken |
| case-06-schema-break | should-detect | MISS | com.specproof.demo.dto.UserResponse |
| case-07-duplicate-event | should-detect | MISS | UserService |
| case-08-transaction-split | should-detect | MISS | UserService.changeEmail |
| case-09-multi-security | should-detect | MISS | — |
| case-10-comment-only | negative | PASS | — |
| case-17-logic-inversion | should-detect | MISS | UserService.updateEmail |
| case-18-wrong-routing-key | should-detect | MISS | change-email |

## 对比 (同一 case 集合)

| Metric | SpecProof | Baseline | Delta |
|---|---|---|---|
| Recall | 100.0% | 0.0% | +100.0pp |
| Precision | 100.0% | 100.0% | +0.0pp |
| F1 | 100.0% | 0.0% | +100.0pp |

Go/No-Go #14 (+25pp recall): **PASS** (+100.0pp)