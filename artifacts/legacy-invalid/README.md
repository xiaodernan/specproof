# Legacy / Invalid Capsules — DO NOT USE FOR P0.5 ACCEPTANCE

These artifacts were generated during P0.5 development and are preserved for
evidence-strategy history. They are NOT valid for P0.5 graduation.

## Why These Are Invalid

| Artifact | Reason for Invalidation |
|----------|------------------------|
| `capsule-STATIC-AUTH-01.zip/dir` | Static regex only — MAJOR capped, no differential execution evidence |
| `capsule-STATIC-MUT-01.zip/dir` | Static regex only — MAJOR capped, no DB state verification |
| `capsule-STATIC-MUT-02.zip/dir` | Static regex only — MAJOR capped, no DB state verification |
| `capsule-COURT-DIFF-HTTP.zip/dir` | Used LLM template fallback, not real DeepSeek generation |
| `capsule-P0_5-CC7E5BBE.zip` | v1 — LLM test used `andExpect()` short-circuit, DB check never executed on Head |
| `capsule-P0_5-32EAD58D.zip` | v2 — LLM test used `andExpect()` short-circuit, DB check never executed on Head |
| `capsule-P0_5-5ECF7092.zip` | v2 — LLM test used `andExpect()` short-circuit, DB check never executed on Head |
| `p0_5_acceptance_report_P0_5-*.json` | Corresponding reports for invalid capsules above |

## Evidence Strategy Evolution

1. **STATIC-AUTH/MUT** (Task 5-7 era): Regex hit on `@PreAuthorize` removal → BLOCKER.
   P0.5 evidence policy later capped static regex at MAJOR. These capsules violate
   the policy that BLOCKER requires 10 conditions including real differential execution.

2. **COURT-DIFF-HTTP** (Task 12 era): Added differential HTTP check but used
   `deterministic_template` test, not `llm_generated`. The `human_fixture`
   `AuthDbStateRegressionTest` was also never attributed as LLM-generated.

3. **P0_5-CC7E5BBE** (v1): Real DeepSeek generation but compilation failed
   (wrong imports, wrong constructors). No retry loop with fix feedback.

4. **P0_5-32EAD58D** (v2): DeepSeek generated compilable code on first attempt.
   Base PASS (401 + DB unchanged), Head FAIL (200 + DB changed). Regression
   confirmed. BUT: `.andExpect(status().isUnauthorized())` causes short-circuit
   — on Head, the 401 assertion throws before DB check executes. Surefire shows
   1 failure, not 2. DB violation evidence is NOT in test output.

5. **P0_5-5ECF7092** (v2 repeat): Same as 32EAD58D. Repeated with slightly
   different LLM output. Same short-circuit defect.

6. **P0_5-511A3276** (v3 — VALID): Prompt explicitly requires `MvcResult.andReturn()` +
   `assertAll()`. Both checks execute independently. Head Surefire shows
   **2 failures** (401 + DB STATE VIOLATION). 10/10 BLOCKER conditions met.
   → **This is the only valid P0.5 artifact.** Archived to `artifacts/p0.5/511A3276/`.

## Policy

- These artifacts MUST NOT be used as acceptance evidence for any phase.
- They are kept to document why the evidence strategy evolved from
  "regex hit → BLOCKER" to "10-condition proof-backed BLOCKER."
- If reproducing P0.5, use only `artifacts/p0.5/511A3276/`.
