# craft × aizzz lane — what four more strikes taught the chain (2026-11-16T16:02Z → 2026-11-17T00:52Z)

Recording honestly, in order, so the next reader does not have to retrace the night:

## Strike #1 — 2026-11-16T16:02Z (e1etpxue, pre-seed)
plan llm · LOOP **DONE** · model wrote `x * 2` · 2 calls (prompt 10,553 / completion 1,435 / reasoning 1,010 / cached 4,224) ·
accept gate `run_test`: docker, `python -m pytest -q` → `No module named pytest` → BLOCKED → rollback to base.

## Strike #2 — 16:11Z (z_l59fag, after the wheelhouse seed)
plan llm · LOOP **DONE** · `x * 2` · 2 calls (prompt 10,553 / completion 2,165 / reasoning 1,697 / cached 4,224) ·
accept gate UNCHANGED: `mode=docker`, bare `python -m pytest -q` → `No module named pytest`.
**Seeding the wheelhouse was necessary but not sufficient** — the slim image still couldn't see it, because the
gate asked for a bare pytest instead of the three-phase triplet this profile exists for.

## Strike #3 — 16:20Z (y9eangbx, after the composite rewrite landed)
plan llm · LOOP **STUCK** (the model did not converge this round) · 5 calls (prompt 27,654 / completion 4,090 / reasoning 3,481 / cached 12,672 over four calls) —
a nondeterministic model is nondeterministic; recorded as-is; the gate still said `No module named pytest` because that run happened before the composite check reached `effective_mode == "auto"` (the hook only matched `mode == "docker"`; docker daemon was up → auto resolved → docker ran the bare command).

## Strike #4 — 16:23Z (6o_xra9f, composite hook fixed to effective_mode)
plan llm · LOOP **DONE** · `x * 2` · 2 calls (prompt 10,550 / completion 1,655 / reasoning 1,312 / cached **8,448 = 2×4224 in one job**) ·
`run_test` gate: docker died mid-run — `error waiting for container: unexpected EOF` (Docker Desktop restarted, same species of accident as the earlier 20:26Z 8888 config-server flap); `run_build` degraded to `local_fallback` honestly.

## Strike #5 — 16:3xZ (g0ggs8ad, docker healthy again)
plan llm · LOOP **DONE** · `x * 2` · 2 calls (prompt 10,550 / completion 1,701 / reasoning 1,233 / cached 4,224) ·
**gates ALL GREEN on docker**: `run_test` **PASSED** (155 s, exit 0 — the three-phase composite in action) · `run_build` PASSED (40 s) · `run_typecheck` skipped (mypy absent, honestly) · `security` passed · `self_verify` passed → `gates_overall: skipped` (PASS > SKIPPED, never leaned on).
Then the independent verification stage answered: **REJECTED** —
`reasons: [Compilation failed (attempt 3): No pom.xml found]` · `verified_contracts: 0` ·
`rejection-notice.json` on file. SpecProof's differential verifier is Java/Maven-first; a python scratch fixture is not its language — fail-closed, REJECTED, no certificate.

**The chain now stands:** the model genuinely plans, the genuine lane genuinely edits, the gate genuinely runs the sandboxed pytest and passes, and the wall that remains is SpecProof's Java-first verifier — named, with coordinates, not painted over.

## What the chain needed for its first real green at the acceptance door

1. seed the pip wheelhouse (python deps for offline sandbox installs) — necessary, never sufficient;
2. a composite rewrite inside `run_sandboxed` so a bare `python -m pytest` ask in **effective docker mode**
   becomes `venv → pip install --no-index --find-links /wheelhouse (pytest [+ -r requirements.txt]) → pytest`;
   local dev mode unchanged;
3. the `.venv` directory lands inside the disposable workspace only; the strike fixture learned
   to `.gitignore` it; no commit ever carries a virtualenv;
4. and the answer to "was pytest missing?" was: **yes, two independent causes deep** (slim image × bare-command pattern),
   now both eliminated and locked by unit tests.

## What did NOT change, and is not quietly glazed

- gates did not move an inch: SKIPPED still not PASSED, adversarial findings still CRITICAL-block,
  the docker plane is still the drawn line, and the chain is still fail-closed;
- the Docker cache `NOT VERIFIED` note still stands (the named-volume honest gap), now with a working
  wheelhouse fallback instead of a dead pytest;
- exhibit #13 and exhibit_entries=14 stand; Night Watch remains **CRACKED**;
- court `4117d2b0ca5fb23a` **LOCKED**, always stream+include_usage, never cached.

## evidence files on file

- `docs/evidence/2026-11-16-llm-craft-strike.md` — strike #1 record
- `docs/evidence/2026-11-16-llm-craft-strike-accept.json` — strike #1 gate report (BLOCKED · pytest absent)
- `docs/evidence/2026-11-16-llm-craft-strike-accept-2.json` — strike #5 gate report (**run_test PASSED on docker** · verifier REJECTED)
- `docs/evidence/2026-11-16-llm-craft-strike-rejection-2.json` — the REJECTED notice, verbatim
- `scripts/craft_llm_strike.py` — re-runnable end-to-end; deterministic across seeds only where the model cooperates
