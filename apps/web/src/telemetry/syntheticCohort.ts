/**
 * specproof_synthetic_cohort — deterministic simulation of *impatient visitors*.
 *
 * Why this exists (owner directive §九): a real visitor may open a page, lose
 * patience and close it, or not know where to go and tap around blindly.
 * The Observatory already shows one real browser's own ledger; this module
 * produces the OTHER half of the owner's ask: a large, seeded simulation of
 * those impatient behaviors — bounce, rage, wander, scanner — so the admin
 * room can watch a whole synthetic crowd, not one person.
 *
 * Honesty rules (inherited from the house style):
 *   - Seeded PRNG (mulberry32). Same seed → byte-identical summary, always.
 *   - Persona mix is a CALIBRATION, not a measurement: probabilities sit in
 *     the commonly published 40–60% bounce range for content sites. No live
 *     fetch ever happens here; constants are recorded below with their origin.
 *   - No real person is ever read, uploaded, or inferred. The cohort is a
 *     thought experiment rendered as numbers.
 */

import type { HeatEvent } from "./behavior";

export const SYNTHETIC_SEED = 20261119;

/* mulberry32 — small, fast, deterministic. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export type PersonaKind =
  | "bouncer"   // opens, never engages, leaves in seconds
  | "skimmer"   // glances, small scroll, leaves before the seal
  | "rager"     // taps a control repeatedly — frustration, not intent
  | "wanderer"  // hops many rooms, refuses the tour — lost
  | "scanner"   // finishes the tour quickly, no drill — half-hearted
  | "finisher"; // tour → drill → asks the book — the whole arc

/** Calibration constants (2026-11-19), not fetched live:
 *  content-site bounce ≈ 40–60% (GA4-class studies); a small frustration
 *  tail is realistic for any UI; completion stays rare on purpose. */
export const PERSONA_MIX: Record<PersonaKind, number> = {
  bouncer: 0.44,
  skimmer: 0.20,
  rager: 0.08,
  wanderer: 0.12,
  scanner: 0.09,
  finisher: 0.07,
};

export const PERSONA_LABEL: Record<PersonaKind, { zh: string; en: string; behavior: { zh: string; en: string } }> = {
  bouncer: {
    zh: "秒退者",
    en: "Bouncer",
    behavior: { zh: "打开、愣 3–9 秒、直接关掉", en: "Opens, hesitates 3–9s, closes" },
  },
  skimmer: {
    zh: "扫读者",
    en: "Skimmer",
    behavior: { zh: "看一眼首页前三屏、滑一下就走", en: "Glances at the top, scrolls a little, leaves" },
  },
  rager: {
    zh: "急躁点触者",
    en: "Rager",
    behavior: { zh: "对同一个控件连点 3 次以上", en: "3+ taps on the same control within seconds" },
  },
  wanderer: {
    zh: "迷路漫游者",
    en: "Wanderer",
    behavior: { zh: "点 4–7 个入口、始终找不到自己要的", en: "Opens 4–7 routes, never finds the room they wanted" },
  },
  scanner: {
    zh: "速览走马灯",
    en: "Scanner",
    behavior: { zh: "刷完导览却不快问、也不留下", en: "Finishes the tour, skips the drill, leaves" },
  },
  finisher: {
    zh: "走完全程者",
    en: "Finisher",
    behavior: { zh: "导览 → 快问 → 请教藏经阁", en: "Tour → Drill → Ask the Book" },
  },
};

export interface SyntheticSession {
  id: number;
  persona: PersonaKind;
  events: HeatEvent[];
}

const ALL_ROUTES = ["/#/dashboard", "/#/tour", "/#/atlas", "/#/library", "/#/drill", "/#/guess", "/#/ask-the-book", "/#/chronicle"];
const HOME = "/#/dashboard";

function pickRoutes(rand: () => number, n: number): string[] {
  const out: string[] = [];
  const used = new Set<string>();
  while (out.length < n) {
    const r = ALL_ROUTES[Math.floor(rand() * ALL_ROUTES.length)];
    if (!used.has(r)) {
      used.add(r);
      out.push(r);
    }
  }
  return out;
}

function dwellMs(rand: () => number, lo: number, hi: number): number {
  return Math.round(lo + rand() * (hi - lo));
}

