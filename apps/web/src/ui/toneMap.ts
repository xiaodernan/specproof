// Pure tone mapping for severity and result/evidence status pills.
//
// Two independent maps, on purpose: severity (BLOCKER/MAJOR/MINOR/INFO) and
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

/**
 * Severity tone map: BLOCKER red, MAJOR orange, MINOR yellow, INFO neutral.
 * Anything else (absent, empty, unrecognized) is 未知 in the neutral tone.
 */
export function severityPill(severity?: string | null): PillSpec {
  switch ((severity || "").toUpperCase()) {
    case "BLOCKER":
      return { cls: "pill-bad", label: "BLOCKER" };
    case "MAJOR":
      return { cls: "pill-major", label: "MAJOR" };
    case "MINOR":
      return { cls: "pill-minor", label: "MINOR" };
    case "INFO":
      return { cls: "pill-mute", label: "INFO" };
    default:
      return { ...UNKNOWN };
  }
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
export const SEVERITY_HINT: Record<string, string> = {
  BLOCKER: "阻塞问题——必须修复，会阻止本次合并。",
  MAJOR: "重要问题——建议在本次改动内处理。",
  MINOR: "轻微问题——可择机改进。",
  INFO: "提示信息——供参考，一般无需处理。",
};

export function severityHint(severity?: string | null): string | undefined {
  return SEVERITY_HINT[(severity || "").toUpperCase()];
}

/** 证据采集方式的中文说明；未知类型原样透传。 */
const EVIDENCE_CN: Record<string, string> = {
  runtime_test: "运行时测试（实际执行验证）",
  static: "静态分析",
  static_analysis: "静态分析",
  differential: "差分对比（改动前后行为）",
  // Repo self-test differential. The evidence kind alone says NOTHING about
  // where it ran: a Node repo is executed in the Docker sandbox while an
  // opt-in host run is unsandboxed (#50/#54). The surface is reported in the
  // finding's own description sentence; the API does not yet carry it as a
  // field, so this label must not claim either way.
  self_test_diff: "仓库自带测试差分",
  review: "人工评审",
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
