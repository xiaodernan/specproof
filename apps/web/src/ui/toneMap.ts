// Pure tone mapping for severity and result/evidence status pills.
//
// Two independent maps, on purpose: severity (see SEVERITIES below) and
// result/evidence status (PASS/FAIL/UNVERIFIED/DEGRADED) must never share a
// tone scale — conflating them once rendered UNVERIFIED with a green PASS
// tone. Every unknown/missing value renders 未知 UNKNOWN in the neutral
// tone; no branch of either map ever returns a green class for anything
// other than a verified pass.

export interface PillSpec {
  /** Suffix for the base .pill class, e.g. "pill-ok". */
  cls: string;
  /** Exact text rendered inside the pill. */
  label: string;
}

const UNKNOWN: PillSpec = { cls: "pill-mute", label: "未知 UNKNOWN" };

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
  BLOCKER: { rank: 0, cls: "pill-bad", label: "BLOCKER", storeable: true, hint: "阻塞问题——必须修复，会阻止本次合并。" },
  MAJOR: { rank: 1, cls: "pill-major", label: "MAJOR", storeable: true, hint: "重要问题——建议在本次改动内处理。" },
  MINOR: { rank: 2, cls: "pill-minor", label: "MINOR", storeable: true, hint: "轻微问题——可择机改进。" },
  NEEDS_CONFIRMATION: { rank: 3, cls: "pill-unverified", label: "NEEDS_CONFIRMATION", storeable: true, hint: "需要人工确认——机器没有给出足够证据，请你判定接受或打回。" },
  NONE: { rank: 4, cls: "pill-mute", label: "NONE", storeable: false, hint: "不构成风险判定——检查器崩溃或该语言/框架没有检查器，相关验收条件保持未验证（不会因沉默而判为通过）。" },
  ERROR: { rank: 5, cls: "pill-mute", label: "ERROR", storeable: false, hint: "生成反例时出错——这一条没有可执行的证据。" },
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
  return spec ? { cls: spec.cls, label: spec.label } : { ...UNKNOWN };
}

/**
 * Result / evidence status map: PASS green, FAIL red, UNVERIFIED amber,
 * DEGRADED neutral. Anything else renders 未知 in the neutral tone —
 * never green.
 */
export function resultPill(result?: string | null): PillSpec {
  switch ((result || "").toUpperCase()) {
    case "PASS":
      return { cls: "pill-ok", label: "PASS" };
    case "FAIL":
      return { cls: "pill-bad", label: "FAIL" };
    case "UNVERIFIED":
      return { cls: "pill-unverified", label: "UNVERIFIED" };
    case "DEGRADED":
      return { cls: "pill-mute", label: "DEGRADED" };
    default:
      return { ...UNKNOWN };
  }
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
  return SEVERITY_HINT[(severity || "").toUpperCase()];
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
  CRITICAL: "关键（凭证已泄漏，计入验收阻断）",
  HIGH: "高危（凭证类发现，与关键同级计入阻断）",
  MEDIUM: "中危（不阻断验收，交付前应处理）",
  LOW: "低危（信息性发现，不阻断验收）",
  BLOCKER: "阻断级（独立验收自身发现的缺省级别）",
  MAJOR: "重要（契约类发现的缺省级别）",
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
  if (!severity) return "未记录严重程度";
  const cn = ACCEPT_SEVERITY_CN[severity.toUpperCase()];
  return cn ? cn + " · " + severity.toUpperCase() : severity;
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
  java_source_diff: "Java 源码差分（静态比对改动前后的源码，没有执行任何代码）",
  constitution_check: "工程规范检查（constitution 规则命中，没有执行任何代码）",
  static_analysis: "静态分析（源码规则命中，没有执行任何代码）",
  // The evidence kind alone says NOTHING about where it ran: a Node repo is
  // executed in the Docker sandbox while an opt-in host run is unsandboxed
  // (#50/#54). The surface is reported in the finding's own description, so
  // this label must not claim either way.
  self_test_diff: "仓库自带测试差分",
  base_pass_head_fail: "改前通过、改后失败（本次变更引入的失败，实际执行过）",
  differential_execution: "差分执行（改前/改后各执行一次的对比证据）",
  probe_differential: "探针差分（对既有行为下探针再对比，用于确认能否复现）",
  // A crashing checker is a finding, not silence — the label must not read as
  // "checked and clean".
  checker_failed: "检查器崩溃（这一项没有跑出结果，相关验收条件保持未验证，不等于没有问题）",
  // The finding carries no evidence kind at all (capsules and PR comments write
  // "unknown"). Say that plainly rather than dressing it up as a kind of proof.
  unknown: "未记录证据方式（这条风险没有说明它是凭什么得出的）",
};

