/**
 * specproof_heat_v1 — this browser's own raw tap/dwell ledger.
 *
 * What it is: a strictly first-party, localStorage-only record of how THIS
 * browser uses the app. Nothing is uploaded, nothing is shared, nothing is
 * attributed to any real person — the data never leaves the device.
 *
 * What it records (ring buffer, capped at 1200 events):
 *   view  — hash-route became visible
 *   dwell — how long that route stayed in front of a human (ms)
 *   rage  — 3+ taps on the same element signature within 2 seconds
 *
 * What it deliberately never records: keystrokes, form values, passwords,
 * URLs outside this app, or anything the device considers sensitive.
 * Clearing your browsing data erases it entirely; there is also a button
 * in the Insight Deck for one tap of the same.
 */

export const BEHAVIOR_KEY = "specproof_heat_v1";
const MAX_EVENTS = 1200;
const RAGE_WINDOW_MS = 2000;
const RAGE_THRESHOLD = 3;

export type HeatEvent =
  | { t: "view"; path: string; at: number }
  | { t: "dwell"; path: string; ms: number; at: number }
  | { t: "rage"; target: string; path: string; at: number };

/* ── ring buffer primitives (pure, unit-testable) ─────────────── */

export function appendHeat(events: HeatEvent[], next: HeatEvent, cap = MAX_EVENTS): HeatEvent[] {
  const sliced = events.length >= cap ? events.slice(events.length - cap + 1) : events.slice();
  sliced.push(next);
  return sliced;
}

export function deriveHeat(events: HeatEvent[]) {
  const views: { path: string; at: number }[] = [];
  const dwells: { path: string; ms: number }[] = [];
  const rages: { target: string; at: number }[] = [];
  for (const e of events) {
    if (e.t === "view") views.push({ path: e.path, at: e.at });
    else if (e.t === "dwell") dwells.push({ path: e.path, ms: e.ms });
    else if (e.t === "rage") rages.push({ target: e.target, at: e.at });
  }

  const perRoute = new Map<string, { path: string; views: number; dwellMs: number }>();
  for (const v of views) {
    const row = perRoute.get(v.path) ?? { path: v.path, views: 0, dwellMs: 0 };
    row.views += 1;
    perRoute.set(v.path, row);
  }
  for (const d of dwells) {
    const row = perRoute.get(d.path) ?? { path: d.path, views: 0, dwellMs: 0 };
    row.dwellMs += d.ms;
    perRoute.set(d.path, row);
  }

  const rageTop = new Map<string, number>();
  for (const r of rages) rageTop.set(r.target, (rageTop.get(r.target) ?? 0) + 1);

  const quickBounces = dwells.filter((d) => d.ms < 4000).length;
  const spanMs = views.length >= 2 ? views[views.length - 1].at - views[0].at : 0;
  const dwellValues = dwells.map((d) => d.ms).sort((a, b) => a - b);
  const medianDwellMs = dwellValues.length
    ? dwellValues.length % 2
      ? dwellValues[(dwellValues.length - 1) / 2]
      : Math.round((dwellValues[dwellValues.length / 2 - 1] + dwellValues[dwellValues.length / 2]) / 2)
    : 0;

  return {
    events: events.length,
    views: views.length,
    distinctRoutes: perRoute.size,
    quickBounces,
    rageTotal: rages.length,
    rageTop: [...rageTop.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5).map(([target, count]) => ({ target, count })),
    medianDwellSec: Math.round(medianDwellMs / 1000),
    spanMin: Math.round(spanMs / 60000),
    routes: [...perRoute.values()].sort((a, b) => b.views - a.views).slice(0, 8),
  };
}

/* ── storage plumbing ──────────────────────────────────────────── */

function readRaw(): HeatEvent[] {
  try {
    const raw = globalThis.localStorage?.getItem(BEHAVIOR_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as HeatEvent[]) : [];
  } catch {
    return [];
  }
}

function writeRaw(events: HeatEvent[]): void {
  try {
    globalThis.localStorage?.setItem(BEHAVIOR_KEY, JSON.stringify(events.slice(-MAX_EVENTS)));
  } catch {
    /* quota exceeded — drop the oldest half and try once */
    try {
      globalThis.localStorage?.setItem(BEHAVIOR_KEY, JSON.stringify(events.slice(-Math.floor(MAX_EVENTS / 2))));
    } catch {
      /* still unwritable — stay silent, never crash the app */
    }
  }
}

export function loadHeat(): HeatEvent[] {
  return readRaw();
}

export function clearHeat(): void {
  try {
    globalThis.localStorage?.removeItem(BEHAVIOR_KEY);
  } catch {
    /* nothing to clear */
  }
}

function currentPath(): string {
  const raw = globalThis.location?.hash?.replace(/^#/, "") ?? "";
  return raw.startsWith("/") ? raw.split("?")[0] : "/" + (raw || "").split("?")[0];
}

function targetSignature(el: Element | null): string | null {
  if (!el) return null;
  const tag = el.tagName?.toLowerCase() ?? "?";
  const cls = (el.getAttribute?.("class") ?? "").split(/\s+/).filter(Boolean).filter((c) => !c.startsWith("_") && c.length < 32).slice(0, 2).join(".");
  const text = (el.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 24);
  return `${tag}.${cls}|${text}`;
}

/** Attach once at app start; safe to call multiple times (no-op after first). */
let attached = false;
export function attachBehaviorTracking(): void {
  if (attached) return;
  attached = true;

  let viewStart = Date.now();
  let viewPath = currentPath();
  const taps: { sig: string; at: number }[] = [];

  const push = (ev: HeatEvent) => writeRaw(appendHeat(readRaw(), ev));

  if (globalThis.localStorage) {
    push({ t: "view", path: viewPath, at: Date.now() });
  }

  globalThis.addEventListener?.("hashchange", () => {
    const now = Date.now();
    push({ t: "dwell", path: viewPath, ms: now - viewStart, at: now });
    viewStart = now;
    viewPath = currentPath();
    push({ t: "view", path: viewPath, at: now });
  });

  globalThis.addEventListener?.("visibilitychange", () => {
    if (globalThis.document?.visibilityState === "hidden") {
      const now = Date.now();
      push({ t: "dwell", path: viewPath, ms: now - viewStart, at: now });
      viewStart = now;
    }
  });

  // Capture-phase tap listener; keys on a stable element signature.
  globalThis.document?.addEventListener(
    "click",
    (event) => {
      const sig = targetSignature(event.target as Element | null);
      if (!sig) return;
      const now = Date.now();
      const fresh = taps.filter((t) => now - t.at < RAGE_WINDOW_MS);
      fresh.push({ sig, at: now });
      taps.length = 0;
      taps.push(...fresh.slice(-8));
      const hits = fresh.filter((t) => t.sig === sig).length;
      if (hits >= RAGE_THRESHOLD) {
        push({ t: "rage", target: sig, path: viewPath, at: now });
        // one rage event per window per signature: swallow the rest
        for (let i = taps.length - 1; i >= 0; i -= 1) {
          if (taps[i].sig === sig) taps[i].at = 0;
        }
      }
    },
    { capture: true, passive: true },
  );
}
