import { useEffect, useMemo, useState } from "react";
import { AgentJobSummary, listAgentJobs } from "../../api";
import { Empty, ErrorBox, Panel, Spinner, Table, fmtTime, shortId, type Column } from "../../ui";
import { loadFailed } from "../../ui/errorHints";
import { agentStatusMeta } from "../util";
import { storedLocale } from "../../i18n/strings";
const isZh = (): boolean => storedLocale() === "zh";
const L = (zh: string, en: string): string => (isZh() ? zh : en);

const STATUS_TONE: Record<string, string> = {
  ok: "pill-ok",
  bad: "pill-bad",
  warn: "pill-run",
};

const COLUMNS: Column<AgentJobSummary>[] = [
  {
    key: "task_name",
    header: L("任务", "Task"),
    sortable: true,
    render: (j) => (
      <span className="mono">
        {j.task_name}
        <span className="muted"> ({shortId(j.id)})</span>
      </span>
    ),
  },
  { key: "repo_path", header: L("仓库", "Repo"), sortable: true, render: (j) => <span className="muted">{j.repo_path}</span> },
  {
    key: "status",
    header: L("状态", "Status"),
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
  { key: "plan_steps", header: L("计划步骤", "Plan steps"), align: "right", sortable: true, render: (j) => <span className="mono">{j.plan_steps}</span> },
  { key: "events_count", header: L("事件", "Events"), align: "right", sortable: true, render: (j) => <span className="mono">{j.events_count}</span> },
  { key: "approvals_count", header: L("审批", "Approvals"), align: "right", sortable: true, render: (j) => <span className="mono">{j.approvals_count}</span> },
  { key: "updated_at", header: L("更新时间", "Updated"), sortable: true, render: (j) => <span className="muted">{fmtTime(j.updated_at)}</span> },
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
        <h1>{L("SpecCraft Agent 工作台", "SpecCraft Agent Workbench")}</h1>
        <div className="page-sub">
          {L("AGENT CONSOLE · 任务向导 / 计划审阅 / 实时工具流 / 审批 / Diff", "AGENT CONSOLE · wizard / plan review / tool stream / approvals / diff")}
        </div>
      </div>
      <ErrorBox error={error} />
      <div style={{ marginBottom: 16, display: "flex", flexWrap: "wrap", gap: 10 }}>
        <a className="btn" href="#/agent/new" style={{ display: "inline-block" }}>
          + {L("新建任务", "New task")}
        </a>
        <a className="btn btn-ghost" href="#/agent/settings">{L("模型连接", "Model connection")}</a>
      </div>
      <Panel
        title={L("Agent 任务", "Agent tasks") + " (" + jobs.length + ")"}
        right={
          <select aria-label={L("按状态筛选", "Filter by status")} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            {statuses.map((s) => (
              <option key={s} value={s}>
                {s === "ALL" ? L("全部状态", "All statuses") : agentStatusMeta(s).label}
              </option>
            ))}
          </select>
        }
      >
        {loadFailed(error) ? (
          <div className="errorbox" role="alert">
            {L("任务列表暂时无法加载（请求失败）——这不代表没有任务，请稍后重试。", "The task list failed to load (request failed); this does not mean there are no tasks — retry shortly.")}
          </div>
        ) : jobs.length === 0 ? (
          <Empty text={L("暂无 Agent 任务 — 通过任务向导提交第一条需求规格", "No Agent tasks yet — file the first spec through the wizard.")} />
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
