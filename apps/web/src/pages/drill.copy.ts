/**
 * Verify Drill copy — every string the #/drill page renders.
 * Bilingual by construction; the page reads locale to pick, never mixes.
 */

export const DRILL = {
  nav: { zh: "验收快问", en: "Verify Drill" },
  title: { zh: "验收快问", en: "Verify Drill" },
  subtitle: { zh: "THE VERIFICATION DRILL", en: "THE VERIFICATION DRILL" },
  lead: { zh: "12 题 · 每题把你送回仓库里去查 · 错了就地见分晓", en: "12 questions — every wrong answer is a doorway back to the repo · answered on the spot" },
  titleNote: { zh: "本页所有题目都锚在真实文件与真实提交上。", en: "Every question anchors to a real file or a real commit in this repository." },
  keyboardHint: { zh: "键盘 1-4 作答 · Enter 进入下一题", en: "Keys 1–4 to answer · Enter for the next question" },

  start: { zh: "开始练功", en: "Start the drill" },
  again: { zh: "再练一遍", en: "Run it back" },
  question: { zh: "第 {n} / 12 题", en: "Question {n} of 12" },
  streak: { zh: "连击", en: "Streak" },
  best: { zh: "最佳成绩", en: "Best" },
  runs: { zh: "开练次数", en: "Runs" },

  correct: { zh: "铁证如山", en: "Iron-verified" },
  wrong: { zh: "徒弟，你答错了", en: "Apprentice, not quite" },
  teachTitle: { zh: "练师说", en: "The teacher says" },
  unansweredFirst: { zh: "先给一个答案再进下一题", en: "Answer first — the drill refuses to be skipped" },
  next: { zh: "下一题", en: "Next" },
  finish: { zh: "揭晓成绩", en: "Reveal the result" },

  resultTitle: { zh: "这一轮，验过了", en: "This round — verified" },
  scoreLine: { zh: "{n} / 12", en: "{n} / 12" },
  newBest: { zh: "最佳纪录被你刷新了", en: "Your personal best just fell" },
  sealRule: { zh: "称号按最佳成绩授予：6+ 正式验收官 · 9+ 见证骑士 · 12 铁证封印", en: "Seals by best score: 6+ Journeyman · 9+ Evidence Knight · 12 Iron Master" },
  mistakesTitle: { zh: "回炉的那几题 · 练师说一句，你才算学会", en: "The ones you missed — read the teacher, then run it back" },
  mistakesNone: { zh: "满分。一字不改地过关。", en: "A perfect 12. Not one mark against you." },
  tourCta: { zh: "想系统地把六盖印全盖了？去巡览 #/tour →", en: "Want the whole lap and all six stamps? Try #/tour →" },
  mistakesGo: { zh: "回看这几题", en: "Review these questions" },
} as const;

export const TIERS = [
  { at: 0, zh: "见习验收官", en: "Apprentice Verifier", note: { zh: "六盖印未满，先把巡览走完", en: "Stamps unearned — walk #/tour first" } },
  { at: 6, zh: "正式验收官", en: "Journeyman Verifier", note: { zh: "手稳了，见证开始落字", en: "Steady hands — the verdicts start to land" } },
  { at: 9, zh: "见证骑士", en: "Evidence Knight", note: { zh: "一眼看穿假点，铁证认你", en: "Sees through fake points on sight — iron recognises you" } },
  { at: 12, zh: "铁证验收官", en: "Iron Verdict Master", note: { zh: "满分封印，仓库替你盖章", en: "A perfect 12 — the repository itself stamps you" } },
] as const;

export function tierIndexFor(score: number): number {
  if (score >= 12) return 3;
  if (score >= 9) return 2;
  if (score >= 6) return 1;
  return 0;
}

export const DRILL_STORE_KEY = "specproof_drill_v1";

export interface DrillRecord {
  best: number;
  runs: number;
}

export function readDrillRecord(): DrillRecord {
  try {
    const raw = globalThis.localStorage?.getItem(DRILL_STORE_KEY);
    if (!raw) return { best: 0, runs: 0 };
    const parsed = JSON.parse(raw) as Partial<DrillRecord>;
    const best = Number(parsed.best) || 0;
    const runs = Number(parsed.runs) || 0;
    return { best: Math.min(12, Math.max(0, best)), runs: Math.max(0, runs) };
  } catch {
    return { best: 0, runs: 0 };
  }
}

export function writeDrillRecord(record: DrillRecord): void {
  try {
    globalThis.localStorage?.setItem(DRILL_STORE_KEY, JSON.stringify(record));
  } catch {
    // storage full — the drill remains playable, it just won't remember
  }
}
