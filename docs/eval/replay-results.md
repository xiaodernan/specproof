# Capsule Replay Batch Results (主计划 §5.9 / 阶段2)

- Generated at: 2026-08-19T21:00:45.839417+00:00
- Tool: `scripts/bench_replay.py`
- Repo: `D:\experim\specproof-clean-clone-gate`
- Capsules dir: `D:\experim\specproof-clean-clone-gate\capsules`
- Temp worktree: `subtree-split`
- Limit: none (full run)

## Replay success rate

| metric | value |
|---|---|
| capsules enumerated | 28 |
| excluded capsules (NOT in the gate denominator) | 3 |
| - excluded_demo_seed | 1 |
| - excluded_stale_artifact | 2 |
| gate denominator (enumerated − excluded) | 25 |
| verified (same_conclusion) | 25 |
| env_mismatch | 0 |
| evidence_inconsistent | 0 |
| replay_failed | 0 |
| replay_pending_probe_infra | 0 |
| static_verified (static evidence re-verified at head) | 13 |
| **success rate (verified / (enumerated − excluded))** | **1.0000** |
| success rate excluding env_mismatch | 1.0000 |
| Go/No-Go gate #4 (replay 成功率 ≥ 95%) | PASS |

## Two-tier replay definition (gate note)

- Tier 1 — runtime reproduction: capsules whose recorded evidence is runtime (blocker_check 2_base_head_execution=true) claim a base-pass/head-fail regression; only a run script verdict of REGRESSION CONFIRMED is same_conclusion.
- Tier 2 — static re-verification: capsules whose recorded evidence kind is static-only (java_source_diff, openapi_endpoint, constitution_check, static_regex_analysis, probe_differential, mutation/annotation checks) are re-verified at the recorded head commit in the temp worktree: the recorded snippet paths must exist with the recorded content at head, and/or the deterministic checker that produced the recorded finding must re-derive it from the head tree. A runtime replay can never reproduce a static finding, so a runtime COMPLIANT verdict is expected and is not a contradiction. Verified static evidence is same_conclusion; unverifiable evidence is replay_failed with the real reason (e.g. the snippet is gone from head).
- `static_verified` counts only tier-2 successes; the raw `same_conclusion` count is unchanged, so both numbers stay auditable.
- Tier 1b — probe-evidence replay: probe_differential capsules record a runtime fault-injection probe finding; the honest replay re-runs the recorded probe test method (repo Maven wrapper, H2, local mode — no Docker) at the recorded base and head refs and compares the probe recorder artifacts (target/specproof-probe.json) against the recorded expectation. Probe scaffolding that genuinely requires Docker/testcontainers is classified replay_pending_probe_infra — a named pending class, never a replay failure.

## Exclusion definitions (gate note, verbatim)

- `excluded_demo_seed` — capsule.json declares demo:true (parsed from the zip; only when it literally contains "demo": true). Reason: demo seed capsule (scripts/seed_demo.py, 非验证发现胶囊) — excluded from the replay gate denominator.
- `excluded_stale_artifact` — recorded manifest_digest matches the sha256 of the pretty-printed manifest (json.dumps(indent=2, sort_keys=True), digest field excluded) while the canonical recompute differs — the zip predates the canonical digest rule. Reason: pre-canonical digest era artifact (built before the canonical manifest rule) — excluded from the replay gate denominator.

The success rate is `verified / (enumerated − excluded)`: excluded capsules are reported with their classification and reason but never counted in the gate denominator, and the raw enumerated count is always printed alongside it.

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

