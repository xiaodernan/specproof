import { useEffect, useState } from "react";
import { apiGet, HealthData } from "../api";
import { ErrorBox, Panel, Spinner, StatCard, type StatTone } from "../ui";
import { buildHealthCategories, HealthCategoryState } from "./healthCategories";

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
        <div className="page-sub">
          FIVE-CATEGORY HEALTH — 服务可达 / 依赖可达 / 能力完整度 / 当前降级 / 数据可查询; 缺失字段显示 未知, 绝不用一个大绿勾掩盖缺陷
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
            <div className="health-category-detail muted">{c.detail}</div>
          </div>
        ))}
      </Panel>

      {data ? (
        <>
          <div className="stat-grid" style={{ marginBottom: 16 }}>
            <StatCard
              label="整体状态"
              value={data.status ? data.status.toUpperCase() : "未知"}
              tone={overallTone}
            />
            <StatCard
              label="可用依赖"
              value={total > 0 ? okCount + " / " + total : "未知"}
              tone={depsTone}
            />
          </div>
          <Panel title="依赖清单 Dependency Matrix">
            <table className="data">
              <thead>
                <tr>
                  <th>依赖</th>
                  <th>状态</th>
                  <th>延迟 Latency</th>
                  <th>错误</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(checks).map(([name, c]) => (
                  <tr key={name}>
                    <td className="mono">{DEP_NAMES[name] || name}</td>
                    <td>
                      <span
                        className={
                          "pill " +
                          (c.ok === true
                            ? "pill-ok"
                            : c.ok === false
                            ? "pill-bad"
                            : "pill-mute")
                        }
                      >
                        {c.ok === true ? "OK" : c.ok === false ? "DOWN" : "未知"}
                      </span>
                    </td>
                    <td className="mono">
                      {typeof c.latency_ms === "number" ? c.latency_ms + " ms" : "—"}
                    </td>
                    <td className="muted mono">{c.error || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
          {data.degraded === true ? (
            <div className="degraded">
              <strong>degraded</strong> — 部分依赖不可用; 相关数据端点将以空数据 + degraded 字段诚实降级, 绝不伪造。
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
