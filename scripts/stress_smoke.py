#!/usr/bin/env python
"""stress_smoke — a bounded, dependency-free load probe.

Two honest lanes:

A) **static lane (default)**: serves `apps/web/dist` over a loopback-only HTTP
   server on an ephemeral port and hammers it with concurrent GETs on the real
   entry assets. This exercises the front door of the product with crisps of
   vanilla throughput — a lower bound sketch, NOT a production rating (the
   production SPA is served by uvicorn *via FastAPI*, not by this handler).

B) **targeted lane** (`--target <url>`): probes exactly one URL you name with
   the same concurrency profile. Point it at a *scratch* endpoint you started;
   do not hammer a live deployment.

Every number printed is measured on this host, this moment, this network stack.

Exit codes: 0 = healthy bounds observed, 1 = an error budget was blown,
2 = dist/ missing (run `npm run build` first).
"""

import argparse
import concurrent.futures as cf
import json
import statistics
import sys
import threading
import time
import urllib.request
from datetime import UTC, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "apps" / "web" / "dist"


def percentile(sorted_vals, p):
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def fetch(url: str, timeout: float):
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read()
            return resp.status, len(body), (time.perf_counter() - t0) * 1000, None
    except Exception as exc:  # noqa: BLE001 - the harness must record, not raise
        return 0, 0, (time.perf_counter() - t0) * 1000, f"{type(exc).__name__}: {exc}"


def run_round(base_url: str, paths: list[str], concurrency: int, requests_per_thread: int, timeout: float):
    urls = []
    per_round = concurrency * requests_per_thread
    for i in range(per_round):
        urls.append(f"{base_url}{paths[i % len(paths)]}")
    latencies, statuses, bytes_read, errors = [], [], 0, []
    with cf.ThreadPoolExecutor(max_workers=concurrency) as pool:
        for status, size, ms, err in pool.map(lambda u: fetch(u, timeout), urls):
            latencies.append(ms)
            statuses.append(status)
            bytes_read += size
            if err:
                errors.append(err)
    latencies.sort()
    total = len(latencies)
    ok = sum(1 for s in statuses if 200 <= s < 300)
    return {
        "total": total,
        "ok": ok,
        "err_rate": 1 - (ok / total) if total else 1.0,
        "p50_ms": percentile(latencies, 0.50),
        "p90_ms": percentile(latencies, 0.90),
        "p95_ms": percentile(latencies, 0.95),
        "p99_ms": percentile(latencies, 0.99),
        "max_ms": latencies[-1] if latencies else 0.0,
        "avg_ms": statistics.fmean(latencies) if latencies else 0.0,
        "bytes_read": bytes_read,
        "sample_errors": errors[:5],
    }


def serve_dist():
    import functools
    import logging
    logging.getLogger("http.server").setLevel(logging.ERROR)

    class _Handler(SimpleHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quiet the access log
            pass

    handler = functools.partial(_Handler, directory=str(DIST))

    # The default listen backlog (5) makes the harness refuse connections under
    # the very high concurrency this probe exists to measure — WinError 10061
    # is the *test server* saturating, not the product. Raise it so the probe
    # measures the app's front door rather than Python's socket queue.
    class _BackloggedServer(ThreadingHTTPServer):
        request_queue_size = 1024

        def handle_error(self, request, client_address):
            # Under load a client may abort a transfer (WinError 10053) — that
            # is an expected outcome of the probe, not a harness crash. Swallow
            # the per-request traceback so it cannot flood stderr (or race the
            # interpreter at shutdown); the measured err_rate still records it.
            pass

    server = _BackloggedServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, name="stress-static", daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded load probe for SpecProof (front door, static lane).")
    parser.add_argument("--target", help="probe exactly this URL instead of the local static lane")
    parser.add_argument("--concurrency", type=int, default=72)
    parser.add_argument("--rounds", type=int, default=4)
    parser.add_argument("--per-thread", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--warmup", type=int, default=0,
                        help="untimed warm-up rounds before the measured rounds (not counted in any verdict)")
    parser.add_argument("--json-report", default="")
    args = parser.parse_args()

    started = datetime.now(UTC).isoformat()
    if args.target:
        base, paths, server, note = (args.target.rstrip("/"), [""], None, "targeted lane")
    else:
        if not DIST.is_dir():
            print(f"dist missing at {DIST} — run `npm run build` first")
            return 2
        assets = sorted(DIST.glob("assets/*.js"), key=lambda p: p.stat().st_size, reverse=True)
        paths = ["/"] + ["/" + str(a.relative_to(DIST)).replace("\\", "/") for a in assets[:2]]
        note = f"static lane, {len(paths)} entry assets, fresh server on 127.0.0.1"
        server, base = serve_dist()
        print("serving dist/ on", base)

    if args.warmup:
        for w in range(args.warmup):
            warm = run_round(base, paths, args.concurrency, args.per_thread, args.timeout)
            print(f"warmup {w + 1}/{args.warmup}: total={warm['total']} ok={warm['ok']} "
                  f"p99={warm['p99_ms']:.1f}ms (not counted)")

    rounds_out = []
    for r in range(args.rounds):
        stats = run_round(base, paths, args.concurrency, args.per_thread, args.timeout)
        rounds_out.append(stats)
        print(f"round {r + 1}/{args.rounds}: total={stats['total']} ok={stats['ok']} "
              f"err={stats['err_rate'] * 100:.2f}% p50={stats['p50_ms']:.1f}ms "
              f"p95={stats['p95_ms']:.1f}ms p99={stats['p99_ms']:.1f}ms "
              f"max={stats['max_ms']:.1f}ms")

    if server:
        server.shutdown()
        server.server_close()

    worst_err = max(r["err_rate"] for r in rounds_out)
    worst_p99 = max(r["p99_ms"] for r in rounds_out)
    summary = {
        "started_utc": started,
        "note": note,
        "concurrency": args.concurrency,
        "per_thread": args.per_thread,
        "warmup_rounds": args.warmup,
        "rounds": rounds_out,
        "verdict": "OK" if worst_err <= 0.01 and worst_p99 < 5000 else "BUDGET-BLOWN",
        "honesty": "This is a static-asset delivery probe on this host; it is not a FastAPI/MySQL/Redis rating.",
    }
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.json_report:
        out = Path(args.json_report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print("report written to", out)
    print(f"\nworst err_rate={worst_err * 100:.2f}% worst p99={worst_p99:.1f}ms verdict={summary['verdict']}")
    return 0 if summary["verdict"] == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
