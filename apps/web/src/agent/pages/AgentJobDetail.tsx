import { useEffect, useState } from "react";
import { cancelAgentJob } from "../../api";
import { ErrorBox, Panel, Spinner, StatCard, kv } from "../../components";
import { AgentJobShell, ProgressBar, useAgentJob } from "../components";
import { agentStatusMeta } from "../util";

function Timeline(props: { jobId: string }) {
  const { job, error, loading, reload } = useAgentJob(props.jobId);
  useEffect(() => {
    const id = window.setInterval(reload, 4000);
    return () => window.clearInterval(id);
  }, [reload]);
  if (loading) return <Spinner />;
  if (!job) return <ErrorBox error={error || "任务不存在 (404)"} />;

  const entries: { at: string; text: string; tone: string }[] = [
    { at: job.created_at, text: "任务创建 Job created", tone: "info" },
  ];
  if (job.plan) {
    entries.push({
      at: job.plan.created_at || job.updated_at,
      text: "计划已生成 (待审批) Plan drafted",
      tone: "warn",
    });
  }
  if (["EXECUTING", "COMPLETED", "FAILED"].includes(job.status)) {
    entries.push({ at: job.updated_at, text: "计划已批准 → 执行 Plan approved", tone: "ok" });
  }
  if (["COMPLETED", "FAILED"].includes(job.status)) {
    entries.push({ at: job.updated_at, text: "门禁已裁决 Gate decided", tone: "warn" });
  }
  entries.push({
    at: job.updated_at,
    text: agentStatusMeta(job.status).label + " · " + job.status,
    tone: agentStatusMeta(job.status).tone,
  });
  return (
    <div className="timeline">
      {entries.map((e, i) => (
        <div key={i} className="tl-item">
          <span className={"tl-dot tl-" + e.tone} />
          <div>
            <div>{e.text}</div>
            <div className="muted mono" style={{ fontSize: 11 }}>
              {e.at}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function AgentJobDetail(props: { jobId: string }) {
  const { jobId } = props;
  const { job, error, loading, reload } = useAgentJob(jobId);
  const [actionError, setActionError] = useState<Error | string | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  if (loading) return <Spinner />;
  if (!job) {
    return (
      <div>
        <ErrorBox error={error || "Agent 任务不存在 (404)"} />
        <a href="#/agent">← 返回 Agent 总览</a>
      </div>
    );
  }

  const cancel = async () => {
    setActionError(null);
    setActionMsg(null);
    try {
      await cancelAgentJob(jobId);
      setActionMsg("已提交取消 Cancel requested");
      reload();
    } catch (e) {
      setActionError(e as Error);
    }
  };

  const progress = job.progress;

  return (
    <AgentJobShell
      job={job}
      active="overview"
      right={
        <button className="btn btn-ghost btn-sm" onClick={() => void cancel()}>
          取消 Cancel
        </button>
      }
    >
      <ErrorBox error={actionError} />
      {actionMsg ? <div className="degraded">{actionMsg}</div> : null}
      <div className="stat-grid" style={{ marginBottom: 16 }}>
        <StatCard label="状态 Status" value={job.status} tone={agentStatusMeta(job.status).tone} />
        <StatCard label="进度 Progress" value={progress.percent + "%"} />
        <StatCard label="计划步骤 Plan steps" value={job.plan ? job.plan.steps.length : 0} />
        <StatCard label="事件 Events" value={job.events_count} />
        <StatCard label="审批 Approvals" value={job.approvals_count} />
      </div>
      <div className="page-grid">
        <Panel title="状态时间线 Timeline">
          <Timeline jobId={jobId} />
        </Panel>
        <Panel title="任务信息">
          {kv("Repo", job.repo_path)}
          {kv("Task", job.task_name)}
          {kv("Worker", job.worker_id || "—")}
          {kv("创建 Created", job.created_at)}
          {kv("更新 Updated", job.updated_at)}
          <div className="kv-label" style={{ margin: "10px 0 4px" }}>
            当前进度 Current progress
          </div>
          <ProgressBar percent={progress.percent} />
          <div className="muted" style={{ marginTop: 6 }}>
            {progress.message}
          </div>
        </Panel>
      </div>
      <Panel title="需求规格 Spec">
        <pre className="json">{job.spec_text}</pre>
      </Panel>
    </AgentJobShell>
  );
}
