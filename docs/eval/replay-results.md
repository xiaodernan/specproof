# Capsule Replay Batch Results (主计划 §5.9 / 阶段2)

- Generated at: 2026-08-19T18:49:05.547927+00:00
- Tool: `scripts/bench_replay.py`
- Repo: `D:\experim\specproof-clean-clone-gate`
- Capsules dir: `D:\experim\specproof-clean-clone-gate\capsules`
- Temp worktree: `subtree-split`
- Limit: none (full run)

## Replay success rate

| metric | value |
|---|---|
| capsules enumerated | 28 |
| same_conclusion | 12 |
| env_mismatch | 0 |
| evidence_inconsistent | 3 |
| replay_failed | 13 |
| **success rate (same_conclusion / enumerated)** | **0.4286** |
| success rate excluding env_mismatch | 0.4286 |
| Go/No-Go gate #4 (replay 成功率 ≥ 95%) | FAIL |

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

| capsule | severity | evidence | base | head | verdict | outcome | reason |
|---|---|---|---|---|---|---|---|
| capsule-4ccc31dc-AUTH-01 |  |  |  |  | - | evidence_inconsistent | manifest.json missing — the existing replay path rejects the capsule as corrupt; recorded evidence cannot be established |
| capsule-CONST-EVENT_ONCE-01 | MAJOR | constitution_check | base | case-97-head | COMPLIANT | replay_failed | static-only recorded evidence; runtime verdict COMPLIANT does not reproduce the finding |
| capsule-COURT-ATOMICITY-01 | MAJOR | base_pass_head_fail | base | case-39-head | REGRESSION CONFIRMED | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-AUTH-01 | MAJOR | base_pass_head_fail | base | case-55-head | REGRESSION CONFIRMED | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-BOUNDARY-01 | BLOCKER | base_pass_head_fail | base | case-74-head | REGRESSION CONFIRMED | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-CACHE-01 | MAJOR | base_pass_head_fail | base | case-65-head | REGRESSION CONFIRMED | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-CONCURRENCY-01 | BLOCKER | base_pass_head_fail | base | case-29-head | REGRESSION CONFIRMED | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-DIFF-01 | MAJOR | base_pass_head_fail | base | head-v1 | - | evidence_inconsistent | manifest_digest mismatch: recorded 'sha256:3301f'..., recomputed bd7add20c331... — the manifest was modified after recording |
| capsule-COURT-EMAIL_FORMAT-01 | BLOCKER | base_pass_head_fail | base | case-77-head | REGRESSION CONFIRMED | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-EVENT_ONCE-01 | MAJOR | probe_differential | base | case-98-head | COMPLIANT | replay_failed | static-only recorded evidence; runtime verdict COMPLIANT does not reproduce the finding |
| capsule-COURT-IDEMPOTENT-01 | BLOCKER | base_pass_head_fail | base | case-35-head | REGRESSION CONFIRMED | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-NPLUSONE-01 | MAJOR | base_pass_head_fail | base | case-86-head | REGRESSION CONFIRMED | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-ORDER_AMOUNT-01 | BLOCKER | base_pass_head_fail | base | case-75-head | REGRESSION CONFIRMED | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-ORDER_EVENT-01 | MAJOR | probe_differential | base | case-97-head | COMPLIANT | replay_failed | static-only recorded evidence; runtime verdict COMPLIANT does not reproduce the finding |
| capsule-COURT-UNIQUE-01 | MAJOR | base_pass_head_fail | base | case-20-head | REGRESSION CONFIRMED | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-SRC-AUTH-ANNO | MAJOR | java_source_diff | base | case-22-head | REGRESSION CONFIRMED | same_conclusion | static-only recorded evidence; runtime replay additionally confirmed the regression (verdict REGRESSION CONFIRMED) — same conclusion, stronger evidence |
| capsule-SRC-BACKWARD_COMPATIBLE-SCHE | MAJOR | java_source_diff | base | case-53-head | COMPLIANT | replay_failed | static-only recorded evidence; runtime verdict COMPLIANT does not reproduce the finding |
| capsule-SRC-EVENT_ONCE-DUPL | MAJOR | java_source_diff | base | case-97-head | COMPLIANT | replay_failed | static-only recorded evidence; runtime verdict COMPLIANT does not reproduce the finding |
| capsule-SRC-MIGRATION-COLU | MAJOR | java_source_diff | base | case-47-head | COMPLIANT | replay_failed | static-only recorded evidence; runtime verdict COMPLIANT does not reproduce the finding |
| capsule-SRC-MIGRATION-CONS | MAJOR | java_source_diff | base | case-45-head | COMPLIANT | replay_failed | static-only recorded evidence; runtime verdict COMPLIANT does not reproduce the finding |
| capsule-SRC-MIGRATION-TABL | MAJOR | java_source_diff | base | case-41-head | COMPLIANT | replay_failed | static-only recorded evidence; runtime verdict COMPLIANT does not reproduce the finding |
| capsule-SRC-OPENAPI-ENDP | MAJOR | java_source_diff | base | case-55-head | REGRESSION CONFIRMED | same_conclusion | static-only recorded evidence; runtime replay additionally confirmed the regression (verdict REGRESSION CONFIRMED) — same conclusion, stronger evidence |
| capsule-SRC-TEST_STRENGTH-ASSE | MAJOR | java_source_diff | base | case-91-head | COMPLIANT | replay_failed | static-only recorded evidence; runtime verdict COMPLIANT does not reproduce the finding |
| capsule-SRC-TEST_STRENGTH-TEST | MAJOR | java_source_diff | base | case-91-head | COMPLIANT | replay_failed | static-only recorded evidence; runtime verdict COMPLIANT does not reproduce the finding |
| capsule-SRC-TOKEN_INVALIDATION-GUAR | MAJOR | java_source_diff | base | case-05-head | COMPLIANT | replay_failed | static-only recorded evidence; runtime verdict COMPLIANT does not reproduce the finding |
| capsule-SRC-TRANSACTION-ANNO | MAJOR | java_source_diff | base | case-37-head | COMPLIANT | replay_failed | static-only recorded evidence; runtime verdict COMPLIANT does not reproduce the finding |
| capsule-SRC-UNIQUE-GUAR | MAJOR | java_source_diff | base | case-04-head | COMPLIANT | replay_failed | static-only recorded evidence; runtime verdict COMPLIANT does not reproduce the finding |
| capsule-STATIC-MUT-01 | MAJOR | static_regex_analysis | base | head-v1 | - | evidence_inconsistent | manifest_digest mismatch: recorded 'sha256:8857f'..., recomputed ca8c1611da4c... — the manifest was modified after recording |

