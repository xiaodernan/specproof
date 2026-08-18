import { useEffect, useState } from "react";
import { apiGet, DashboardData, Job } from "../api";
import { Degraded, Empty, ErrorBox, Panel, Spinner, StatCard, StatusPill, fmtPct, fmtTime, shortId } from "../components";

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<Error | string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const [d, j] = await Promise.all([
          apiGet<DashboardData>("/api/v1/dashboard"),
          apiGet<{ jobs: Job[] }>("/jobs?limit=200"),
        ]);
        if (!alive) return;
        setData(d);
        setJobs(j.jobs || []);
      } catch (e) {
        if (alive) setError(e as Error);
      } finally {
        if (alive) setLoading(false);
      }
    }
    load();
    return () => {
      alive = false;
    };
  }, []);

  if (loading) return <Spinner />;

  const d = data;
  const maxTl = d && d.timeline_24h.length
    ? Math.max(...d.timeline_24h.map((t) => t.count), 1)
    : 1;

  return (
    <div>
      <div className="page-head">
        <h1>总览 Dashboard</h1>
        <div className="page-sub">JOB AGGREGATES / 24H TIMELINE / COST — MySQL 为事实源</div>
      </div>
      <ErrorBox error={error} />
      {d ? <Degraded reasons={d.degraded_reasons} /> : null}

      {d ? (
        <>
          <div className="stat-grid" style={{ marginBottom: 16 }}>
            <StatCard label="任务总数 JOBS" value={d.jobs.total} tone="info" />
            <StatCard
              label="失败率 FAILURE"
              value={fmtPct(d.jobs.failure_rate)}
              tone={d.jobs.failure_rate ? (d.jobs.failure_rate > 0 ? "bad" : "ok") : "mute"}
              sub={((d.jobs.by_status["FAILED"] || 0) + (d.jobs.by_status["ERROR"] || 0)) + " 个"}
            />
            <StatCard
              label="拦截率 BLOCKED"
              value={fmtPct(d.jobs.blocked_rate)}
              tone={d.jobs.blocked_rate ? (d.jobs.blocked_rate > 0 ? "warn" : "ok") : "mute"}
              sub={(d.jobs.by_status["BLOCKED"] || 0) + " 个"}
            />
            <StatCard
              label="已验证 VERIFIED"
              value={d.jobs.by_status["VERIFIED"] || 0}
              tone="ok"
            />
            <StatCard
              label="运行中 RUNNING"
              value={(d.jobs.by_status["RUNNING"] || 0) + (d.jobs.by_status["QUEUED"] || 0)}
              tone="warn"
            />
          </div>

          <div className="page-grid">
            <Panel title="24h 任务时间线 Timeline">
              {d.timeline_24h.length === 0 ? (
                <Empty text="近 24 小时无任务记录 (诚实空态, 非伪造)" />
              ) : (
                <>
                  <div className="timeline-chart">
                    {d.timeline_24h.map((t) => (
                      <div key={t.hour} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center" }}>
                        <div style={{ height: 80, display: "flex", alignItems: "flex-end", width: "100%" }}>
                          <div
                            className={"tl-bar" + (t.failed > 0 ? " tl-failed" : "")}
                            style={{ height: Math.max(4, (t.count / maxTl) * 80) }}
                            title={t.hour + " — " + t.count + " 个任务, 失败 " + t.failed}
                          />
                        </div>
                        <div className="tl-label">{t.hour.slice(11, 16)}</div>
                      </div>
                    ))}
                  </div>
                  <div className="muted" style={{ fontSize: 11 }}>
                    时区: {d.timeline_timezone} — 红色柱表示该小时含失败任务
                  </div>
                </>
              )}
            </Panel>

            <Panel title="成本与 Token">
              <div className="kv">
                <span className="kv-label">成本 Cost</span>
                <span className="kv-value">
                  {d.cost.available ? d.cost.total_usd + " USD" : "不可用 UNAVAILABLE"}
                </span>
              </div>
              <div className="kv">
                <span className="kv-label">Token</span>
                <span className="kv-value">{d.tokens.available ? String(d.tokens.total) : "不可用 UNAVAILABLE"}</span>
              </div>
              <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                {d.cost.reason} / {d.tokens.reason} — 管线未持久化账本时显式呈现, 绝不显示伪造数字。
              </div>
            </Panel>
          </div>

          <Panel
            title="最近任务 Recent Jobs"
            right={<a href="#/jobs" className="btn btn-ghost btn-sm">全部任务 →</a>}
          >
            {d.recent_jobs.length === 0 ? (
              <Empty text="暂无任务 — 可通过 POST /jobs 提交验证任务" />
            ) : (
              <table className="data">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Base → Head</th>
                    <th>状态</th>
                    <th>创建时间</th>
                  </tr>
                </thead>
                <tbody>
                  {d.recent_jobs.map((j) => (
                    <tr key={j.id} style={{ cursor: "pointer" }} onClick={() => (window.location.hash = "#/jobs/" + j.id)}>
                      <td className="mono">{shortId(j.id)}</td>
                      <td className="mono">{(j.base_ref || "") + " → " + (j.head_ref || "")}</td>
                      <td><StatusPill status={j.status || ""} /></td>
                      <td className="muted">{fmtTime(j.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>
        </>
      ) : (
        <Empty text={error ? "加载失败" : "无数据"} />
      )}

      <Panel title="全量任务状态分布 (Jobs API)">
        {jobs.length === 0 ? (
          <Empty text="暂无任务" />
        ) : (
          <div className="stat-grid">
            {Object.entries(
              jobs.reduce<Record<string, number>>((acc, j) => {
                const s = (j.status || "UNKNOWN").toUpperCase();
                acc[s] = (acc[s] || 0) + 1;
                return acc;
              }, {})
            )
              .sort((a, b) => b[1] - a[1])
              .map(([status, n]) => (
                <StatCard key={status} label={status} value={n} tone={status === "VERIFIED" ? "ok" : status === "BLOCKED" || status === "FAILED" ? "bad" : "mute"} />
              ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
