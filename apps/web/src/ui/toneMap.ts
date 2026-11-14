import { STRINGS, storedLocale } from "../i18n/strings";

const locale = (): "zh" | "en" => storedLocale();

function gloss(key: string): string {
  return STRINGS[locale()][key] ?? key;
}

// Pure tone mapping for severity and result/evidence status pills.
//
// Two independent maps, on purpose: severity (see SEVERITIES below) and
// result/evidence status (RESULT_STATES: PASS/FAIL/UNVERIFIED) must never share
// a tone scale — conflating them once rendered UNVERIFIED with a green PASS
// tone. Every unknown/missing value renders 未知 UNKNOWN in the neutral
// tone; no branch of either map ever returns a green class for anything
// other than a verified pass.

export interface PillSpec {
  /** Suffix for the base .pill class, e.g. "pill-ok". */
  cls: string;
  /** Exact text rendered inside the pill. */
  label: string;
}

const unknownPill = (): PillSpec => ({ cls: "pill-mute", label: gloss("ui.unknown") });

export interface SeveritySpec {
  rank: number;
  cls: string;
  label: string;
  storeable: boolean;
  hint: string;
}

/**
 * The one severity vocabulary in the product, on one line per value so the
 * parity gate (`tests/unit/test_severity_vocabulary_parity.py`) can read it.
 *
 * `storeable` mirrors `findings.severity` / `finding_feedback.severity` — the
 * same MySQL ENUM, which is also the pattern `api/routes/feedback.py` accepts.
 * The two `false` rows are pipeline events that reach the UI through the job
 * summary and can NEVER be stored or voted on: glossing them as 未知 used to
 * hide the most actionable line on the page (a crashing checker) behind the
 * same words used for a typo in a payload.
 */
export const SEVERITIES: Record<string, SeveritySpec> = {
  BLOCKER: { rank: 0, cls: "pill-bad", label: "BLOCKER", storeable: true, hint: "severity.BLOCKER.hint" },
  MAJOR: { rank: 1, cls: "pill-major", label: "MAJOR", storeable: true, hint: "severity.MAJOR.hint" },
  MINOR: { rank: 2, cls: "pill-minor", label: "MINOR", storeable: true, hint: "severity.MINOR.hint" },
  NEEDS_CONFIRMATION: { rank: 3, cls: "pill-unverified", label: "NEEDS_CONFIRMATION", storeable: true, hint: "severity.NEEDS_CONFIRMATION.hint" },
  NONE: { rank: 4, cls: "pill-mute", label: "NONE", storeable: false, hint: "severity.NONE.hint" },
  ERROR: { rank: 5, cls: "pill-mute", label: "ERROR", storeable: false, hint: "severity.ERROR.hint" },
};

/** Severity values the platform can persist and a reviewer can vote on. */
export const SEVERITY_STOREABLE: string[] = Object.keys(SEVERITIES).filter(
  (k) => SEVERITIES[k].storeable
);

/**
 * Severity tone map. Values outside the vocabulary render 未知 in the neutral
 * tone: no branch of this map can ever return a green class.
 */
export function severityPill(severity?: string | null): PillSpec {
  const spec = SEVERITIES[(severity || "").toUpperCase()];
  return spec ? { cls: spec.cls, label: spec.label } : { ...unknownPill() };
}

/**
 * Result / evidence status map: PASS green, FAIL red, UNVERIFIED amber.
 * Anything else renders 未知 in the neutral tone — never green.
 *
 * The keys are the merge rule's own vocabulary
 * (`agent/matrix_policy.py::_RESULT_PRIORITY`), and
 * `tests/unit/test_matrix_result_vocabulary_parity.py` pins both directions.
 * This used to carry a fourth row, `DEGRADED`: no producer in the pipeline ever
 * wrote that word into a matrix result (it belongs to the health scale, which
 * `healthStatusLabel` glosses), so the badge could never appear — and every
 * real "the run was limited" signal went to 未知 instead, where it reads as an
 * unrecognised value rather than a documented state.
 */
export const RESULT_STATES: Record<string, { cls: string; caption: string }> = {
  PASS: { cls: "pill-ok", caption: "result.PASS.caption" },
  FAIL: { cls: "pill-bad", caption: "result.FAIL.caption" },
  UNVERIFIED: { cls: "pill-unverified", caption: "result.UNVERIFIED.caption" },
};

