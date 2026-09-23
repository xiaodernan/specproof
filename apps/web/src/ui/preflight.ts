// 环境预检（preflight）结果的展示层翻译。
//
// 后端 agent/preflight.py 以稳定的英文 check id 与 status 上报探测结果，
// 这里只做展示翻译：未收录的 id / 状态原样返回真实值，绝不臆造含义。
// 与 stages.ts / toneMap.ts 保持同一约定：英文是契约，中文是界面。

export const PREFLIGHT_CHECK_LABELS: Record<string, string> = {
  disk_space: "磁盘空间",
  java: "Java 运行时",
  javac: "Java 编译器",
  JAVA_HOME: "JAVA_HOME 环境变量",
  maven_wrapper: "Maven 构建器",
  node: "Node.js 运行时",
  package_manager: "包管理器",
  node_test_script: "测试脚本",
  python: "Python 解释器",
  pytest: "pytest 测试框架",
  go: "Go 工具链",
};

export const PREFLIGHT_STATUS_LABELS: Record<string, string> = {
  PASS: "正常",
  FAIL: "不满足",
  WARN: "提醒",
};

/** 探测项中文名；未知 id 原样透传，便于排查而非被猜测掩盖。 */
export function preflightCheckLabel(id: string | undefined | null): string {
  if (!id) return "—";
  return PREFLIGHT_CHECK_LABELS[id] || id;
}

/** 探测状态中文名；未知状态原样透传。 */
export function preflightStatusLabel(status: string | undefined | null): string {
  if (!status) return "—";
  return PREFLIGHT_STATUS_LABELS[status] || status;
}

export const PREFLIGHT_LANGUAGE_LABELS: Record<string, string> = {
  java: "Java / Maven",
  node: "JavaScript / TypeScript",
  python: "Python",
  go: "Go",
  unknown: "未识别",
};

/** 识别出的项目语言；未识别时明确说"未识别"，不说"通用"。 */
export function preflightLanguageLabel(lang: string | undefined | null): string {
  if (!lang) return "—";
  return PREFLIGHT_LANGUAGE_LABELS[lang] || lang;
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
      return "输入校验未通过，环境预检已跳过。";
    case "probe_error":
      return "环境探测自身异常，已跳过预检并继续验证。";
    case "disabled_by_SPECPROOF_PREFLIGHT":
      return "已通过环境变量关闭环境预检。";
    default:
      return p?.not_run ? `环境预检未执行（${p.not_run}）。` : "";
  }
}

// 预检阻断原因 → 可执行的中文行动卡。匹配后端 agent/preflight.py 的
// 英文文案；未命中的串原样透传，不臆造下一步。
const PREFLIGHT_ERROR_HINTS: Array<[RegExp, string]> = [
  [/Java not found/i,
    "执行环境未安装 Java。请安装 Eclipse Temurin JDK 21（https://adoptium.net/）并设置 JAVA_HOME，然后重新验证。"],
  [/JDK 21 required/i,
    "已安装的 JDK 版本低于 21。请安装 JDK 21 并让 java / javac 指向它（设置 JAVA_HOME 或调整 PATH），然后重新验证。"],
  [/javac not found/i,
    "只找到了 Java 运行环境（JRE），缺少编译器 javac，项目无法编译。请安装完整 JDK 21 而非 JRE。"],
  [/(No )?Maven Wrapper found|maven-wrapper\.properties/i,
    "项目缺少可用的 Maven 构建器：既没有 mvnw / mvnw.cmd，PATH 上也找不到 mvn。请在项目中提交 Maven Wrapper"
    + "（mvn -N wrapper:wrapper），或在执行环境安装 Maven 后重新验证。"],
  [/Node\.js not found/i,
    "执行环境未安装 Node.js。请安装 Node.js 18+（https://nodejs.org/）后重新验证。"],
  [/No Node package manager found/i,
    "执行环境找不到 npm / pnpm / yarn，项目的测试脚本无法运行。请安装 Node.js（自带 npm）后重新验证。"],
  [/No working Python interpreter/i,
    "执行环境找不到可用的 Python 解释器。请安装 Python 3.9+ 后重新验证。"],
  [/Go toolchain not found/i,
    "执行环境未安装 Go 工具链。请安装 Go（https://go.dev/dl/）后重新验证。"],
  [/Low disk space/i,
    "执行环境磁盘空间不足（少于 1 GB）。依赖与构建产物无法写入，请清理磁盘后重新验证。"],
];

/** 把预检阻断原因翻译成中文行动卡；未识别的串原样透传。 */
export function describePreflightError(raw: string): string {
  const body = raw.replace(/^Preflight:\s*/, "");
  for (const [pattern, hint] of PREFLIGHT_ERROR_HINTS) {
    if (pattern.test(body)) return hint;
  }
  return body;
}
