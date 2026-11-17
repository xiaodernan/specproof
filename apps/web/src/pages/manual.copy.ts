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
      title: { zh: "模型怎么帮忙（不是替代你）", en: "What the model does — and doesn't do for you" },
      rows: {
        zh: [
          "「AI 解读」/insight — admin/operator：让模型读这块面板的匿名聚合数，给出下一件事该做什么；不给判决，不替裁判",
          "「深挖现场」/dig — admin/operator：只读问一个问题，三只调查员（explorer/tester/security）并发敲同一把钥匙；不够就说不够",
          "「值班手册」/runbook — admin/operator：告警一响，模型先读仓库（告警规则本体 + 最近 20 提交 + 最新 5 份 evidence）；它只回 CONFIRMED 或 INCONCLUSIVE；判词不下场",
          "「观察舱」/observe — 公开·只读页：『123』即开——本页只有 240 人合成校准群体 + 你浏览器自己的点按轨迹，不含任何其他人；解锁后模型 live 现敲读取本页四项聚合数（后端车道 · 指纹缓存 · 失败时如实报错，永不代写）。",
          "「工单现场」craft × aizzz — 让 LLM 端对端跑一遍 AI 按需求改代码；验收门按你的要求不放行就是不放行",
          "「缓存账目」/usage — 车道 × 协议双轴拆开：direct 看 prefix 缓存，policy 看语义缓存；未上报的就是「—」，绝不是 0",
        ],
        en: [
          "“AI Advice” /insight — admin/operator: ask the model to read this panel's anonymous aggregates and name the next move. No verdict, never a judge.",
          "“The Dig” /dig — admin/operator: ask one question of three readonly investigators (explorer/tester/security); if the model can't tell, it says INSUFFICIENT rather than a fabricated answer.",
          "“Runbook” /runbook — admin/operator: the alert fires, the model reads the repo first (the alert's own rule + last 20 commits + the five newest evidence files); it returns only CONFIRMED or INCONCLUSIVE — never a judged triage.",
          "“Observatory” /observe — public, read-only. Open it without any credential: the door is `123`, it always was. What you see is only a synthetic 240-member calibration cohort plus your own browser's tap strips — never anyone else's. Unlocking fires a live model read of this page's four aggregates only (server-side lane · fingerprint-cached); on failure you get one honest error line, never ghost-written prose.",
          "“SpecCraft × aizzz” — the full chain with the model's hand on the key; the acceptance gate is not the model's to open.",
          "“Usage” /usage — the cache account split by lane × protocol: direct (prefix cache) and policy (semantic cache, off by default); an unreported call shows “—”, never a zero.",
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
