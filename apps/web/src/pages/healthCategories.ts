import { HealthData } from "../api";
import type { Locale } from "../i18n/strings";

// #14.4 honest five-category health: every category is derived from what the
// payload actually carries. A missing field renders as UNKNOWN — never
// a guessed status, never one big green check hiding defects.
// Every user-facing sentence is localised; the field names stay untouched.

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

const COPY = {
  zh: {
    unknownPill: "未知 UNKNOWN",
    serviceLabel: "服务可达 Service reachable",
    depsLabel: "依赖可达 Dependencies",
    capsLabel: "能力清单 Capabilities",
    degradedLabel: "当前降级 Degraded",
    dataLabel: "数据可查询 Data queryable",
    reachable: "可达 REACHABLE",
    unreachable: "不可达 UNREACHABLE",
    reachableAll: (n: number, total: number) => `${n} / ${total} 可达`,
    depsOkDetail: (list: string) => `${list} — 全部通过；失败项会逐个点亮。`,
    depsBadDetail: (down: string) => `不可达: ${down} — 记录如下，确认是否是读取完整库的问题。`,
    depsNone: "无",
    depsNoData: "服务未返回任何依赖探针 — 未知状态。",
    serviceOkDetail: "服务端口已经连通 — 证成书可达。",
    serviceUnknownDetail: "还未拿到服务状态。",
    capsCount: (n: number) => `${n} 项已上报`,
    capsDetail: (list: string) => `声明的能力清单: ${list}。`,
    capsEmpty: "清单为空 — 没法判断。",
    capsAbsent: "服务端未提供清单 — 没法判断。",
    degradedDegraded: "服务处于受限模式 — 记录如下可能不完整，确认是否是读取完整库的问题。",
    degradedNormal: "服务未报告降级状态。",
    degradedUnknown: "服务端未报告降级状态 — 未知。",
    normalValue: "正常 NORMAL",
    degradedValue: "降级中 DEGRADED",
    dataOk: "可查询 QUERYABLE",
    dataBad: "不可查询 NOT QUERYABLE",
    dataUnknown: "服务端未返回数据探针 — 没法判断数据是否可查。",
    dataOkDetail: (ms?: number) => `MySQL（控制面）探针通过${typeof ms === "number" ? ` — ${ms} ms` : ""}。mysql 探针成功。`,
    dataBadDetail: (err?: string | null) => `MySQL（控制面）探针失败${err ? `: ${err}` : ""} — 数据不能当作全量库使用。`,
  },
  en: {
    unknownPill: "UNKNOWN",
    serviceLabel: "Service reachable",
    depsLabel: "Dependencies",
    capsLabel: "Capabilities",
    degradedLabel: "Degraded",
    dataLabel: "Data queryable",
    reachable: "REACHABLE",
    unreachable: "UNREACHABLE",
    reachableAll: (n: number, total: number) => `${n} / ${total} reachable`,
    depsOkDetail: (list: string) => `${list} — all green; failures light up individually.`,
    depsBadDetail: (down: string) => `Down: ${down} — recorded above; check whether full-schema reads are the issue.`,
    depsNone: "none",
    depsNoData: "The service returned no dependency probes — status unknown.",
    serviceOkDetail: "The service port is connected — the certificate authority is reachable.",
    serviceUnknownDetail: "No service state received yet.",
    capsCount: (n: number) => `${n} capabilities`,
    capsDetail: (list: string) => `Declared capability inventory: ${list}.`,
    capsEmpty: "The inventory is empty — cannot judge.",
    capsAbsent: "The server did not provide an inventory — cannot judge.",
    degradedDegraded: "The service is in limited mode — the record may be incomplete; confirm whether full-schema reads are the issue.",
    degradedNormal: "The service reports no degraded state.",
    degradedUnknown: "The service did not report a degraded state — unknown.",
    normalValue: "NORMAL",
    degradedValue: "DEGRADED",
    dataOk: "QUERYABLE",
    dataBad: "NOT QUERYABLE",
    dataUnknown: "The server returned no data probe — cannot tell whether data is queryable.",
    dataOkDetail: (ms?: number) => `The MySQL (control-plane) probe passed${typeof ms === "number" ? ` — ${ms} ms` : ""}. The mysql probe succeeded.`,
    dataBadDetail: (err?: string | null) => `The MySQL (control-plane) probe failed${err ? `: ${err}` : ""} — the data cannot be used as the full schema.`,
  },
} as const;

