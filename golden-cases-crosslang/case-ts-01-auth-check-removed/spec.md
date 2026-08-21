# CrossLang TS 01: Auth Check Removed in changeEmail

A TypeScript module guards email changes with `isAuthorized(user, "user")`
in Base. In Head the guard call is removed, so unauthenticated callers are
accepted instead of rejected with "UNAUTHORIZED" (TypeScript mirror of
case-01 auth-bypass).

## Expected Finding
- Severity: BLOCKER
- Type: auth_bypass
- Evidence: differential execution — the same invariant test passes on
  Base (2/2) and fails on Head (unauthenticated caller accepted)

## Execution Status (honest)
- SpecProof pipeline (experiments/adapters.py): **unsupported** — the
  JavaScript/TypeScript row is `planned`; `detect_node()` raises
  AdapterNotImplemented and no executor is wired. No pipeline detection
  result is claimed.
- Direct toolchain: runnable offline with `node --test` (Node >= 23.6
  type stripping, no dependencies, no network, no API key). Measured on
  this host 2026-08-20 — see README.md.
