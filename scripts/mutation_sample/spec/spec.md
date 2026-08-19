# Offline Mutation Sample — Pricing Contract

The human contract for the bundled mutation target. spec/contract.py is its
deterministic compilation (the offline stand-in for the real
compile_contracts + checkers nodes — no LLM, no network).

## Contract

- C1 Bulk discount: a subtotal >= 500.0 gets a 10% discount, applied as
  multiplication by (1 - 0.10) and rounded to cents. Subtotal below the
  threshold is returned unchanged.
- C2 Free shipping: a subtotal >= 100.0 ships free. The threshold is exactly
  100.0.
- C3 Tax: 8% tax is applied as multiplication by (1 + 0.08), rounded to cents.

## Out of scope (deliberate)

- The suggested tip amount (SUGGESTED_TIP_RATE) is advisory UX: it is not
  part of the contract and has no test coverage. Mutant M06 changes it and
  therefore survives both channels — an honest coverage gap that the bench
  reports as SURVIVED rather than a rigged 100% kill rate.
