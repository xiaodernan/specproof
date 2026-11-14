import { useEffect, useState } from "react";
import { apiGet, HealthData } from "../api";
import { ErrorBox, Panel, Spinner, StatCard, Table, healthStatusLabel, type Column, type StatTone } from "../ui";
import { buildHealthCategories, HealthCategoryState } from "./healthCategories";
import { useI18n } from "../i18n";

interface DepRow {
  name: string;
  ok?: boolean;
  latency_ms?: number;
  error?: string | null;
}

interface HealthCopy {
  title: string; sub: string; fivePanel: string; overallLabel: string; unknownTitle: string;
  depsLabel: string; depColName: string; depColStatus: string; depColLatency: string;
  depColError: string; unknown: string; matrixTitle: string; matrixEmptyTitle: string;
  matrixEmptyDesc: string; degradedStrong: string; degradedText: string;
}

const COPY: Record<"zh" | "en", HealthCopy> = {
  zh: {
    title: "服务状态",
    sub: "五类健康 · 服务是否跑着、依赖是否配齐、能力是否可用、降级是否发生——每一格都如实显示；未知就是未知，绝不把它抹成绿色。",
    fivePanel: "服务健康 · Five-category health",
    overallLabel: "整体状态",
    unknownTitle: "未知",
    depsLabel: "可达依赖",
    depColName: "依赖",
    depColStatus: "状态",
    depColLatency: "延迟 Latency",
    depColError: "错误",
    unknown: "未知",
    matrixTitle: "依赖矩阵 Dependency Matrix",
    matrixEmptyTitle: "没有依赖信息",
    matrixEmptyDesc: "健康检查还没有返回任何探针。",
    degradedStrong: "服务受限 DEGRADED",
    degradedText: "有些探针未通过，记录可能不完整，确认是否是读取完整库的问题。",
  },
  en: {
    title: "Service Health",
    sub: "Five-category health — is the service up, are the dependencies wired, are the capabilities available, did anything degrade. Every cell renders the truth; unknown stays unknown, never painted green.",
    fivePanel: "Five-category health",
    overallLabel: "Overall",
    unknownTitle: "UNKNOWN",
    depsLabel: "Dependencies reachable",
    depColName: "Dependency",
    depColStatus: "Status",
    depColLatency: "Latency",
    depColError: "Error",
    unknown: "UNKNOWN",
    matrixTitle: "Dependency Matrix",
    matrixEmptyTitle: "No dependency data",
    matrixEmptyDesc: "The health check returned no probes yet.",
    degradedStrong: "DEGRADED",
    degradedText: "Some probes are not passing; the record may be incomplete — confirm whether full-schema reads are the issue.",
  },
};

const makeColumns = (c: HealthCopy): Column<DepRow>[] => [
  {
    key: "name",
    header: c.depColName,
    sortable: true,
    render: (r) => <span className="mono">{DEP_NAMES[r.name] || r.name}</span>,
  },
  {
    key: "ok",
    header: c.depColStatus,
    sortable: true,
    sortValue: (r) => (r.ok === true ? 0 : r.ok === false ? 2 : 1),
    render: (r) => (
      <span
        className={
          "pill " + (r.ok === true ? "pill-ok" : r.ok === false ? "pill-bad" : "pill-mute")
        }
      >
        {r.ok === true ? "OK" : r.ok === false ? "DOWN" : c.unknown}
      </span>
    ),
  },
  {
    key: "latency_ms",
    header: c.depColLatency,
    align: "right",
    sortable: true,
    sortValue: (r) => r.latency_ms ?? -1,
    render: (r) => (
      <span className="mono">
        {typeof r.latency_ms === "number" ? r.latency_ms + " ms" : c.unknown}
      </span>
    ),
  },
  {
    key: "error",
    header: c.depColError,
    render: (r) => <span className="muted mono">{r.error || c.unknown}</span>,
  },
];

const DEP_NAMES: Record<string, string> = {
  mysql: "MySQL",
  mongodb: "MongoDB",
  elasticsearch: "Elasticsearch",
  redis: "Redis",
  rabbitmq: "RabbitMQ",
  minio: "MinIO",
};

const STATE_PILL: Record<HealthCategoryState, string> = {
  ok: "pill-ok",
  warn: "pill-run",
  bad: "pill-bad",
  unknown: "pill-mute",
};

export default function Health() {
  const { locale } = useI18n();
  const c = COPY[locale];
  const depColumns = makeColumns(c);
  const [data, setData] = useState<HealthData | null>(null);
  const [error, setError] = useState<Error | string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    const tick = () => {
      apiGet<HealthData>("/api/v1/health")
        .then((d) => {
          if (alive) setData(d);
        })
        .catch((e) => {
          if (alive) setError(e as Error);
        })
        .finally(() => {
          if (alive) setLoading(false);
        });
    };
    tick();
    const t = window.setInterval(tick, 15000);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, []);

  if (loading) return <Spinner />;

  const checks = data && data.checks ? data.checks : {};
  const depRows: DepRow[] = Object.entries(checks).map(([name, c]) => ({ name, ...c }));
  const okCount = Object.values(checks).filter((c) => c.ok === true).length;
  const total = Object.keys(checks).length;
  const overallTone: StatTone =
    data && data.degraded === true
      ? "warn"
      : data && typeof data.degraded === "boolean"
      ? "ok"
      : data && data.status === "ok"
      ? "ok"
      : "mute";
  const depsTone: StatTone =
    total === 0 ? "mute" : okCount === total ? "ok" : okCount === 0 ? "bad" : "warn";

  return (
    <div>
      <div className="page-head">
        <h1>{c.title}</h1>
        <div className="page-sub" title="FIVE-CATEGORY HEALTH">{c.sub}</div>
      </div>
      <ErrorBox error={error} />

      <Panel title={c.fivePanel}>
        {buildHealthCategories(data, error, locale).map((c) => (
          <div
            key={c.key}
            className="health-category"
            data-testid={"health-category-" + c.key}
            data-state={c.state}
          >
            <div className="health-category-head">
              <span className="health-category-label">{c.label}</span>
              <span className={"pill " + STATE_PILL[c.state]}>{c.value}</span>
            </div>
            <div className="health-category-detail muted" title={c.detailTitle}>
              {c.detail}
            </div>
          </div>
        ))}
      </Panel>

      {data ? (
        <>
          <div className="stat-grid" style={{ marginBottom: 16 }}>
            <StatCard
              label={c.overallLabel}
              value={
                <span title={data.status || c.unknownTitle}>
                  {healthStatusLabel(data.status)}
                </span>
              }
              tone={overallTone}
            />
            <StatCard
              label={c.depsLabel}
              value={total > 0 ? okCount + " / " + total : c.unknown}
              tone={depsTone}
            />
          </div>
          <Panel title={c.matrixTitle}>
            <Table<DepRow>
              columns={depColumns}
              rows={depRows}
              rowKey={(r) => r.name}
              emptyTitle={c.matrixEmptyTitle}
              emptyDescription={c.matrixEmptyDesc}
            />
          </Panel>
          {data.degraded === true ? (
            <div className="degraded" title="degraded">
              <strong>{c.degradedStrong}</strong> —{" "}
              {c.degradedText}
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
