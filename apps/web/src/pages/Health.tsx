import { useEffect, useState } from "react";
import { apiGet, HealthData } from "../api";
import { ErrorBox, Panel, Spinner, StatCard, Table, healthStatusLabel, type Column, type StatTone } from "../ui";
import { buildHealthCategories, HealthCategoryState } from "./healthCategories";

interface DepRow {
  name: string;
  ok?: boolean;
  latency_ms?: number;
  error?: string | null;
}

const DEP_COLUMNS: Column<DepRow>[] = [
  {
    key: "name",
    header: "依赖",
    sortable: true,
    render: (r) => <span className="mono">{DEP_NAMES[r.name] || r.name}</span>,
  },
  {
    key: "ok",
    header: "状态",
    sortable: true,
    sortValue: (r) => (r.ok === true ? 0 : r.ok === false ? 2 : 1),
    render: (r) => (
      <span
        className={
          "pill " + (r.ok === true ? "pill-ok" : r.ok === false ? "pill-bad" : "pill-mute")
        }
      >
        {r.ok === true ? "OK" : r.ok === false ? "DOWN" : "未知"}
      </span>
    ),
  },
  {
    key: "latency_ms",
    header: "延迟 Latency",
    align: "right",
    sortable: true,
    sortValue: (r) => r.latency_ms ?? -1,
    render: (r) => (
      <span className="mono">
        {typeof r.latency_ms === "number" ? r.latency_ms + " ms" : "—"}
      </span>
    ),
  },
  {
    key: "error",
    header: "错误",
    render: (r) => <span className="muted mono">{r.error || "—"}</span>,
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
        <h1>健康 Health</h1>
        <div className="page-sub" title="FIVE-CATEGORY HEALTH">
          从五个角度看服务健康：服务是否可达、依赖是否可用、能力是否完整、当前是否降级、数据能否查询。缺少的信息会如实显示为「未知」，绝不用一个大绿勾掩盖问题。
        </div>
      </div>
      <ErrorBox error={error} />

      <Panel title="五类健康 Five-category health">
        {buildHealthCategories(data, error).map((c) => (
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
              label="整体状态"
              value={
                <span title={data.status || "未知"}>
                  {healthStatusLabel(data.status)}
                </span>
              }
              tone={overallTone}
            />
            <StatCard
              label="可用依赖"
              value={total > 0 ? okCount + " / " + total : "未知"}
              tone={depsTone}
            />
          </div>
          <Panel title="依赖清单 Dependency Matrix">
            <Table<DepRow>
              columns={DEP_COLUMNS}
              rows={depRows}
              rowKey={(r) => r.name}
              emptyTitle="暂无依赖信息"
              emptyDescription="健康端点未返回任何依赖检查。"
            />
          </Panel>
          {data.degraded === true ? (
            <div className="degraded" title="degraded">
              <strong>降级中 DEGRADED</strong> —{" "}
              部分依赖不可用；相关数据会以空结果明确返回并标记为降级，绝不伪造。
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