function simulateSession(rand: () => number, id: number, persona: PersonaKind): SyntheticSession {
  const events: HeatEvent[] = [];
  const t0 = 1_700_000_000_000 + id * 47_000 + Math.floor(rand() * 40_000);
  const at = (offsetMs: number) => t0 + offsetMs;

  const pushRoute = (path: string, offset: number, holdMs: number) => {
    events.push({ t: "view", path, at: at(offset) });
    events.push({ t: "dwell", path, ms: holdMs, at: at(offset + holdMs) });
  };

  switch (persona) {
    case "bouncer": {
      pushRoute(HOME, 0, dwellMs(rand, 3_000, 9_000));
      break;
    }
    case "skimmer": {
      pushRoute(HOME, 0, dwellMs(rand, 12_000, 35_000));
      break;
    }
    case "rager": {
      const target = ["nav.drill", "quickstart-cta", "lang-switch"][Math.floor(rand() * 3)];
      pushRoute(HOME, 0, dwellMs(rand, 20_000, 48_000));
      for (let i = 0; i < 3 + Math.floor(rand() * 3); i += 1) {
        events.push({ t: "rage", target, path: HOME, at: at(22_000 + i * 700 + Math.floor(rand() * 300)) });
      }
      break;
    }
    case "wanderer": {
      const n = 4 + Math.floor(rand() * 4);
      let offset = 0;
      for (const route of pickRoutes(rand, n)) {
        const hold = dwellMs(rand, 6_000, 25_000);
        pushRoute(route, offset, hold);
        offset += hold + 1_500;
      }
      break;
    }
    case "scanner": {
      pushRoute(HOME, 0, dwellMs(rand, 10_000, 20_000));
      pushRoute("/#/tour", 12_000, dwellMs(rand, 40_000, 110_000));
      break;
    }
    case "finisher": {
      pushRoute(HOME, 0, dwellMs(rand, 15_000, 30_000));
      pushRoute("/#/tour", 16_000, dwellMs(rand, 60_000, 150_000));
      pushRoute("/#/drill", 170_000, dwellMs(rand, 45_000, 120_000));
      pushRoute("/#/ask-the-book", 300_000, dwellMs(rand, 30_000, 90_000));
      break;
    }
  }

  return { id, persona, events };
}

function pickPersona(rand: () => number): PersonaKind {
  const roll = rand();
  let acc = 0;
  for (const kind of Object.keys(PERSONA_MIX) as PersonaKind[]) {
    acc += PERSONA_MIX[kind];
    if (roll < acc) return kind;
  }
  return "finisher";
}

export interface PersonaSummary {
  persona: PersonaKind;
  count: number;
  share: number; // 0..1
  medianDwellMs: number | null;
  rageEvents: number;
}

export interface SyntheticCohort {
  seed: number;
  size: number;
  bouncers: number;
  impatientRate: number;            // bouncer + rager share (0..1)
  totalRageEvents: number;
  rageSessions: number;
  medianDwellMs: number;
  finishers: number;
  personaSummaries: PersonaSummary[];
  funnel: Array<{ key: "opened" | "engaged" | "toured" | "drilled" | "sealed"; count: number }>;
  note: { zh: string; en: string };
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1 ? sorted[mid] : Math.round((sorted[mid - 1] + sorted[mid]) / 2);
}

export function simulateCohort(size = 240, seed: number = SYNTHETIC_SEED): SyntheticCohort {
  const rand = mulberry32(seed);
  const sessions: SyntheticSession[] = [];
  for (let i = 0; i < size; i += 1) {
    sessions.push(simulateSession(rand, i, pickPersona(rand)));
  }

  const dwellsOf = (s: SyntheticSession) => s.events.filter((e) => e.t === "dwell").map((e) => (e as { ms: number }).ms);
  const allDwells = sessions.flatMap(dwellsOf);
  const rageEvents = sessions.flatMap((s) => s.events.filter((e) => e.t === "rage"));
  const sessionsWithRage = sessions.filter((s) => s.events.some((e) => e.t === "rage"));

  const personaSummaries: PersonaSummary[] = (Object.keys(PERSONA_MIX) as PersonaKind[]).map((persona) => {
    const bucket = sessions.filter((s) => s.persona === persona);
    const dwells = bucket.flatMap(dwellsOf);
    return {
      persona,
      count: bucket.length,
      share: bucket.length / size,
      medianDwellMs: dwells.length ? median(dwells) : null,
      rageEvents: bucket.flatMap((s) => s.events.filter((e) => e.t === "rage")).length,
    };
  });

  const opened = sessions.length;
  const engaged = sessions.filter((s) => s.persona !== "bouncer").length;
  const toured = sessions.filter((s) => s.persona === "scanner" || s.persona === "finisher").length;
  const drilled = sessions.filter((s) => s.persona === "finisher").length;
  const sealed = drilled; // the drill is the seal room for this model

  const bouncers = sessions.filter((s) => s.persona === "bouncer").length;
  const ragers = sessions.filter((s) => s.persona === "rager").length;

  return {
    seed,
    size,
    bouncers,
    impatientRate: (bouncers + ragers) / size,
    totalRageEvents: rageEvents.length,
    rageSessions: sessionsWithRage.length,
    medianDwellMs: median(allDwells),
    finishers: sealed,
    personaSummaries,
    funnel: [
      { key: "opened", count: opened },
      { key: "engaged", count: engaged },
      { key: "toured", count: toured },
      { key: "drilled", count: drilled },
      { key: "sealed", count: sealed },
    ],
    note: {
      zh: `合成群体 · 种子 ${seed} · 不是任何人 · 校准常数见代码注释`,
      en: `Synthetic cohort · seed ${seed} · not anyone · calibration constants documented inline`,
    },
  };
}
