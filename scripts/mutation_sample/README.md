# mutation_sample — bundled offline mutation target

A minimal, self-contained target for `python scripts/bench_mutation.py
--offline`: no Docker, no network, no LLM.

## Layout

- `module/pricing.py` — real price-calculation behavior (bulk discount, free
  shipping, tax, advisory tip);
- `spec/spec.md` — the human contract; `spec/contract.py` is its
  deterministic compilation (`check_module(source) -> violations`, the
  SpecProof-verdict stand-in);
- `tests/` — pytest suite (the differential test channel);
- `mutants/manifest.json` — six hand-defined mutants: operand swap, boundary
  change, return inversion, and three constant changes.

## Honesty note

Mutant M06 changes an out-of-spec, untested behavior (the advisory tip rate)
and survives both channels on purpose, so the offline run reports a real,
non-rigged kill rate: 5 killed / 1 survived = 83.3%. See
docs/eval/MUTATION_PLAN.md for the method and limitations.

## Standalone use

Run the test suite directly from this directory:

    python -m pytest -q