/** What the page says about a result token this vocabulary does not hold. */
const RESULT_UNKNOWN_CAPTION = "result.unknown.caption";

export function resultPill(result?: string | null): PillSpec {
  const token = (result || "").toUpperCase();
  const spec = RESULT_STATES[token];
  return spec ? { cls: spec.cls, label: token } : { ...unknownPill() };
}

/**
 * The one Chinese gloss of a result value, next to its pill. Exported so pages
 * import it instead of writing a second copy of the same vocabulary.
 */
export function resultCaption(result?: string | null): string {
  const key = RESULT_STATES[(result || "").toUpperCase()]?.caption;
  return key ? gloss(key) : gloss(RESULT_UNKNOWN_CAPTION);
}

// 术语对照表：把面向机器的规范枚举/字段翻译成评审者能直接行动的中文说明，
// 同时保留英文原值以便追溯。未知值原样返回，绝不臆造含义。

/** 每个严重级别一句"该怎么办"，用于风险详情页与风险列表悬浮提示。 */
export const SEVERITY_HINT: Record<string, string> = Object.fromEntries(
  Object.entries(SEVERITIES).map(([token, spec]) => [token, spec.hint])
);

/**
 * Sort rank for finding tables: most actionable first, and anything outside
 * the vocabulary sinks to the bottom instead of being re-labelled.
 *
 * This used to be a private map inside JobDetail.tsx listing CRITICAL/HIGH/
 * MEDIUM/LOW/INFO — five severities no backend can produce — while
 * NEEDS_CONFIRMATION, which the findings ENUM really has, was missing and so
 * sorted as unknown.
 */
export function severityRank(severity?: string | null): number {
  const spec = SEVERITIES[(severity || "").toUpperCase()];
  return spec ? spec.rank : 99;
}

export function severityHint(severity?: string | null): string | undefined {
  const key = SEVERITY_HINT[(severity || "").toUpperCase()];
  return key ? gloss(key) : undefined;
}

/**
 * 独立验收（craft 通道）发现的严重程度。
 *
 * 这不是验收平台那条 `findings.severity` ENUM，而是另一套刻度：密钥扫描器报
 * CRITICAL/HIGH/MEDIUM/LOW（agent/security_scanner.py 的规则表），craft 自己的
 * 发现缺省写 BLOCKER/MAJOR。只有 CRITICAL 与 HIGH 计入阻断，所以两套刻度不能混用，
 * 措辞也必须说清"阻断"与"不阻断"。值集由 `craft/severity.py` 声明，
 * `tests/unit/test_accept_severity_parity.py` 双向钉住；扫描器若报出新级别，
 * 这里必须先加词，否则门红。
 */
export const ACCEPT_SEVERITY_CN: Record<string, string> = {
  CRITICAL: "acceptSeverity.CRITICAL",
  HIGH: "acceptSeverity.HIGH",
  MEDIUM: "acceptSeverity.MEDIUM",
  LOW: "acceptSeverity.LOW",
  BLOCKER: "acceptSeverity.BLOCKER",
  MAJOR: "acceptSeverity.MAJOR",
};

/**
 * The only two severities the acceptance gates actually block on — mirrored
 * from `craft/severity.py::BLOCKING_ACCEPT_SEVERITIES` and reconciled by
 * `tests/unit/test_accept_severity_parity.py`, so the console cannot colour a
 * MEDIUM finding red or a CRITICAL one harmless.
 */
export const ACCEPT_SEVERITY_BLOCKING: string[] = ["CRITICAL", "HIGH"];

/** Known kinds are glossed with the token kept; anything else is shown exactly
 * as the scanner wrote it — re-casing an unrecognised value would dress up a
 * guess in the product's own typography. */
export function acceptSeverityLabel(severity?: string | null): string {
  if (!severity) return gloss("acceptSeverity.missing");
  const cn = ACCEPT_SEVERITY_CN[severity.toUpperCase()];
  return cn ? gloss(cn) + " · " + severity.toUpperCase() : severity;
}

export function acceptSeverityTone(severity?: string | null): "bad" | "mute" {
  return ACCEPT_SEVERITY_BLOCKING.includes((severity || "").toUpperCase()) ? "bad" : "mute";
}

