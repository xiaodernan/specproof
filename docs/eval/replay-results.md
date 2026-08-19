# Capsule Replay Batch Results (主计划 §5.9 / 阶段2)

- Generated at: 2026-08-19T19:41:42.216604+00:00
- Tool: `scripts/bench_replay.py`
- Repo: `D:\experim\specproof-clean-clone-gate`
- Capsules dir: `D:\experim\specproof-clean-clone-gate\capsules`
- Temp worktree: `subtree-split`
- Limit: none (full run)

## Replay success rate

| metric | value |
|---|---|
| capsules enumerated | 28 |
| same_conclusion | 23 |
| env_mismatch | 0 |
| evidence_inconsistent | 3 |
| replay_failed | 2 |
| static_verified (static evidence re-verified at head) | 13 |
| **success rate (same_conclusion / enumerated)** | **0.8214** |
| success rate excluding env_mismatch | 0.8214 |
| Go/No-Go gate #4 (replay 成功率 ≥ 95%) | FAIL |

## Two-tier replay definition (gate note)

- Tier 1 — runtime reproduction: capsules whose recorded evidence is runtime (blocker_check 2_base_head_execution=true) claim a base-pass/head-fail regression; only a run script verdict of REGRESSION CONFIRMED is same_conclusion.
- Tier 2 — static re-verification: capsules whose recorded evidence kind is static-only (java_source_diff, openapi_endpoint, constitution_check, static_regex_analysis, probe_differential, mutation/annotation checks) are re-verified at the recorded head commit in the temp worktree: the recorded snippet paths must exist with the recorded content at head, and/or the deterministic checker that produced the recorded finding must re-derive it from the head tree. A runtime replay can never reproduce a static finding, so a runtime COMPLIANT verdict is expected and is not a contradiction. Verified static evidence is same_conclusion; unverifiable evidence is replay_failed with the real reason (e.g. the snippet is gone from head).
- `static_verified` counts only tier-2 successes; the raw `same_conclusion` count is unchanged, so both numbers stay auditable.

## Environment

| tool | status |
|---|---|
| python | `C:\Users\HUAWEI\AppData\Local\Programs\Python\Python312\python.exe` |
| git | `C:\Program Files\Git\cmd\git.EXE` |
| pwsh | `C:\Users\HUAWEI\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.EXE` |
| bash | `C:\Windows\system32\bash.EXE` |
| java | `C:\Program Files\Amazon Corretto\jdk21.0.11_10\bin\java.EXE` (openjdk version "21.0.11" 2026-04-21 LTS) |
| Maven distribution cache | `C:\Users\HUAWEI\.m2\wrapper\dists` |

## Object-metadata store

| metric | value |
|---|---|
| capsule records total | 191 |
| records under this repo's capsules/ | 179 |
| records pointing at other repos | 12 |
| records whose payload no longer exists | 0 |
| records joined to a zip by payload digest | 25 |

## Per-capsule results

| capsule | severity | evidence | base | head | mode | verdict | outcome | reason |
|---|---|---|---|---|---|---|---|---|
| capsule-4ccc31dc-AUTH-01 |  |  |  |  | - | - | evidence_inconsistent | manifest.json missing — the existing replay path rejects the capsule as corrupt; recorded evidence cannot be established |
| capsule-CONST-EVENT_ONCE-01 | MAJOR | constitution_check | base | case-97-head | static_reverify | - | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding EVENT_ONCE-01/forbidden_duplicate_publish at head ref case-97-head |
| capsule-COURT-ATOMICITY-01 | MAJOR | base_pass_head_fail | base | case-39-head | runtime | REGRESSION CONFIRMED | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-AUTH-01 | MAJOR | base_pass_head_fail | base | case-55-head | runtime | REGRESSION CONFIRMED | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-BOUNDARY-01 | BLOCKER | base_pass_head_fail | base | case-74-head | runtime | REGRESSION CONFIRMED | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-CACHE-01 | MAJOR | base_pass_head_fail | base | case-65-head | runtime | REGRESSION CONFIRMED | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-CONCURRENCY-01 | BLOCKER | base_pass_head_fail | base | case-29-head | runtime | REGRESSION CONFIRMED | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-DIFF-01 | MAJOR | base_pass_head_fail | base | head-v1 | - | - | evidence_inconsistent | manifest_digest mismatch: recorded 'sha256:3301f'..., recomputed bd7add20c331... — the manifest was modified after recording |
| capsule-COURT-EMAIL_FORMAT-01 | BLOCKER | base_pass_head_fail | base | case-77-head | runtime | REGRESSION CONFIRMED | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-EVENT_ONCE-01 | MAJOR | probe_differential | base | case-98-head | static_reverify | - | replay_failed | recorded static evidence for EVENT_ONCE-01 no longer re-verifies at head ref case-98-head: the deterministic checkers produce no violation for the contract at head |
| capsule-COURT-IDEMPOTENT-01 | BLOCKER | base_pass_head_fail | base | case-35-head | runtime | REGRESSION CONFIRMED | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-NPLUSONE-01 | MAJOR | base_pass_head_fail | base | case-86-head | runtime | REGRESSION CONFIRMED | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-ORDER_AMOUNT-01 | BLOCKER | base_pass_head_fail | base | case-75-head | runtime | REGRESSION CONFIRMED | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-ORDER_EVENT-01 | MAJOR | probe_differential | base | case-97-head | static_reverify | - | replay_failed | recorded static evidence for ORDER_EVENT-01 no longer re-verifies at head ref case-97-head: the deterministic checkers produce no violation for the contract at head |
| capsule-COURT-UNIQUE-01 | MAJOR | base_pass_head_fail | base | case-20-head | runtime | REGRESSION CONFIRMED | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-SRC-AUTH-ANNO | MAJOR | java_source_diff | base | case-22-head | static_reverify | - | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding AUTH-01/annotation_removed at head ref case-22-head |
| capsule-SRC-BACKWARD_COMPATIBLE-SCHE | MAJOR | java_source_diff | base | case-53-head | static_reverify | - | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding BACKWARD_COMPATIBLE-01/schema_break at head ref case-53-head |
| capsule-SRC-EVENT_ONCE-DUPL | MAJOR | java_source_diff | base | case-97-head | static_reverify | - | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding EVENT_ONCE-01/duplicate_publish at head ref case-97-head |
| capsule-SRC-MIGRATION-COLU | MAJOR | java_source_diff | base | case-47-head | static_reverify | - | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding MIGRATION-01/column_type_changed at head ref case-47-head |
| capsule-SRC-MIGRATION-CONS | MAJOR | java_source_diff | base | case-45-head | static_reverify | - | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding MIGRATION-01/constraint_removed at head ref case-45-head |
| capsule-SRC-MIGRATION-TABL | MAJOR | java_source_diff | base | case-41-head | static_reverify | - | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding MIGRATION-01/table_removed at head ref case-41-head |
| capsule-SRC-OPENAPI-ENDP | MAJOR | java_source_diff | base | case-55-head | static_reverify | - | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding OPENAPI-01/endpoint_removed at head ref case-55-head |
| capsule-SRC-TEST_STRENGTH-ASSE | MAJOR | java_source_diff | base | case-91-head | static_reverify | - | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding TEST_STRENGTH-01/assertions_weakened at head ref case-91-head |
| capsule-SRC-TEST_STRENGTH-TEST | MAJOR | java_source_diff | base | case-91-head | static_reverify | - | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding TEST_STRENGTH-01/test_removed at head ref case-91-head |
| capsule-SRC-TOKEN_INVALIDATION-GUAR | MAJOR | java_source_diff | base | case-05-head | static_reverify | - | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding TOKEN_INVALIDATION-01/guard_removed at head ref case-05-head |
| capsule-SRC-TRANSACTION-ANNO | MAJOR | java_source_diff | base | case-37-head | static_reverify | - | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding TRANSACTION-01/annotation_removed at head ref case-37-head |
| capsule-SRC-UNIQUE-GUAR | MAJOR | java_source_diff | base | case-04-head | static_reverify | - | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding UNIQUE-01/guard_removed at head ref case-04-head |
| capsule-STATIC-MUT-01 | MAJOR | static_regex_analysis | base | head-v1 | - | - | evidence_inconsistent | manifest_digest mismatch: recorded 'sha256:8857f'..., recomputed ca8c1611da4c... — the manifest was modified after recording |

