import type { Locale } from "../i18n/strings";

/**
 * The Verify Drill — twelve questions, every one anchored to a real file,
 * a real gate or a real ledger entry in this repository. Nothing here is
 * trivia; every wrong answer is a door into the record.
 *
 * `answer` is the index of the correct choice. `teach` fires after the lock,
 * right or wrong, so the drill always pays out.
 */

export interface DrillQuestion {
  id: string;
  prompt: Record<Locale, string>;
  choices: Record<Locale, string[]>;
  answer: number;
  teach: Record<Locale, string>;
}

export const DRILL_QUESTIONS: DrillQuestion[] = [
  {
    id: "base-pass-head-fail",
    prompt: {
      zh: "`base_pass_head_fail` 这个 evidence_type 的含义是？",
      en: "What does the evidence_type `base_pass_head_fail` mean?",
    },
    choices: {
      zh: ["基准版本通过验收，待检查版本失败——变更引入的回归", "基准版本失败，待检查版本通过——修复被确认", "两个版本都没有跑过"],
      en: ["The base revision passes, the head revision fails — a regression introduced by the change", "The base fails, the head passes — the fix is confirmed", "Neither revision was executed"],
    },
    answer: 0,
    teach: {
      zh: "agent/evidence_kinds.py 的声明域；见证被删掉的那行 @PreAuthorize。锚点：demo/spring-backend tag head-v1。",
      en: "Declared in agent/evidence_kinds.py; witnesses the removed @PreAuthorize line. Anchor: demo/spring-backend tag head-v1.",
    },
  },
  {
    id: "cached-tokens-null",
    prompt: {
      zh: "网关返回 `cached_tokens: null`（比如 wkapi.pro），Unit test 面板应显示什么？",
      en: "The gateway returns `cached_tokens: null` (e.g. wkapi.pro). What should the usage panel show?",
    },
    choices: {
      zh: ["0%，缓存没有命中", "「—」并断开折线——未上报绝不能补 0", "404 错误"],
      en: ["0% — the cache clearly did not hit", "“—” and a broken line — an unreported value is never zero-filled", "A 404 error"],
    },
    answer: 1,
    teach: {
      zh: "#1646/#1704：宁可断档也不画假点。账本 #1723 进一步实测：网关对超短 prompt 不做缓存上报。",
      en: "#1646/#1704 — a gap, never a fabricated point. Ledger #1723 measured it further: the gateway never reports cache use on short prompts.",
    },
  },
  {
    id: "red-light",
    prompt: {
      zh: "门禁红了，但合并前大家都说「考虑过」。这算不算证据？",
      en: "The gate is red, but everyone 「considered」 it before merging. Is that evidence?",
    },
    choices: {
      zh: ["算——集体判断可以替代机器", "不算——门禁红就是门禁红，考虑过不是一个状态", "算一半，取决于谁考虑的"],
      en: ["Yes — collective judgement outranks the machine", "No — a red gate is a red gate; “considering” is not a verdict state", "Half, depending on who considered it"],
    },
    answer: 1,
    teach: {
      zh: "卷十四·14.3「门禁不是口号」、14.4「红也被留下」、14.13「连接可疑的手」。铁律不给口头禅开后门。",
      en: "Vol. XIV · 14.3 — “the gate is not a slogan”; 14.4 — red is kept; 14.13 — a hand on the button stays suspect. Iron law grants no oral exemptions.",
    },
  },
  {
    id: "unverified",
    prompt: {
      zh: "UNVERIFIED 代表什么？",
      en: "What does UNVERIFIED represent?",
    },
    choices: {
      zh: ["检查了一遍没问题", "证据不足——既不算通过也不算失败", "代码有 bug"],
      en: ["We checked, it is fine", "Insufficient evidence — neither pass nor fail", "The code is buggy"],
    },
    answer: 1,
    teach: {
      zh: "checker_failed（检查器崩溃）就是 UNVERIFIED 的原型：相关验收条件保持未验证，绝不等同于「没有问题」。",
      en: "checker_failed (a crashing checker) is the prototype: the related acceptance criteria stay UNVERIFIED — never the same as “no problem”.",
    },
  },
  {
    id: "no-llm",
    prompt: {
      zh: "`verify --no-llm` 跑的是什么？",
      en: "What does `verify --no-llm` execute?",
    },
    choices: {
      zh: ["不跑验证，直接生成报告", "只跑确定性管线（契约/差分/矩阵），不调模型——结论仍然成立", "用旧结果冒充新结果"],
      en: ["No verification runs; it just drafts a report", "The deterministic pipeline (contracts / differential / matrix) with no model calls — the verdict still holds", "Yesterday's result presented as fresh"],
    },
    answer: 1,
    teach: {
      zh: "CLI 的离线模式：deterministic 管线 + base_pass_head_fail，模型只在反例生成与评测隔离层使用。诚实边界写在 USER_GUIDE §6。",
      en: "The CLI's offline lane: the deterministic pipeline + base_pass_head_fail; the model only powers counterexample generation and eval isolation. See USER_GUIDE §6 honest limits.",
    },
  },
  {
    id: "streaming-lane",
    prompt: {
      zh: "为什么真调 LLM 时要 `stream=True + include_usage=True`？",
      en: "Why real LLM calls go down `stream=True + include_usage=True`?",
    },
    choices: {
      zh: ["更快", "否则网关通常不报 usage / cached_tokens，缓存计数永远落不到账本里", "为了让回答看起来逐字打出"],
      en: ["It is faster", "Otherwise the gateway usually reports no usage / cached_tokens — the cache can never enter the ledger", "To make the reply look typed"],
    },
    answer: 1,
    teach: {
      zh: "#1679/#1681/#1719：不带流+usage，缓存到底省了多少 token 只取决于「网关今天的心情」。流式不是美学，是考核。",
      en: "#1679/#1681/#1719: without the stream lane, how much the cache saved depends on “the gateway's mood that day”. Streaming is not aesthetics; it is measurement.",
    },
  },
  {
    id: "hit-rate-truth",
    prompt: {
      zh: "wkapi.pro 报出的 ~96.5% 命中率后来被实测证明是？",
      en: "What did measurement later prove the ~96.5% wkapi.pro hit rate to be?",
    },
    choices: {
      zh: ["我们的提示词被缓存了", "网关静态 system prompt 的 4224 常数——是网关的计费表象，不是我们 prompt 的命中", "证明稳定前缀无效"],
      en: ["Our prompts were cached", "The gateway's static system-prompt constant (4224 tokens) — gateway accounting, not our prompt's hits", "Proof that the stable prefix is useless"],
    },
    answer: 1,
    teach: {
      zh: "#1723：超短 prompt → cached=null；超长工程 prompt → 恒定 4224。命中率降级为观测指标，不再是契约。",
      en: "#1723: tiny prompts → cached=null; long engineering prompts → constant 4224. The hit rate is an observational metric, never a contract.",
    },
  },
  {
    id: "matrix-cell",
    prompt: {
      zh: "需求覆盖矩阵的一个单元格代表什么？",
      en: "What does one cell of the requirement-coverage matrix represent?",
    },
    choices: {
      zh: ["一个 contract_id × 一个 evidence_type 的定案", "一次 CI 运行", "一段 commit 说明"],
      en: ["One contract_id × one evidence_type, and its verdict", "One CI run", "One commit message"],
    },
    answer: 0,
    teach: {
      zh: "Matrix 页每格 PASS / FAIL / UNVERIFIED 之一，由 agent/matrix_policy 合并；底-底文件可追溯到具体 job。",
      en: "Each cell is PASS / FAIL / UNVERIFIED, merged by agent/matrix_policy — and every cell traces back to a job you can open.",
    },
  },
  {
    id: "blocker",
    prompt: {
      zh: "BLOCKER 发现出现后，合并能不能靠「人工 override」继续？",
      en: "A BLOCKER finding lands. Can the merge go through on “manual override”?",
    },
    choices: {
      zh: ["可以，人工权限高于一切", "不可以——override 只能基于新证据，人压不住红灯，证据先于人", "可以，仅限审查者本人"],
      en: ["Yes — humans outrank everything", "No — overrides ride on new evidence; a human hand does not press out the red light. Evidence before people", "Yes — reviewer's own call"],
    },
    answer: 1,
    teach: {
      zh: "卷十四·14.13「连接可疑的手」：接受意味着承担；系统不继承盲目，也不喂幻想。证据先于人，人负责证物。",
      en: "Vol. XIV · 14.13 — a hand on the button stays suspect: accepting means owning the consequence; the system inherits neither blindness nor wishes. Evidence before people; people are responsible for the evidence.",
    },
  },
  {
    id: "checker-crash",
    prompt: {
      zh: "检查器本身崩溃（checker_failed）时，相关的验收条件应显示什么状态？",
      en: "When the checker itself crashed (checker_failed), what state should the related acceptance criteria show?",
    },
    choices: {
      zh: ["PASS——没报错就算过了", "UNVERIFIED——相关条件保持未验证，检查器崩溃不等于没有问题", "BLOCKED——自动阻断合并"],
      en: ["PASS — silence counts", "UNVERIFIED — the criteria stay unverified; a crashing checker is not “no problem”", "BLOCKED — the merge is auto-blocked"],
    },
    answer: 1,
    teach: {
      zh: "agent/nodes：checker 崩溃是一条 findings，不是沉默——UNKNOWN 语义不可伪造，这也是 UNVERIFIED 存在的意义。",
      en: "agent/nodes: a crashing checker is a finding, not silence — UNKNOWN is never faked, and this is why UNVERIFIED exists.",
    },
  },
  {
    id: "ledger",
    prompt: {
      zh: "账本里写错了一笔，正确的做法是？",
      en: "A ledger entry turns out wrong. The correct move is…",
    },
    choices: {
      zh: ["删除重写", "追加一笔更正，旧账不动", "悄悄改日期"],
      en: ["Delete and rewrite it", "Append a correction entry — the old line stays", "Quietly amend the date"],
    },
    answer: 1,
    teach: {
      zh: "append-only：#1690 至今没有删掉任何一条。失败也被留下；错误的更正是新的条目，不是返工。",
      en: "append-only: not one entry has been deleted since #1690. Failures stay; correcting a mistake means writing the next entry, never re-writing the page.",
    },
  },
  {
    id: "headline",
    prompt: {
      zh: "SpecProof 报告里的 Headline VERDICT 由谁决定？",
      en: "Who decides the headline VERDICT in a SpecProof report?",
    },
    choices: {
      zh: ["写这份报告的人", "全市场的 CI 平均水平", "shared policy（evaluate_acceptance / matrix merge）——确定性代码，可复现"],
      en: ["The report's author", "The global average of CI behaviour", "The shared policy (evaluate_acceptance / matrix merge) — deterministic code, replayable"],
    },
    answer: 2,
    teach: {
      zh: "evidence/verdict.py + agent/matrix_policy.py：命运不属于文书员，文书员只誊抄已经落地的定案。",
      en: "evidence/verdict.py + agent/matrix_policy.py: the fate is not the scribe's — the scribe only copies the verdict that already landed.",
    },
  },
];

export const DRILL_TOTAL = DRILL_QUESTIONS.length;