/**
 * 证据采集方式的中文说明；未知类型原样透传。
 *
 * The key set is the declared domain: `EVIDENCE_KINDS` in
 * `agent/evidence_kinds.py`, reconciled both ways by
 * `tests/unit/test_evidence_vocabulary_parity.py`. `findings.evidence_type` is a
 * plain VARCHAR(64), so before that declaration existed the UI glossary named
 * `runtime_test` / `static` / `differential` / `review` — kinds no emitter
 * produces — while six kinds the pipeline does write reached a reviewer as raw
 * English.
 */
const EVIDENCE_CN: Record<string, string> = {
  java_source_diff: "evidence.java_source_diff",
  constitution_check: "evidence.constitution_check",
  static_analysis: "evidence.static_analysis",
  // The evidence kind alone says NOTHING about where it ran: a Node repo is
  // executed in the Docker sandbox while an opt-in host run is unsandboxed
  // (#50/#54). The surface is reported in the finding's own description, so
  // this label must not claim either way.
  self_test_diff: "evidence.self_test_diff",
  base_pass_head_fail: "evidence.base_pass_head_fail",
  differential_execution: "evidence.differential_execution",
  probe_differential: "evidence.probe_differential",
  // A crashing checker is a finding, not silence — the label must not read as
  // "checked and clean".
  checker_failed: "evidence.checker_failed",
  // The finding carries no evidence kind at all (capsules and PR comments write
  // "unknown"). Say that plainly rather than dressing it up as a kind of proof.
  unknown: "evidence.unknown",
};

export function evidenceLabel(t?: string | null): string {
  if (!t) return gloss("evidence.empty");
  const cn = EVIDENCE_CN[t.toLowerCase()];
  return cn ? gloss(cn) + " · " + t : t;
}

/** 验收条件"检查方式"（checker_type）的中文说明；未知类型原样透传。 */
const CHECKER_CN: Record<string, string> = {
  http: "checker.http",
  sql: "checker.sql",
  redis: "checker.redis",
  openapi: "checker.openapi",
  rabbitmq: "checker.rabbitmq",
  constitution: "checker.constitution",
  tests: "checker.tests",
  "?": "checker.question",
};

export function checkerLabel(t?: string | null): string {
  if (!t) return gloss("checker.empty");
  const cn = CHECKER_CN[t.toLowerCase()];
  return cn ? gloss(cn) + " · " + t : t;
}

/**
 * 评测（evaluation）逐案判定 verdict 的中文说明。这里的 verdict 与需求覆盖的
 * PASS/FAIL 不是同一套语义：PASS=检出结果与预期一致，PARTIAL=检出但少于预期
 * 数量（命中不全），MISS=预期问题被漏检（假阴性），FALSE_POSITIVE=报出了并不
 * 预期的问题（假阳性），NOT_RUN=流水线在比较前中止、该案例没有跑（既不算
 * 漏检也不算检出，是「没看」而不是「看了没问题」）。未知值原样返回，绝不臆造含义。
 */
const EVAL_VERDICT_CN: Record<string, string> = {
  PASS: "evalVerdict.PASS",
  PARTIAL: "evalVerdict.PARTIAL",
  MISS: "evalVerdict.MISS",
  FALSE_POSITIVE: "evalVerdict.FALSE_POSITIVE",
  NOT_RUN: "evalVerdict.NOT_RUN",
};

export function evalVerdictLabel(v?: string | null): string {
  if (!v) return gloss("evalVerdict.empty");
  const key = EVAL_VERDICT_CN[v.toUpperCase()];
  return key ? gloss(key) : v;
}

/**
 * 整体健康状态（`/api/v1/health` 的 `status`）中文说明。
 *
 * 该字段是英文枚举（ok / degraded），此前在「整体状态」指标卡里被
 * `toUpperCase()` 原样直出为 "OK"/"DEGRADED"，与全站"英文枚举译中文、
 * 原文留在 title 供审计"的约定不一致。已知值译中文；未知值原样透传 ——
 * 绝不臆造一个"正常"的措辞去掩盖真实状态。
 */
const HEALTH_STATUS_CN: Record<string, string> = {
  OK: "healthStatus.OK",
  DEGRADED: "healthStatus.DEGRADED",
};

export function healthStatusLabel(s?: string | null): string {
  if (!s) return gloss("healthStatus.unknown");
  const key = HEALTH_STATUS_CN[s.toUpperCase()];
  return key ? gloss(key) : s;
}