| capsule | severity | evidence | base | head | mode | verdict | outcome | classification | reason |
|---|---|---|---|---|---|---|---|---|---|
| capsule-4ccc31dc-AUTH-01 |  |  |  |  | - | - | excluded | excluded_demo_seed | demo seed capsule (scripts/seed_demo.py, 非验证发现胶囊) — excluded from the replay gate denominator |
| capsule-CONST-EVENT_ONCE-01 | MAJOR | constitution_check | base | case-97-head | static_reverify | - | same_conclusion | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding EVENT_ONCE-01/forbidden_duplicate_publish at head ref case-97-head |
| capsule-COURT-ATOMICITY-01 | MAJOR | base_pass_head_fail | base | case-39-head | runtime | REGRESSION CONFIRMED | same_conclusion | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-AUTH-01 | MAJOR | base_pass_head_fail | base | case-55-head | runtime | REGRESSION CONFIRMED | same_conclusion | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-BOUNDARY-01 | BLOCKER | base_pass_head_fail | base | case-74-head | runtime | REGRESSION CONFIRMED | same_conclusion | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-CACHE-01 | MAJOR | base_pass_head_fail | base | case-65-head | runtime | REGRESSION CONFIRMED | same_conclusion | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-CONCURRENCY-01 | BLOCKER | base_pass_head_fail | base | case-29-head | runtime | REGRESSION CONFIRMED | same_conclusion | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-DIFF-01 | MAJOR | base_pass_head_fail | base | head-v1 | - | - | excluded | excluded_stale_artifact | pre-canonical digest era artifact (built before the canonical manifest rule) — excluded from the replay gate denominator |
| capsule-COURT-EMAIL_FORMAT-01 | BLOCKER | base_pass_head_fail | base | case-77-head | runtime | REGRESSION CONFIRMED | same_conclusion | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-EVENT_ONCE-01 | MAJOR | probe_differential | base | case-98-head | probe_replay | - | same_conclusion | same_conclusion | probe evidence replayed at head (fault-injection probe re-run, H2) — recorded finding description: head violates outcome (base profile met); replayed base {"available": true, "outcome": "success", "payload_count": 0, "payload_timestamp_non_null": false, "publish_count": 0} vs head {"available": true, "outcome": "error", "payload_count": 0, "payload_timestamp_non_null": false, "publish_count": 0} |
| capsule-COURT-IDEMPOTENT-01 | BLOCKER | base_pass_head_fail | base | case-35-head | runtime | REGRESSION CONFIRMED | same_conclusion | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-NPLUSONE-01 | MAJOR | base_pass_head_fail | base | case-86-head | runtime | REGRESSION CONFIRMED | same_conclusion | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-ORDER_AMOUNT-01 | BLOCKER | base_pass_head_fail | base | case-75-head | runtime | REGRESSION CONFIRMED | same_conclusion | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-COURT-ORDER_EVENT-01 | MAJOR | probe_differential | base | case-97-head | probe_replay | - | same_conclusion | same_conclusion | probe evidence replayed at head (fault-injection probe re-run, H2) — recorded finding description: head violates publish_count (base profile met); replayed base {"available": true, "outcome": "error", "payload_count": 1, "payload_timestamp_non_null": true, "publish_count": 1} vs head {"available": true, "outcome": "success", "payload_count": 2, "payload_timestamp_non_null": true, "publish_count": 2} |
| capsule-COURT-UNIQUE-01 | MAJOR | base_pass_head_fail | base | case-20-head | runtime | REGRESSION CONFIRMED | same_conclusion | same_conclusion | recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED |
| capsule-SRC-AUTH-ANNO | MAJOR | java_source_diff | base | case-22-head | static_reverify | - | same_conclusion | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding AUTH-01/annotation_removed at head ref case-22-head |
| capsule-SRC-BACKWARD_COMPATIBLE-SCHE | MAJOR | java_source_diff | base | case-53-head | static_reverify | - | same_conclusion | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding BACKWARD_COMPATIBLE-01/schema_break at head ref case-53-head |
| capsule-SRC-EVENT_ONCE-DUPL | MAJOR | java_source_diff | base | case-97-head | static_reverify | - | same_conclusion | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding EVENT_ONCE-01/duplicate_publish at head ref case-97-head |
| capsule-SRC-MIGRATION-COLU | MAJOR | java_source_diff | base | case-47-head | static_reverify | - | same_conclusion | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding MIGRATION-01/column_type_changed at head ref case-47-head |
| capsule-SRC-MIGRATION-CONS | MAJOR | java_source_diff | base | case-45-head | static_reverify | - | same_conclusion | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding MIGRATION-01/constraint_removed at head ref case-45-head |
| capsule-SRC-MIGRATION-TABL | MAJOR | java_source_diff | base | case-41-head | static_reverify | - | same_conclusion | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding MIGRATION-01/table_removed at head ref case-41-head |
| capsule-SRC-OPENAPI-ENDP | MAJOR | java_source_diff | base | case-55-head | static_reverify | - | same_conclusion | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding OPENAPI-01/endpoint_removed at head ref case-55-head |
| capsule-SRC-TEST_STRENGTH-ASSE | MAJOR | java_source_diff | base | case-91-head | static_reverify | - | same_conclusion | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding TEST_STRENGTH-01/assertions_weakened at head ref case-91-head |
| capsule-SRC-TEST_STRENGTH-TEST | MAJOR | java_source_diff | base | case-91-head | static_reverify | - | same_conclusion | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding TEST_STRENGTH-01/test_removed at head ref case-91-head |
| capsule-SRC-TOKEN_INVALIDATION-GUAR | MAJOR | java_source_diff | base | case-05-head | static_reverify | - | same_conclusion | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding TOKEN_INVALIDATION-01/guard_removed at head ref case-05-head |
| capsule-SRC-TRANSACTION-ANNO | MAJOR | java_source_diff | base | case-37-head | static_reverify | - | same_conclusion | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding TRANSACTION-01/annotation_removed at head ref case-37-head |
| capsule-SRC-UNIQUE-GUAR | MAJOR | java_source_diff | base | case-04-head | static_reverify | - | same_conclusion | same_conclusion | static evidence re-verified at head (runtime COMPLIANT expected for static-only findings) — the deterministic checker re-derived the recorded finding UNIQUE-01/guard_removed at head ref case-04-head |
| capsule-STATIC-MUT-01 | MAJOR | static_regex_analysis | base | head-v1 | - | - | excluded | excluded_stale_artifact | pre-canonical digest era artifact (built before the canonical manifest rule) — excluded from the replay gate denominator |