## Observed root causes (deduplicated reasons)

- ×13 — static-only recorded evidence; runtime verdict COMPLIANT does not reproduce the finding
- ×10 — recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED
- ×2 — static-only recorded evidence; runtime replay additionally confirmed the regression (verdict REGRESSION CONFIRMED) — same conclusion, stronger evidence
- ×1 — manifest.json missing — the existing replay path rejects the capsule as corrupt; recorded evidence cannot be established
- ×1 — manifest_digest mismatch: recorded 'sha256:3301f'..., recomputed bd7add20c331... — the manifest was modified after recording
- ×1 — manifest_digest mismatch: recorded 'sha256:8857f'..., recomputed ca8c1611da4c... — the manifest was modified after recording

## Method notes

- Classification is anchored on each capsule's own recorded evidence: blocker_check condition 2_base_head_execution=true commits the capsule to a differential base-pass/head-fail regression, so only a REGRESSION CONFIRMED verdict is same_conclusion; static-only capsules carry no runtime claim and a runtime confirmation is recorded as the same conclusion (strengthened).
- Capsules are replayed through the existing path (python -m cli.specproof.main replay), then their own generated run script is executed unmodified against a temp worktree — observed replay defects are reported in the reasons, never patched around.
- Temp worktree mechanism `subtree-split`: the repo is cloned to a temp dir (the real repo is never mutated) and each needed ref is rebuilt with the demo project at the repo root, because the generated run scripts expect mvnw at the git root while this repo keeps the project under demo/spring-backend.
- The existing replay CLI appends one replay_report record per capsule to the object-metadata store — documented CLI behavior, outside the repo.
- env_mismatch is only reported for environment failures, always with the exact reason; verdicts are never fabricated.
