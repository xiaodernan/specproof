import { HealthData } from "../api";

// §14.4 honest five-category health: every category is derived from what the
// payload actually carries. A missing field renders as 未知 UNKNOWN — never
// a guessed status, never one big green check hiding defects.

export type HealthCategoryState = "ok" | "warn" | "bad" | "unknown";

export interface HealthCategory {
  key: "service" | "deps" | "capabilities" | "degraded" | "data";
  label: string;
  state: HealthCategoryState;
  value: string;
  detail: string;
  // Raw payload field name behind a friendly detail line, kept inspectable via
  // the title tooltip so softening the wording never hides what the API sent.
  detailTitle?: string;
}

const UNKNOWN_PILL = "未知 UNKNOWN";

export function buildHealthCategories(
  data: HealthData | null,
  error: Error | string | null
): HealthCategory[] {
  const checks =
    data && data.checks && typeof data.checks === "object" ? data.checks : null;
  const entries = checks ? Object.entries(checks) : [];
  const okCount = entries.filter(([, c]) => c && c.ok === true).length;
  const downNames = entries
    .filter(([, c]) => c && c.ok === false)
    .map(([name]) => name);

  // 1. 服务可达 — derived from the health call itself, never guessed.
  const service: HealthCategory = data
    ? {
        key: "service",
        label: "服务可达 Service reachable",
        state: "ok",
        value: "可达 REACHABLE",
        detail: "健康检查已成功返回 — 服务进程在线。",
        detailTitle: "GET /api/v1/health",
      }
    : error
    ? {
        key: "service",
        label: "服务可达 Service reachable",
        state: "bad",
        value: "不可达 UNREACHABLE",
        detail: typeof error === "string" ? error : error.message,
      }
    : {
        key: "service",
        label: "服务可达 Service reachable",
        state: "unknown",
        value: UNKNOWN_PILL,
        detail: "尚未完成首次探测。",
      };

  // 2. 依赖可达 — aggregated from the checks map; absent map = 未知.
  const deps: HealthCategory =
    checks && entries.length > 0
      ? okCount === entries.length
        ? {
            key: "deps",
            label: "依赖可达 Dependencies",
            state: "ok",
            value: okCount + " / " + entries.length + " 可达",
            detail:
              entries
                .map(([name, c]) => name + (c && c.ok === true ? " OK" : " DOWN"))
                .join(" · ") +
              " — 依赖逐项探测, 失败显式呈现。",
          }
        : {
            key: "deps",
            label: "依赖可达 Dependencies",
            state: okCount === 0 ? "bad" : "warn",
            value: okCount + " / " + entries.length + " 可达",
            detail:
              "不可达: " +
              (downNames.length > 0 ? downNames.join(", ") : "无") +
              " — 相关数据会明确标记为降级，绝不伪造。",
            detailTitle: "degraded",
          }
      : {
          key: "deps",
          label: "依赖可达 Dependencies",
          state: "unknown",
          value: UNKNOWN_PILL,
          detail: "健康检查未返回任何依赖探测结果 — 不猜测状态。",
          detailTitle: "checks 字段缺失",
        };

  // 3. 能力完整度 — only reported when the payload carries a capability
  //    inventory; the current /health contract does not, so this is 未知.
  const caps = data ? data.capabilities : undefined;
  const capabilities: HealthCategory = Array.isArray(caps)
    ? caps.length > 0
      ? {
          key: "capabilities",
          label: "能力完整度 Capabilities",
          state: "ok",
          value: caps.length + " 项已上报",
          detail:
            "载荷上报能力清单: " +
            caps.map((c) => String(c)).join(", ") +
            "。",
        }
      : {
          key: "capabilities",
          label: "能力完整度 Capabilities",
          state: "unknown",
          value: UNKNOWN_PILL,
          detail: "能力清单为空 — 完整度无法判断。",
        }
    : caps && typeof caps === "object"
    ? {
        key: "capabilities",
        label: "能力完整度 Capabilities",
        state: "ok",
        value: Object.keys(caps).length + " 项已上报",
        detail:
          "载荷上报能力清单: " + Object.keys(caps).join(", ") + "。",
      }
    : {
        key: "capabilities",
        label: "能力完整度 Capabilities",
        state: "unknown",
        value: UNKNOWN_PILL,
        detail: "健康检查未提供能力清单 — 完整度无法判断。",
        detailTitle: "capabilities 字段缺失",
      };

  // 4. 当前降级 — reported only when the degraded flag is actually present.
  const degraded: HealthCategory =
    typeof data?.degraded === "boolean"
      ? data.degraded
        ? {
            key: "degraded",
            label: "当前降级 Degraded",
            state: "warn",
            value: "降级中 DEGRADED",
            detail:
              Array.isArray(data.degraded_reasons) &&
              data.degraded_reasons.length > 0
                ? data.degraded_reasons.join("; ")
                : "部分依赖不可用 — 相关数据会以空结果明确降级，绝不伪造。",
          }
        : {
            key: "degraded",
            label: "当前降级 Degraded",
            state: "ok",
            value: "正常 NORMAL",
            detail: "服务未处于降级状态。",
            detailTitle: "degraded: false",
          }
      : {
          key: "degraded",
          label: "当前降级 Degraded",
          state: "unknown",
          value: UNKNOWN_PILL,
          detail: "健康检查未返回降级状态 — 不猜测。",
          detailTitle: "degraded 字段缺失",
        };

  // 5. 数据可查询 — derived from the MySQL probe (the data store of record),
  //    and clearly labeled as a derivation, not an independent check.
  const mysql = checks ? checks.mysql : undefined;
  const queryable: HealthCategory = !mysql
    ? {
        key: "data",
        label: "数据可查询 Data queryable",
        state: "unknown",
        value: UNKNOWN_PILL,
        detail: "暂无主数据库的探测结果 — 数据能否查询无法判断。",
        detailTitle: "checks.mysql 缺失",
      }
    : mysql.ok === true
    ? {
        key: "data",
        label: "数据可查询 Data queryable",
        state: "ok",
        value: "可查询 QUERYABLE",
        detail:
          "MySQL (数据主库) 探测通过" +
          (typeof mysql.latency_ms === "number"
            ? " · " + mysql.latency_ms + " ms"
            : "") +
          "。由 mysql 探测推导。",
      }
    : {
        key: "data",
        label: "数据可查询 Data queryable",
        state: "bad",
        value: "不可查询 NOT QUERYABLE",
        detail:
          "MySQL (数据主库) 探测失败" +
          (mysql.error ? ": " + mysql.error : "") +
          " — 数据端点可能降级。",
      };

  return [service, deps, capabilities, degraded, queryable];
}