## Observed root causes (deduplicated reasons)

- ×10 — recorded base_pass_head_fail reproduced — run script verdict REGRESSION CONFIRMED
- ×2 — pre-canonical digest era artifact (built before the canonical manifest rule) — excluded from the replay gate denominator
- ×1 — demo seed capsule (scripts/seed_demo.py, 非验证发现胶囊) — excluded from the replay gate denominator
- ×1 — probe evidence replayed at head (fault-injection probe re-run, H2) — recorded finding description: head violates outcome (base profile met); replayed base {"available": true, "outcome": "success", "payload_count": 0, "payload_timestamp_non_null": false, "publish_count": 0} vs head {"available": true, "outcome": "error", "payload_count": 0, "payload_timestamp_non_null": false, "publish_count": 0}
- ×1 — probe evidence replayed at head (fault-injection probe re-run, H2) — recorded finding description: head violates publish_count (base profile met); replayed base {"available": true, "outcome": "error", "payload_count": 1, "payload_timestamp_non_null": true, "publish_count": 1} vs head {"available": true, "outcome": "success", "payload_count": 2, "payload_timestamp_non_null": true, "publish_count": 2}
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
- probe_differential capsules are replayed as tier 1b: the recorded probe test method is re-run at the recorded base and head refs through the repo Maven wrapper (H2, local mode — the probe scaffolding mocks the broker/redis beans, no Docker) and the probe recorder artifacts are compared against the recorded expectation — a runtime probe finding can only be replayed by re-running the probe, never by the static checkers.
- Temp worktree mechanism `subtree-split`: the repo is cloned to a temp dir (the real repo is never mutated) and each needed ref is rebuilt with the demo project at the repo root, because the generated run scripts expect mvnw at the git root while this repo keeps the project under demo/spring-backend.
- The existing replay CLI appends one replay_report record per capsule to the object-metadata store — documented CLI behavior, outside the repo.
- env_mismatch is only reported for environment failures, always with the exact reason; verdicts are never fabricated.
- Two explicit exclusion classifications keep the gate denominator auditable: excluded_demo_seed (capsule.json declares demo:true) and excluded_stale_artifact (the recorded digest matches the pre-canonical pretty-printed manifest digest while the canonical recompute differs). Excluded capsules are reported with their classification and reason and are never counted in the gate denominator.
- The gate success rate is verified / (enumerated − excluded): both denominators (the raw enumerated count and the gate denominator) are printed in the JSON totals and this document — raw counts are never hidden.