/**
 * 差分实验的"执行面"——仓库自带测试到底跑在容器沙箱里，还是跑在**你的本机上**。
 *
 * 这是安全问题而不是措辞问题：宿主执行会把不受信的 PR 自带测试真的跑起来，
 * 用户有权知道自己有没有被暴露。所以：已知值译中文并**保留原 token**（审计/检索），
 * 未知值原样透传，缺失返回空串（由调用方决定不渲染，而不是显示一个假的"安全"）。
 */
const EXECUTION_SURFACE_CN: Record<string, string> = {
  docker_sandbox: "execSurface.docker_sandbox",
  local_host_no_sandbox: "execSurface.local_host_no_sandbox",
  unconfirmed: "execSurface.unconfirmed",
};

export function executionSurfaceLabel(s?: string | null): string {
  if (!s) return "";
  const cn = EXECUTION_SURFACE_CN[s];
  return cn ? gloss(cn) + " · " + s : s;
}

/**
 * 执行面的语气。沙箱才给 ok；宿主执行与"未确认"都给 warn —— 与后端
 * fail-closed 的判定一致（拿不到完成态运行就不算沙箱），绝不把未知当安全。
 */
export function executionSurfaceTone(s?: string | null): "ok" | "warn" | "mute" {
  if (s === "docker_sandbox") return "ok";
  if (s === "local_host_no_sandbox" || s === "unconfirmed") return "warn";
  return "mute";
}

/**
 * 依赖来源披露（#56/#26）：沙箱自测跑之前，工作区的依赖是怎么来的
 * （离线安装 / 已备好 / 宿主流程）。后端给的是一句描述性英文（不同语言
 * 适配器措辞不同，双侧不一致时还有 "base: …; head: …" 形态），所以这里
 * 按关键词归类出中文短标签，归类不中的原样透传；原始串由调用方放
 * `title` 供审计。缺失返回空串（调用方不渲染，而不是显示一个假来源）。
 */
export function dependencyInstallLabel(s?: string | null): string {
  if (!s) return "";
  // A combined disclosure names both sides ("base: …; head: …") — it cannot
  // be compressed into one label, so it passes through verbatim.
  if (s.includes("; head:") || s.includes("; base:")) return s;
  if (s.includes("offline npm ci")) return gloss("dep.npmOffline");
  if (s.includes("offline pip install")) return gloss("dep.pipOffline");
  if (s.includes("skipped")) return gloss("dep.skipped");
  if (s.includes("not applicable")) return gloss("dep.notApplicable");
  return s;
}

/**
 * 契约 / 验收规则「审核状态」（contract status）中文说明。这套枚举与任务的
 * job status（statusLabel）不是同一套语义：这里是规则评审生命周期
 * APPROVED/PROPOSED/REJECTED/REVOKED。已知值译中文并保留英文枚举原值供追溯；
 * 未知值原样透传，绝不臆造一个"状态未知"去隐藏真实 token —— 那会让评审者
 * 看不出后端究竟返回了什么。
 */
export const CONTRACT_STATUS_CN: Record<string, string> = {
  APPROVED: "contractStatus.APPROVED",
  PROPOSED: "contractStatus.PROPOSED",
  REJECTED: "contractStatus.REJECTED",
  REVOKED: "contractStatus.REVOKED",
};

export function contractStatusLabel(status?: string | null): string {
  const s = (status || "").toUpperCase();
  if (!s) return gloss("contractStatus.empty");
  const cn = CONTRACT_STATUS_CN[s];
  return cn ? gloss(cn) + " · " + s : s;
}

/**
 * 证据矩阵的「差异归因」（attribution）—— 这条不符是改前就有的，还是这次变更
 * 引入的。这是评审者最关心的一栏：值来自 agent/matrix_policy 的
 * head/base/not_attributed/none/unknown 词汇。未知值原样透传。
 */
export const MATRIX_ATTRIBUTION_CN: Record<string, string> = {
  head: "attribution.head",
  base: "attribution.base",
  not_attributed: "attribution.not_attributed",
  none: "attribution.none",
  unknown: "attribution.unknown",
};

export function attributionLabel(attribution?: string | null): string {
  const s = (attribution || "").trim().toLowerCase();
  if (!s) return gloss("attribution.empty");
  const cn = MATRIX_ATTRIBUTION_CN[s];
  return cn ? gloss(cn) + " · " + s : s;
}
