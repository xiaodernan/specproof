import { STRINGS, storedLocale } from "../i18n/strings";

function gloss(key: string): string {
  return STRINGS[storedLocale()][key] ?? key;
}

// 环境预检（preflight）结果的展示层翻译。
//
// 后端 agent/preflight.py 以稳定的英文 check id 与 status 上报探测结果，
// 这里只做展示翻译：未收录的 id / 状态原样返回真实值，绝不臆造含义。
// 与 stages.ts / toneMap.ts 保持同一约定：英文是契约，中文是界面。

export const PREFLIGHT_CHECK_LABELS: Record<string, string> = {
  disk_space: "preflightCheck.disk_space",
  java: "preflightCheck.java",
  javac: "preflightCheck.javac",
  JAVA_HOME: "preflightCheck.JAVA_HOME",
  maven_wrapper: "preflightCheck.maven_wrapper",
  node: "preflightCheck.node",
  package_manager: "preflightCheck.package_manager",
  node_test_script: "preflightCheck.node_test_script",
  python: "preflightCheck.python",
  pytest: "preflightCheck.pytest",
  go: "preflightCheck.go",
};

export const PREFLIGHT_STATUS_LABELS: Record<string, string> = {
  PASS: "preflightStatus.PASS",
  FAIL: "preflightStatus.FAIL",
  WARN: "preflightStatus.WARN",
};

/** 探测项中文名；未知 id 原样透传，便于排查而非被猜测掩盖。 */
export function preflightCheckLabel(id: string | undefined | null): string {
  if (!id) return gloss("preflight.missing");
  const cn = PREFLIGHT_CHECK_LABELS[id];
  return cn ? gloss(cn) : id;
}

/** 探测状态中文名；未知状态原样透传。 */
export function preflightStatusLabel(status: string | undefined | null): string {
  if (!status) return gloss("preflight.missing");
  const cn = PREFLIGHT_STATUS_LABELS[status];
  return cn ? gloss(cn) : status;
}

export const PREFLIGHT_LANGUAGE_LABELS: Record<string, string> = {
  java: "Java / Maven",
  node: "JavaScript / TypeScript",
  python: "Python",
  go: "Go",
  unknown: "preflightLanguage.unknown",
};

/** 识别出的项目语言；未识别时明确说"未识别"，不说"通用"。 */
export function preflightLanguageLabel(lang: string | undefined | null): string {
  if (!lang) return gloss("preflight.missing");
  const cn = PREFLIGHT_LANGUAGE_LABELS[lang];
  return cn ? gloss(cn) : lang;
}

export interface PreflightCheck {
  check?: string;
  status?: string;
  detail?: string;
}

export interface PreflightResult {
  passed?: boolean;
  language?: string;
  checks?: PreflightCheck[];
  errors?: string[];
  warnings?: string[];
  skipped?: string[];
  not_run?: string;
}

/** 预检未真正执行的原因（后端写入 not_run 字段）。 */
export function preflightNotRunReason(p: PreflightResult | null | undefined): string {
  switch (p?.not_run) {
    case "upstream_errors":
      return gloss("preflightNotRun.upstream_errors");
    case "probe_error":
      return gloss("preflightNotRun.probe_error");
    case "disabled_by_SPECPROOF_PREFLIGHT":
      return gloss("preflightNotRun.disabled_by_SPECPROOF_PREFLIGHT");
    default:
      return p?.not_run ? gloss("preflightNotRun.generic").replace("{reason}", p.not_run) : "";
  }
}

// 预检阻断原因 → 可执行的中文行动卡。匹配后端 agent/preflight.py 的
// 英文文案；未命中的串原样透传，不臆造下一步。
const PREFLIGHT_ERROR_HINTS: Array<[RegExp, string]> = [
  [/Java not found/i,
    "preflightBlocker.javaMissing"],
  [/JDK 21 required/i,
    "preflightBlocker.jdk21Required"],
  [/javac not found/i,
    "preflightBlocker.javacMissing"],
  [/(No )?Maven Wrapper found|maven-wrapper\.properties/i,
    "preflightBlocker.mavenWrapperMissing"],
  [/Node\.js not found/i,
    "preflightBlocker.nodeMissing"],
  [/No Node package manager found/i,
    "preflightBlocker.pmMissing"],
  [/No working Python interpreter/i,
    "preflightBlocker.pythonMissing"],
  [/Go toolchain not found/i,
    "preflightBlocker.goMissing"],
  [/Low disk space/i,
    "preflightBlocker.diskLow"],
];

/** 把预检阻断原因翻译成中文行动卡；未识别的串原样透传。 */
export function describePreflightError(raw: string): string {
  const body = raw.replace(/^Preflight:\s*/, "");
  for (const [pattern, hint] of PREFLIGHT_ERROR_HINTS) {
    if (pattern.test(body)) return STRINGS[storedLocale()][hint] ?? hint;
  }
  return body;
}
