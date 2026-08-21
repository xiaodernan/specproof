# Attribution Case Set (go-nogo gate #3, W164 lane)

Purpose: give gate #3 ("PR 归因准确率 ≥ 90%") an independent, quantified
attribution-accuracy measurement. Built and measured by
scripts/attribution_cases.py against the REAL deterministic pipeline
(python -m cli.specproof.main eval 的同一 graph 调用, LLM off).

## Construct

Each case is a synthetic PR review: scenario.json names an existing pair of
demo/spring-backend refs (tags only — the shared repo's git state is never
mutated), spec.md states the requirement, and ground-truth.json declares
which contracts are head-introduced defects vs base-side (pre-existing)
defects:

- head_defects: the contract is broken ONLY by the reviewed head. Correct
  attribution = the pipeline publishes a confirmed finding for it
  (attributed to HEAD). Anything else is a missed attribution (漏归因).
- base_defects: the contract is already broken on the base side of the
  review. Correct attribution = the pipeline does NOT publish a confirmed
  finding for it (错归因 if it does).

The existing demo tags have no head that preserves a base bug, so the two
base-side constructs are expressed with cross-tag pairings:

- case-att-07: base_ref=case-17-head (inverted unique guard, pre-existing)
  vs head_ref=case-18-head (guard fixed, unrelated routing-key bug). The
  pipeline must report the pre-existing base failure without blaming the
  head.
- case-att-08: same ref pair, two-contract spec — Base fails UNIQUE-01
  while Head fails EVENT_ONCE-01 (Base 与 Head 各自都有失败). Measures
  how attribution behaves when both sides fail.

## Metric

attribution_accuracy_pct = 100 * (correctly_attributed +
correctly_not_attributed) / (head_defects + base_defects), where
correctly_not_attributed = base_defects - misattributed_to_head.
missed_attribution counts head defects whose finding is absent or was
downgraded to not_attributed.

Results: docs/eval/attribution-results.json (per-case rows + totals).
Eval-side HTML/sidecar: docs/eval/attribution-eval.html /
attribution-eval.results.json.

## Commands

    python scripts/attribution_cases.py build
    python scripts/attribution_cases.py run
    python -m cli.specproof.main eval --cases golden-cases-attribution --repo . --no-llm --output docs/eval/attribution-eval.html