## Observed root causes (deduplicated reasons)

- ×10 — recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED
- ×1 — manifest.json missing — the existing replay path rejects the capsule as corrupt; recorded evidence cannot be established
- ×1 — manifest_digest mismatch: recorded 'sha256:3301f'..., recomputed bd7add20c331... — the manifest was modified after recording
- ×1 — manifest_digest mismatch: recorded 'sha256:8857f'..., recomputed ca8c1611da4c... — the manifest was modified after recording
- ×1 — recorded static evidence for EVENT_ONCE-01 no longer re-verifies at head ref case-98-head: the deterministic checkers produce no violation for the contract at head
- ×1 — recorded static evidence for ORDER_EVENT-01 no longer re-verifies at head ref case-97-head: the deterministic checkers produce no violation for the contract at head
- ×1 — static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding AUTH-01/annotation_removed at head ref case-22-head
- ×1 — static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding BACKWARD_COMPATIBLE-01/schema_break at head ref case-53-head
- ×1 — static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding EVENT_ONCE-01/duplicate_publish at head ref case-97-head
- ×1 — static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding EVENT_ONCE-01/forbidden_duplicate_publish at head ref case-97-head
- ×1 — static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding MIGRATION-01/column_type_changed at head ref case-47-head
- ×1 — static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding MIGRATION-01/constraint_removed at head ref case-45-head
- ×1 — static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding MIGRATION-01/table_removed at head ref case-41-head
- ×1 — static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding OPENAPI-01/endpoint_removed at head ref case-55-head
- ×1 — static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding TEST_STRENGTH-01/assertions_weakened at head ref case-91-head
- ×1 — static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding TEST_STRENGTH-01/test_removed at head ref case-91-head
- ×1 — static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding TOKEN_INVALIDATION-01/guard_removed at head ref case-05-head
- ×1 — static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding TRANSACTION-01/annotation_removed at head ref case-37-head
- ×1 — static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding UNIQUE-01/guard_removed at head ref case-04-head

## Method notes

- Classification is anchored on each capsule's own recorded evidence, in two tiers: runtime-evidence capsules (2_base_head_execution=true) require a REGRESSION CONFIRMED run script verdict; static-only capsules are re-verified at the recorded head commit (recorded snippet paths + content, and/or deterministic checker re-derivation) — never by a runtime verdict.
- Capsules are replayed through the existing path (python -m cli.specproof.main replay); runtime-evidence capsules then execute their own generated run script unmodified against a temp worktree — observed replay defects are reported in the reasons, never patched around.
- Temp worktree mechanism `subtree-split`: the repo is cloned to a temp dir (the real repo is never mutated) and each needed ref is rebuilt with the demo project at the repo root, because the generated run scripts expect mvnw at the git root while this repo keeps the project under demo/spring-backend.
- The existing replay CLI appends one replay_report record per capsule to the object-metadata store — documented CLI behavior, outside the repo.
- env_mismatch is only reported for environment failures, always with the exact reason; verdicts are never fabricated.