export function evidenceLabel(t?: string | null): string {
  if (!t) return "—";
  const cn = EVIDENCE_CN[t.toLowerCase()];
  return cn ? cn + " · " + t : t;
}

/** 验收条件"检查方式"（checker_type）的中文说明；未知类型原样透传。 */
const CHECKER_CN: Record<string, string> = {
  http: "HTTP 接口检查",
  sql: "数据库 / SQL 检查",
  redis: "Redis 缓存检查",
  openapi: "OpenAPI 契约检查",
  rabbitmq: "消息队列检查",
  constitution: "工程规范检查",
  tests: "已有测试用例",
};

export function checkerLabel(t?: string | null): string {
  if (!t) return "尚未指定";
  const cn = CHECKER_CN[t.toLowerCase()];
  return cn ? cn + " · " + t : t;
}

/**
 * 评测（evaluation）逐案判定 verdict 的中文说明。这里的 verdict 与需求覆盖的
 * PASS/FAIL 不是同一套语义：PASS=检出结果与预期一致，MISS=预期问题被漏检
 * （假阴性），FALSE_POSITIVE=报出了并不预期的问题（假阳性）。未知值原样返回，
 * 绝不臆造含义。
 */
const EVAL_VERDICT_CN: Record<string, string> = {
  PASS: "判定正确",
  MISS: "漏检（未检出预期问题）",
  FALSE_POSITIVE: "误报（检出非预期问题）",
};

export function evalVerdictLabel(v?: string | null): string {
  if (!v) return "—";
  return EVAL_VERDICT_CN[v.toUpperCase()] ?? v;
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
  OK: "正常",
  DEGRADED: "降级",
};

export function healthStatusLabel(s?: string | null): string {
  if (!s) return "未知";
  return HEALTH_STATUS_CN[s.toUpperCase()] ?? s;
}

/**
 * 差分实验的"执行面"——仓库自带测试到底跑在容器沙箱里，还是跑在**你的本机上**。
 *
 * 这是安全问题而不是措辞问题：宿主执行会把不受信的 PR 自带测试真的跑起来，
 * 用户有权知道自己有没有被暴露。所以：已知值译中文并**保留原 token**（审计/检索），
 * 未知值原样透传，缺失返回空串（由调用方决定不渲染，而不是显示一个假的"安全"）。
 */
const EXECUTION_SURFACE_CN: Record<string, string> = {
  docker_sandbox: "容器沙箱执行",
  local_host_no_sandbox: "本机执行 · 无沙箱",
  unconfirmed: "执行面未确认",
};

export function executionSurfaceLabel(s?: string | null): string {
  if (!s) return "";
  const cn = EXECUTION_SURFACE_CN[s];
  return cn ? cn + " · " + s : s;
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
 * 契约 / 验收规则「审核状态」（contract status）中文说明。这套枚举与任务的
 * job status（statusLabel）不是同一套语义：这里是规则评审生命周期
 * APPROVED/PROPOSED/REJECTED/REVOKED。已知值译中文并保留英文枚举原值供追溯；
 * 未知值原样透传，绝不臆造一个"状态未知"去隐藏真实 token —— 那会让评审者
 * 看不出后端究竟返回了什么。
 */
export const CONTRACT_STATUS_CN: Record<string, string> = {
  APPROVED: "已批准",
  PROPOSED: "待审核",
  REJECTED: "已驳回",
  REVOKED: "已撤销",
};

export function contractStatusLabel(status?: string | null): string {
  const s = (status || "").toUpperCase();
  if (!s) return "—";
  const cn = CONTRACT_STATUS_CN[s];
  return cn ? cn + " · " + s : s;
}

/**
 * 证据矩阵的「差异归因」（attribution）—— 这条不符是改前就有的，还是这次变更
 * 引入的。这是评审者最关心的一栏：值来自 agent/matrix_policy 的
 * head/base/not_attributed/none/unknown 词汇。未知值原样透传。
 */
export const MATRIX_ATTRIBUTION_CN: Record<string, string> = {
  head: "本次变更引入",
  base: "改前既有",
  not_attributed: "无法归因",
  none: "无需归因",
  unknown: "归因未知",
};

export function attributionLabel(attribution?: string | null): string {
  const s = (attribution || "").trim().toLowerCase();
  if (!s) return "—";
  const cn = MATRIX_ATTRIBUTION_CN[s];
  return cn ? cn + " · " + s : s;
}
