# CrossLang Go 01: Inverted Domain Blocklist (Execution-Only Regression)

The registration validator's blocklist guard is inverted in Head: addresses
from blocked domains are now accepted and addresses from ordinary domains
are rejected. The diff is a single `!` that a static diff reader cannot
judge without executing the behaviour (Go mirror of case-17
logic-inversion).

## Expected Finding
- Severity: BLOCKER
- Type: data_integrity
- Evidence: differential execution — the same invariant test passes on
  Base (2/2) and fails on Head (both expectations inverted)

## Execution Status (honest)
- SpecProof pipeline (experiments/adapters.py): **unsupported** — the Go row
  is `planned`; `detect_go()` raises AdapterNotImplemented and no
  executor is wired. No pipeline detection result is claimed.
- Direct toolchain: NOT run on this host — no Go toolchain in PATH
  (checked 2026-08-20). The sources follow idiomatic Go and mirror the
  toycalc-sum sample layout; they remain unexecuted until a Go toolchain
  or Go adapter exists.
