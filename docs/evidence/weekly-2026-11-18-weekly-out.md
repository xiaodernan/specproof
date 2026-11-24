# Weekly stress strike — run 3
- finished_utc: 2026-11-18T19:15:04Z
- exit_code: 0
- evidence: docs/evidence/weekly-2026-11-18.json (artifact)

The harness names its report with a temp suffix; the committed artifact is
the date-named file above — the same run, the same bytes.  What that run
printed:

- warmup 1/2: total=96 ok=96 p99=2878.0ms (not counted)
- warmup 2/2: total=96 ok=96 p99=4372.5ms (not counted)
- round 1/2: total=96 ok=96 err=0.00% p50=20.9ms p95=1854.2ms p99=1888.3ms max=1891.7ms
- round 2/2: total=96 ok=96 err=0.00% p50=22.5ms p95=1479.4ms p99=1878.1ms max=1882.1ms
- verdict: OK — worst err_rate 0.00%, worst p99 1888.3ms

The command that produced it (the harness the repository carries):

```
python scripts/stress_smoke.py --concurrency 48 --per-thread 2 --warmup 2 --rounds 2
```

A fresh run of the same profile is in docs/evidence/stress-2026-11-23.md.