export function buildHealthCategories(
  data: HealthData | null,
  error: Error | string | null,
  locale: Locale = "zh"
): HealthCategory[] {
  const c = COPY[locale];
  const checks =
    data && data.checks && typeof data.checks === "object" ? data.checks : null;
  const entries = checks ? Object.entries(checks) : [];
  const okCount = entries.filter(([, k]) => k && k.ok === true).length;
  const downNames = entries
    .filter(([, k]) => k && k.ok === false)
    .map(([name]) => name);

  // 1. service reachable — derived from the health call itself, never guessed.
  const service: HealthCategory = data
    ? {
        key: "service",
        label: c.serviceLabel,
        state: "ok",
        value: c.reachable,
        detail: c.serviceOkDetail,
        detailTitle: "GET /api/v1/health",
      }
    : error
    ? {
        key: "service",
        label: c.serviceLabel,
        state: "bad",
        value: c.unreachable,
        detail: typeof error === "string" ? error : error.message,
      }
    : {
        key: "service",
        label: c.serviceLabel,
        state: "unknown",
        value: c.unknownPill,
        detail: c.serviceUnknownDetail,
      };

  // 2. dependencies — aggregated from the checks map; absent map = UNKNOWN.
  const deps: HealthCategory =
    checks && entries.length > 0
      ? okCount === entries.length
        ? {
            key: "deps",
            label: c.depsLabel,
            state: "ok",
            value: c.reachableAll(okCount, entries.length),
            detail: c.depsOkDetail(
              entries
                .map(([name, k]) => name + (k && k.ok === true ? " OK" : " DOWN"))
                .join(" · ")
            ),
          }
        : {
            key: "deps",
            label: c.depsLabel,
            state: okCount === 0 ? "bad" : "warn",
            value: c.reachableAll(okCount, entries.length),
            detail: c.depsBadDetail(downNames.length > 0 ? downNames.join(", ") : c.depsNone),
            detailTitle: "degraded",
          }
      : {
          key: "deps",
          label: c.depsLabel,
          state: "unknown",
          value: c.unknownPill,
          detail: c.depsNoData,
          detailTitle: "checks missing",
        };

  // 3. capabilities — only reported when the payload carries an inventory.
  const caps = data ? data.capabilities : undefined;
  const capabilities: HealthCategory = Array.isArray(caps)
    ? caps.length > 0
      ? {
          key: "capabilities",
          label: c.capsLabel,
          state: "ok",
          value: c.capsCount(caps.length),
          detail: c.capsDetail(caps.map((k) => String(k)).join(", ")),
        }
      : {
          key: "capabilities",
          label: c.capsLabel,
          state: "unknown",
          value: c.unknownPill,
          detail: c.capsEmpty,
        }
    : caps && typeof caps === "object"
    ? {
        key: "capabilities",
        label: c.capsLabel,
        state: "ok",
        value: c.capsCount(Object.keys(caps).length),
        detail: c.capsDetail(Object.keys(caps).join(", ")),
      }
    : {
        key: "capabilities",
        label: c.capsLabel,
        state: "unknown",
        value: c.unknownPill,
        detail: c.capsAbsent,
        detailTitle: "capabilities missing",
      };

  // 4. degraded — reported only when the flag is actually present.
  const degraded: HealthCategory =
    typeof data?.degraded === "boolean"
      ? data.degraded
        ? {
            key: "degraded",
            label: c.degradedLabel,
            state: "warn",
            value: c.degradedValue,
            detail:
              Array.isArray(data.degraded_reasons) &&
              data.degraded_reasons.length > 0
                ? data.degraded_reasons.join("; ")
                : c.degradedDegraded,
          }
        : {
            key: "degraded",
            label: c.degradedLabel,
            state: "ok",
            value: c.normalValue,
            detail: c.degradedNormal,
            detailTitle: "degraded: false",
          }
      : {
          key: "degraded",
          label: c.degradedLabel,
          state: "unknown",
          value: c.unknownPill,
          detail: c.degradedUnknown,
          detailTitle: "degraded missing",
        };

  // 5. data queryable — derived from the MySQL probe.
  const mysql = checks ? checks.mysql : undefined;
  const queryable: HealthCategory = !mysql
    ? {
        key: "data",
        label: c.dataLabel,
        state: "unknown",
        value: c.unknownPill,
        detail: c.dataUnknown,
        detailTitle: "checks.mysql missing",
      }
    : mysql.ok === true
    ? {
        key: "data",
        label: c.dataLabel,
        state: "ok",
        value: c.dataOk,
        detail: c.dataOkDetail(typeof mysql.latency_ms === "number" ? mysql.latency_ms : undefined),
      }
    : {
        key: "data",
        label: c.dataLabel,
        state: "bad",
        value: c.dataBad,
        detail: c.dataBadDetail(mysql.error),
      };

  return [service, deps, capabilities, degraded, queryable];
}
