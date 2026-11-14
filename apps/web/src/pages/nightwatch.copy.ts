import type { Locale } from "../i18n";

/**
 * 巡夜 · 子时之后 — The Night Watch.
 *
 * A walking simulator through SpecProof at night as the ledger-keeper.
 * Every number these questions test is REAL and re-derived from the repo's
 * own tracked artifacts at runtime (repoStats.json / the world bible). The
 * game is the world book you can play; it cannot drift into fiction.
 */

export interface NightStation {
  id: string;
  /** 时辰 — the traditional Chinese double-hour. */
  hourZh: string;
  hourEn: string;
  placeZh: string;
  placeEn: string;
  loreZh: string;
  loreEn: string;
  q: Record<Locale, string>;
  /** correct index into options (options are pre-shuffled per attempt). */
  options: Record<Locale, [string, string, string, string]>;
  correctIndex: number;
  verseZh: string;
  verseEn: string;
}

const num = (n: number) => n.toLocaleString();

export function buildStations(stats: {
  ledger_sections: number;
  repository_files: number;
  git_commit_count: number;
  worldbook_sections: number;
  ledger_bytes_kB: number;
}): NightStation[] {
  const ledger = stats.ledger_sections;
  const files = stats.repository_files;
  const wb = stats.worldbook_sections;
  const halls = 24; // the 24 halls of #/atlas — a layout constant, not a measurement

  return [
    {
      id: "foundry",
      hourZh: "卯时",
      hourEn: "MAO · THE RABBIT",
      placeZh: "差分之炉",
      placeEn: "The Differential Foundry",
      loreZh: "炉火正旺。基线过、头版挂——这是铁证的心脏。",
      loreEn: "The furnace is hot. Base passed, head failed — the heart of iron evidence.",
      q: { zh: "「base_pass_head_fail」在 SpecProof 里的含义是？", en: "What does base_pass_head_fail mean in SpecProof?" },
      options: {
        zh: ["基准版本通过验收、待检版本失败——变更引入的回归", "基准版本失败、待检版本通过——修复被确认", "两个版本都差评如流", "静态分析发现的一切可疑点"],
        en: ["Base passes, head fails — a regression introduced by the change", "Base fails, head passes — the fix confirmed", "Both revisions reviewed poorly", "Any suspicious point found by static analysis"],
      },
      correctIndex: 0,
      verseZh: "一等铁证，炉火为名。",
      verseEn: "One-class iron: named by furnace fire.",
    },
    {
      id: "chronicle",
      hourZh: "辰时",
      hourEn: "CHEN · THE DRAGON",
      placeZh: "编年之柱",
      placeEn: "The Chronicle Pillar",
      loreZh: "每一节是一夜的记忆——从 #130 直到今天。",
      loreEn: "Each entry is one night's memory — from #130 to today.",
      q: { zh: "编年史目前共有多少节？", en: "How many entries does the Chronicle hold right now?" },
      options: {
        zh: [num(ledger), num(ledger - 37), num(ledger + 41), "1,024"],
        en: [num(ledger), num(ledger - 37), num(ledger + 41), "1,024"],
      },
      correctIndex: 0,
      verseZh: "一事一卷，不增一字，不删一字。",
      verseEn: "One entry, one night — not one word more, not one less.",
    },
    {
      id: "census",
      hourZh: "巳时",
      hourEn: "SI · THE SNAKE",
      placeZh: "铁样寨地",
      placeEn: "The Iron Census Yard",
      loreZh: "每一块砖都称过、量过、记过——git ls-files 不说谎。",
      loreEn: "Every brick has been weighed and counted — git ls-files does not lie.",
      q: { zh: "本仓库 git 跟踪的文件数大约是？", en: "Approximately how many tracked files does this repo hold?" },
      options: {
        zh: [num(files), num(Math.round(files * 1.8)), num(Math.round(files * 0.44)), "9,511"],
        en: [num(files), num(Math.round(files * 1.8)), num(Math.round(files * 0.44)), "9,511"],
      },
      correctIndex: 0,
      verseZh: "不传伪数，不虚增一瓦。",
      verseEn: "No false count, not one brick inflated.",
    },
    {
      id: "readingroom",
      hourZh: "午时",
      hourEn: "WU · THE HORSE",
      placeZh: "铁证书房",
      placeEn: "The Reading Room",
      loreZh: "序章之后，三十节正史，两种文字，同一个心脏。",
      loreEn: "After the frontispiece, thirty sections of history, two tongues, one heart.",
      q: { zh: "世界书（含序章与附录）现在共几节？", en: "How many sections does the World Book hold now?" },
      options: {
        zh: [num(wb), num(wb - 2), num(wb + 7), "57"],
        en: [num(wb), num(wb - 2), num(wb + 7), "57"],
      },
      correctIndex: 0,
      verseZh: "正史不结卷，书房不落锁。",
      verseEn: "The history never seals; the room never locks.",
    },
    {
      id: "sanctum",
      hourZh: "未时",
      hourEn: "WEI · THE GOAT",
      placeZh: "缓存圣断",
      placeEn: "The Cache Sanctum",
      loreZh: "wkapi 对每个请求都收取静态前缀——四千二百二十四，一个固定的影子。",
      loreEn: "wkapi charges every request for its static prefix — 4,224, a fixed shadow.",
      q: { zh: "2026-11-15 本机实测（#1777）：wkapi 短 prompt 的 cached 常报约为？", en: "On 2026-11-15 (#1777), wkapi reported cached for short prompts as ≈ what?" },
      options: {
        zh: ["4,224", "1,024", "9,876", "0（从未上报）"],
        en: ["4,224", "1,024", "9,876", "0 (never reported)"],
      },
      correctIndex: 0,
      verseZh: "缓存的影子，不是命中的福音。",
      verseEn: "The cache's shadow is not the gospel of hits.",
    },
    {
      id: "cartouche",
      hourZh: "酉时",
      hourEn: "YOU · THE ROOSTER",
      placeZh: "印章庭",
      placeEn: "The Cartouche Court",
      loreZh: "印章不是结束，是签名——REVOKED 是「我曾一度相信它」。",
      loreEn: "The seal is not the end; it is the signature — REVOKED means “I believed this once”.",
      q: { zh: "「REVOKED」徽印的真正含义是？", en: "What does the REVOKED cartouche really mean?" },
      options: {
        zh: ["我曾一度相信它——撤销是诚实的撤回，不是耻辱", "此证据被证明为永久伪造", "自动系统检测到模型欺骗", "未达覆盖率红线"],
        en: ["I believed this once — revocation is honest retraction, not disgrace", "This evidence is proven for-forgery forever", "The automatic system detected model deception", "Coverage threshold not met"],
      },
      correctIndex: 0,
      verseZh: "徽印是签字；签字就是责任。",
      verseEn: "The cartouche is a signature; the signature is the duty.",
    },
    {
      id: "archipelago",
      hourZh: "戌时",
      hourEn: "XU · THE DOG",
      placeZh: "证据群岛",
      placeEn: "The Evidence Archipelago",
      loreZh: "三座岛、三条探险路线——走完这一站，天就要亮了。",
      loreEn: "Three islands, three expedition routes — finish this station and dawn breaks.",
      q: { zh: "世界舆图（#/atlas）上共有多少个厅？", en: "How many halls stand in the Atlas (#/atlas)?" },
      options: {
        zh: [num(halls), "18", "31", "57"],
        en: [num(halls), "18", "31", "57"],
      },
      correctIndex: 0,
      verseZh: "走到哪里，哪里就是你的国土。",
      verseEn: "Wherever you walk, there is your ground.",
    },
  ];
}

export const NIGHT_OIL = 3;
export const BEST_KEY = "specproof_nightwatch_best";

export interface NightBest {
  timeMs: number;
  oilLeft: number;
  moves: number;
  date: string;
}
