import type { Locale } from "../i18n/strings";

/**
 * The SpecProof Manual — the pocket card, turned into a first-class route
 * inside the product itself. It renders the exact same artifact you would
 * carry out the door; it exists because "open the doc" is not a feature the
 * way "open the Manual in the sidebar" is.
 *
 * Written bilingually. The print.css is reused, so the whole page is a
 * one-click A4 for anyone who needs a physical cheat sheet at the desk.
 */

export interface ManualCommand {
  id: string;
  title: Record<Locale, string>;
  body: string;
}

export interface ManualSection {
  title: Record<Locale, string>;
  rows: Record<Locale, string[]>;
}

export interface ManualPackage {
  subtitle: Record<Locale, string>;
  lead: Record<Locale, string>;
  sections: ManualSection[];
  commands: ManualCommand[];
  punchline: Record<Locale, string>;
  copyLabel: Record<Locale, string>;
  copiedLabel: Record<Locale, string>;
}

export const MANUAL: ManualPackage = {
  subtitle: {
    zh: "SpecProof · 三十秒手札",
    en: "SpecProof · The 30-second Pocket Card",
  },
  lead: {
    zh: "打印或收藏：带上这一页，就带上了『出门前必须知道』的全部。",
    en: "Print or keep: this one page is everything you must know before opening the door.",
  },
  sections: [
    {
      title: { zh: "出门带着这 5 件事", en: "The five things to carry out the door" },
      rows: {
        zh: [
          "这是验收，不是写代码：你交 base、head、spec，它交回铁证。证据先于一切结论。",
          "先看红色，再看绿色：BLOCKER 阻止合并；UNVERIFIED 不是 PASS。",
          "缓存命中率只是一只数字——null 就是 null，不是零，也绝不是“—”。",
          "worktree 是你自己的：demo/spring-backend，`base` 是原始实现，`head-v1` 故意删了 @PreAuthorize。",
          "30 秒自检：`python scripts/demo_doctor.py` 全绿后再跑验收。",
        ],
        en: [
          "This is acceptance, not authoring: you bring base/head/spec, SpecProof returns iron evidence. Evidence sits above any conclusion.",
          "Read the red before you read the green: a BLOCKER blocks the merge; UNVERIFIED is not PASS.",
          "Cache hit rate is an observation, never a contract — null counts as null, never as zero.",
          "The worktree is yours to use: demo/spring-backend, tag `base` (original code), tag `head-v1` (deleted @PreAuthorize).",
          "30-second self-check: `python scripts/demo_doctor.py` — six checks, green before you trust it.",
        ],
      },
    },
    {
      title: { zh: "三个不要", en: "The three don'ts" },
      rows: {
        zh: [
          "口头“考虑过了”不能替代红灯。",
          "不要相信 96.5% 的“命中率”——它只是网关 system prompt 的常数，不是你的功劳。",
          "不要“没声音就等于没问题”——检查器崩溃 = UNVERIFIED，绝不是 PASS。",
        ],
        en: [
          "“We considered it” is never evidence; the red gate decides.",
          "The 96.5% hit rate the gateway may report is its own system-prompt constant (#1723) — not your win.",
          "Silence is not a verdict: a crashed checker equals UNVERIFIED, never PASS.",
        ],
      },
    },
  ],
  commands: [
    {
      id: "demo-doctor",
      title: { zh: "30 秒自检：demo doctor", en: "Self-check: demo doctor" },
      body: "python scripts/demo_doctor.py",
    },
    {
      id: "build-chronicle",
      title: { zh: "重建编年史（ledger → JSON）", en: "Rebuild the chronicle" },
      body: "python scripts/build_chronicle.py",
    },
    {
      id: "ledger-four",
      title: { zh: "账本四件套", en: "Ledger four gates" },
      body: "python -m pytest tests/unit/test_ledger_section_ids_are_unique.py tests/unit/test_ledger_section_numbers_are_unique.py tests/unit/test_ledger_evidence_claims_are_true.py tests/unit/test_ledger_queue_pointers_resolve.py -q",
    },
    {
      id: "provider-smoke",
      title: { zh: "真实 LLM smoke（provider → JSON → JUnit）", en: "Real LLM smoke" },
      body: "python scripts/provider_smoke.py",
    },
    {
      id: "sync-portfolio",
      title: { zh: "重建 portfolio 数据（不推送）", en: "Rebuild portfolio data" },
      body: "python scripts/sync_portfolio.py",
    },
  ],
  punchline: {
    zh: "证据先于人。这页只写你见证了什么。",
    en: "Evidence before people. This page is what you carry to the gate.",
  },
  copyLabel: { zh: "复制", en: "Copy" },
  copiedLabel: { zh: "已复制", en: "Copied" },
};
