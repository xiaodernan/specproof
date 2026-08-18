import { useEffect, useMemo, useState } from "react";
import { AgentJobSummary, listAgentJobs } from "../../api";
import { Empty, ErrorBox, Panel, Spinner, fmtTime, shortId } from "../../components";
import { agentStatusMeta } from "../util";

export default function AgentOverview() {
  const [jobs, setJobs] = useState<AgentJobSummary[]>([]);
  const [error, setError] = useState<Error | string | null>(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("ALL");

  useEffect(() => {
    let alive = true;
    listAgentJobs(statusFilter === "ALL" ? undefined : statusFilter)
      .then((d) => {
        if (alive) setJobs(d.jobs || []);
      })
      .catch((e) => {
        if (alive) setError(e as Error);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [statusFilter]);

  const statuses = useMemo(() => {
    const s = new Set<string>();
    jobs.forEach((j) => s.add(j.status || "UNKNOWN"));
    return ["ALL", ...Array.from(s).sort()];
  }, [jobs]);

  if (loading) return <Spinner />;

  return (
    <div>
      <div className="page-head">
        <h1>SpecCraft Agent 工作台</h1>
        <div className="page-sub">
          AGENT CONSOLE — 任务向导 / 计划审阅 / 实时工具流 / 审批 / Diff
        </div>
      </div>
      <ErrorBox error={error} />
      <div style={{ marginBottom: 16 }}>
        <a className="btn" href="#/agent/new" style={{ display: "inline-block" }}>
          + 新建任务 New task
        </a>
      </div>
      <Panel
        title={"Agent 任务 (" + jobs.length + ")"}
        right={
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            {statuses.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        }
      >
        {jobs.length === 0 ? (
          <Empty text="暂无 Agent 任务 — 通过任务向导提交第一条需求规格" />
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>任务</th>
                <th>Repository</th>
                <th>状态</th>
                <th>计划步骤</th>
                <th>事件</th>
                <th>审批</th>
                <th>更新时间</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => {
                const meta = agentStatusMeta(j.status);
                return (
                  <tr
                    key={j.id}
                    style={{ cursor: "pointer" }}
                    onClick={() => (window.location.hash = "#/agent/jobs/" + j.id)}
                  >
                    <td className="mono">
                      {j.task_name}
                      <span className="muted"> ({shortId(j.id)})</span>
                    </td>
                    <td className="muted">{j.repo_path}</td>
                    <td>
                      <span className={"pill " + (meta.tone === "ok" ? "pill-ok" : meta.tone === "bad" ? "pill-bad" : meta.tone === "warn" ? "pill-run" : "pill-mute")}>
                        {j.status}
                      </span>
                    </td>
                    <td className="mono">{j.plan_steps}</td>
                    <td className="mono">{j.events_count}</td>
                    <td className="mono">{j.approvals_count}</td>
                    <td className="muted">{fmtTime(j.updated_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
