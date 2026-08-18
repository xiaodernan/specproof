import { useEffect, useState } from "react";
import { apiGet, HealthData } from "../api";
import { ErrorBox, Panel, Spinner, StatCard } from "../components";

const DEP_NAMES: Record<string, string> = {
  mysql: "MySQL",
  mongodb: "MongoDB",
  elasticsearch: "Elasticsearch",
  redis: "Redis",
  rabbitmq: "RabbitMQ",
  minio: "MinIO",
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

  const okCount = data ? Object.values(data.checks).filter((c) => c.ok).length : 0;
  const total = data ? Object.keys(data.checks).length : 0;

  return (
    <div>
      <div className="page-head">
        <h1>健康 Health</h1>
        <div className="page-sub">DEPENDENCY PROBES — 逐项探测 + 延迟, 失败显式呈现 (degraded)</div>
      </div>
      <ErrorBox error={error} />

      {data ? (
        <>
          <div className="stat-grid" style={{ marginBottom: 16 }}>
            <StatCard label="整体状态" value={data.status.toUpperCase()} tone={data.degraded ? "warn" : "ok"} />
            <StatCard label="可用依赖" value={okCount + " / " + total} tone={okCount === total ? "ok" : "bad"} />
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
                {Object.entries(data.checks).map(([name, c]) => (
                  <tr key={name}>
                    <td className="mono">{DEP_NAMES[name] || name}</td>
                    <td>
                      <span className={"pill " + (c.ok ? "pill-ok" : "pill-bad")}>{c.ok ? "OK" : "DOWN"}</span>
                    </td>
                    <td className="mono">{c.latency_ms} ms</td>
                    <td className="muted mono">{c.error || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
          {data.degraded ? (
            <div className="degraded">
              <strong>degraded</strong> — 部分依赖不可用; 相关数据端点将以空数据 + degraded 字段诚实降级, 绝不伪造。
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
