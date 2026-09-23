import { useEffect, useMemo, useState } from "react";
import { AgentJobSummary, listAgentJobs } from "../../api";
import { Empty, ErrorBox, Panel, Spinner, Table, fmtTime, shortId, type Column } from "../../ui";
import { loadFailed } from "../../ui/errorHints";
import { agentStatusMeta } from "../util";

const STATUS_TONE: Record<string, string> = {
  ok: "pill-ok",
  bad: "pill-bad",
  warn: "pill-run",
};

const COLUMNS: Column<AgentJobSummary>[] = [
  {
    key: "task_name",
    header: "任务",
    sortable: true,
    render: (j) => (
      <span className="mono">
        {j.task_name}
        <span className="muted"> ({shortId(j.id)})</span>
      </span>
    ),
  },
  { key: "repo_path", header: "仓库 Repository", sortable: true, render: (j) => <span className="muted">{j.repo_path}</span> },
  {
    key: "status",
    header: "状态",
    sortable: true,
    render: (j) => {
      const meta = agentStatusMeta(j.status);
      return (
        <span className={"pill " + (STATUS_TONE[meta.tone] ?? "pill-mute")} title={j.status || ""}>
          {meta.label}
        </span>
      );
    },
  },
  { key: "plan_steps", header: "计划步骤", align: "right", sortable: true, render: (j) => <span className="mono">{j.plan_steps}</span> },
  { key: "events_count", header: "事件", align: "right", sortable: true, render: (j) => <span className="mono">{j.events_count}</span> },
  { key: "approvals_count", header: "审批", align: "right", sortable: true, render: (j) => <span className="mono">{j.approvals_count}</span> },
  { key: "updated_at", header: "更新时间", sortable: true, render: (j) => <span className="muted">{fmtTime(j.updated_at)}</span> },
];

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
      <div style={{ marginBottom: 16, display: "flex", flexWrap: "wrap", gap: 10 }}>
        <a className="btn" href="#/agent/new" style={{ display: "inline-block" }}>
          + 新建任务 New task
        </a>
        <a className="btn btn-ghost" href="#/agent/settings">模型连接</a>
      </div>
      <Panel
        title={"Agent 任务 (" + jobs.length + ")"}
        right={
          <select aria-label="按状态筛选 Filter by status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            {statuses.map((s) => (
              <option key={s} value={s}>
                {s === "ALL" ? "全部状态" : agentStatusMeta(s).label}
              </option>
            ))}
          </select>
        }
      >
        {loadFailed(error) ? (
          <div className="errorbox" role="alert">
            任务列表暂时无法加载（请求失败）— 这不代表没有任务，请稍后重试。
          </div>
        ) : jobs.length === 0 ? (
          <Empty text="暂无 Agent 任务 — 通过任务向导提交第一条需求规格" />
        ) : (
          <Table<AgentJobSummary>
            columns={COLUMNS}
            rows={jobs}
            rowKey={(j) => j.id}
            onRowClick={(j) => (window.location.hash = "#/agent/jobs/" + j.id)}
          />
        )}
      </Panel>
    </div>
  );
}
