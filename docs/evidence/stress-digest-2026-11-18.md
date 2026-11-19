# Weekly stress digest · the strike, read aloud

- mode: offline · deterministic table, no model
- evidence: weekly-2026-11-18.json (packet 1010 bytes)
- started_utc: 2026-11-18T19:14:52.419221+00:00 · concurrency=48 · per_thread=2 · warmup_rounds=2
- note from the strike: static lane, 3 entry assets, fresh server on 127.0.0.1
- floor_ms: 5000 (machine sanity floor — not an SLO, not a verdict on this repo)
- floor_comparison: under · worst_p99_ms=1888.2743487500054 · best_p99_ms=1878.110929900005
- the strike's machine label, verbatim (never re-graded): OK

## Rounds

| round | err_rate | p99_ms | p95_ms | avg_ms | total/ok | bytes |
|---|---|---|---|---|---|---|
| 1 | 0.0 | 1888.2743487500054 | 1854.2357539999978 | 526.6906444791666 | 96/96 | 43688512 |
| 2 | 0.0 | 1878.110929900005 | 1479.4063337499992 | 467.65639021874904 | 96/96 | 43688512 |

## The reading (offline, deterministic)

- Every round finished with err_rate 0 — the static lane delivered, byte after byte.
- worst_p99_ms = 1888.3, which sits 3111.7 ms UNDER the 5000 ms machine floor on this host.
- honest note from the strike, verbatim: “This is a static-asset delivery probe on this host; it is not a FastAPI/MySQL/Redis rating.”

*This is a reading of one strike on one host. It is never a release decision; the court is never in this room.*
