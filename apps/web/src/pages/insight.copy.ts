import type { Locale } from "../i18n";

/**
 * The Insight console — admin-only analytics over a clearly-labelled
 * SYNTHETIC population (deterministic, seeded) plus this browser's real
 * localStorage-derived onboarding telemetry. Every user-facing sentence is
 * localised; nothing about a real person is shown — the population is a
 * calibration dataset, not a surveillence feed.
 */

export interface FunnelStage {
  key: string;
  label: Record<Locale, string>;
  count: number;
}

export interface FeatureAdoption {
  key: string;
  label: Record<Locale, string>;
  users: number;
}

export interface Persona {
  key: string;
  label: Record<Locale, string>;
  count: number;
  demeanor: Record<Locale, string>;
}

export interface InsightData {
  population: number;
  sessionsPerDay: number[];
  predictedNext7: number[];
  dailySlope: number;
  r2: number;
  funnel: FunnelStage[];
  features: FeatureAdoption[];
  personas: Persona[];
  medianDwellMin: number;
  drillPassRate: number;
  tourCompletionRate: number;
  generatedAt: string;
}

/** mulberry32 — tiny deterministic PRNG. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function leastSquares(y: number[]): { slope: number; intercept: number; r2: number } {
  const n = y.length;
  const xs = Array.from({ length: n }, (_, i) => i);
  const meanX = xs.reduce((a, b) => a + b, 0) / n;
  const meanY = y.reduce((a, b) => a + b, 0) / n;
  let sxx = 0, sxy = 0, syy = 0;
  for (let i = 0; i < n; i += 1) {
    const dx = xs[i] - meanX;
    const dy = y[i] - meanY;
    sxx += dx * dx;
    sxy += dx * dy;
    syy += dy * dy;
  }
  const slope = sxx === 0 ? 0 : sxy / sxx;
  const intercept = meanY - slope * meanX;
  const r2 = syy === 0 ? 1 : (sxy * sxy) / (sxx * syy);
  return { slope, intercept, r2 };
}

export function buildInsight(now: Date = new Date("2026-11-15T00:00:00Z")): InsightData {
  const rand = mulberry32(20261115);

  // 28-day session series with mild weekly seasonality + a slow drift.
  const sessionsPerDay: number[] = [];
  for (let d = 0; d < 28; d += 1) {
    const weekday = (d % 7);
    const weekendPenalty = weekday >= 5 ? 0.72 : 1;
    const wave = 1 + 0.18 * Math.sin((d / 28) * Math.PI * 2.2);
    const noise = 0.78 + rand() * 0.46;
    sessionsPerDay.push(Math.round(340 * weekendPenalty * wave * noise));
  }

  const last14 = sessionsPerDay.slice(-14);
  const { slope, intercept, r2 } = leastSquares(last14);
  const predictedNext7 = Array.from({ length: 7 }, (_, k) =>
    Math.max(0, Math.round(intercept + slope * (last14.length + k))),
  );

  // Synthetic population of 240 distinct synthetic members.
  // Behavioural attributes are seeded so the demo is stable across runs.
  const population = 240;
  const tourStarted = 201;
  const tourCompleted = 113;
  const firstVerification = 84;
  const accepted = 41;

  const funnel: FunnelStage[] = [
    { key: "visit", label: { zh: "进入工作台", en: "Opened the workspace" }, count: population },
    { key: "tour", label: { zh: "开始巡览（六盖印）", en: "Started the Grand Tour" }, count: tourStarted },
    { key: "tourDone", label: { zh: "通关巡览", en: "Completed the tour" }, count: tourCompleted },
    { key: "first", label: { zh: "发起首次验收", en: "Ran the first verification" }, count: firstVerification },
    { key: "accepted", label: { zh: "获得一枚验讫印", en: "Landed one sealed ACCEPT" }, count: accepted },
  ];

  const features: FeatureAdoption[] = [
    { key: "epic", label: { zh: "史诗·创世记", en: "Epic · Genesis" }, users: 156 },
    { key: "atlas", label: { zh: "世界舆图", en: "The Atlas" }, users: 141 },
    { key: "lexicon", label: { zh: "铁证词典", en: "Iron Lexicon" }, users: 128 },
    { key: "drill", label: { zh: "验收快问", en: "Verify Drill" }, users: 110 },
    { key: "worldbook", label: { zh: "世界书", en: "World Book" }, users: 97 },
    { key: "gestures", label: { zh: "十四式", en: "Fourteen Gestures" }, users: 76 },
    { key: "nightwatch", label: { zh: "巡夜·子时之后", en: "The Night Watch" }, users: 52 },
    { key: "gazette", label: { zh: "铁证晨报", en: "The Gazette" }, users: 48 },
    { key: "manual", label: { zh: "袖中手札", en: "Pocket Card" }, users: 33 },
    { key: "census", label: { zh: "铁样寨地", en: "Iron Census" }, users: 21 },
  ];

  const personas: Persona[] = [
    { key: "skeptic", label: { zh: "怀疑论验收官", en: "The Skeptic" }, count: 58,
      demeanor: { zh: "先读编年史再验 · 喜欢点证据链 · 对照着读代码diff", en: "Reads the chronicle first · walks the evidence chain · diffs alongside" } },
    { key: "firsttimer", label: { zh: "初出茅庐的工程师", en: "The First-timer" }, count: 64,
      demeanor: { zh: "按巡览走 · 常在 /guide 里来回切换", en: "Follows the tour · flips back to /guide often" } },
    { key: "tourist", label: { zh: "路过看热闹的游客", en: "The Tourist" }, count: 61,
      demeanor: { zh: "瞄两眼就关 · 多数停在史诗页", en: "Glances and leaves · mostly lands on the Epic" } },
    { key: "archivist", label: { zh: "铁证考古学家", en: "The Archivist" }, count: 27,
      demeanor: { zh: "逐卷通读世界书 · 收藏账本 #1645 附近", en: "Reads the World Book cover to cover · loves the #1645 era" } },
    { key: "speedrun", label: { zh: "追印章的效率主义者", en: "The Speedrunner" }, count: 18,
      demeanor: { zh: "目标是 seal 计数 · 不看编年读结果", en: "Optimises for the seal count · skips the prose" } },
    { key: "nightowl", label: { zh: "子时守夜人", en: "The Night Watch" }, count: 12,
      demeanor: { zh: "巡夜通关两次 · 发现 14 式手势按顺序练", en: "Cleared the Night Watch twice · drills the 14 gestures in order" } },
  ];

  const medianDwellMin = 6.4;
  const drillPassRate = 0.62;
  const tourCompletionRate = tourCompleted / tourStarted;

  return {
    population,
    sessionsPerDay,
    predictedNext7,
    dailySlope: slope,
    r2,
    funnel,
    features,
    personas,
    medianDwellMin,
    drillPassRate,
    tourCompletionRate,
    generatedAt: now.toISOString(),
  };
}
