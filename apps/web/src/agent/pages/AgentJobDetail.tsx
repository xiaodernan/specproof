import { useEffect, useState } from "react";
import { cancelAgentJob, type AgentJob } from "../../api";
import { Button, ErrorBox, Panel, Spinner, StatCard, fmtTime, kv, shortId } from "../../ui";
import { recordRecentJob } from "../../ui/recentJobs";
import { describePipelineError } from "../../ui/errorHints";
import { AgentJobShell, ProgressBar, useAgentJob } from "../components";
import { agentStatusMeta, eventKindLabel, sseStateLabel } from "../util";

function Timeline({ job }: { job: AgentJob }) {

  const entries: { at: string; text: string; tone: string }[] = [
    { at: job.created_at, text: "任务创建 Job created", tone: "info" },
  ];
  if (job.plan) {
    entries.push({
      at: job.plan.created_at || job.updated_at,
      text: "计划已生成 Plan drafted",
      tone: "warn",
    });
  }
  if (job.status === "EXECUTING") {
    entries.push({ at: job.updated_at, text: "正在执行计划", tone: "info" });
  }
  entries.push({
    at: job.updated_at,
    text: agentStatusMeta(job.status).label + " · " + job.status,
    tone: agentStatusMeta(job.status).tone,
  });
  return (
    <div className="timeline" aria-label="任务状态时间线">
      {entries.map((e, i) => (
        <div key={i} className="tl-item">
          <span className={"tl-dot tl-" + e.tone} />
          <div>
            <div>{e.text}</div>
            <div className="muted mono" style={{ fontSize: 11 }} title={e.at}>
              {fmtTime(e.at)}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function AgentJobDetail(props: { jobId: string }) {
  const { jobId } = props;
  const { job, error, loading, reload, events, streamState } = useAgentJob(jobId);
  const [actionError, setActionError] = useState<Error | string | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);

  useEffect(() => { setActionError(null); setActionMsg(null); setCancelling(false); }, [jobId]);

  // Record the opened job for the command palette (Aurora recent-jobs).
  useEffect(() => {
    if (!job) return;
    const label = job.task_name || job.repo_path
      ? (job.task_name || job.repo_path) + " · " + shortId(job.id)
      : "任务 " + shortId(job.id);
    recordRecentJob("#/agent/jobs/" + jobId, label);
  }, [job, jobId]);

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
    if (cancelling) return;
    setCancelling(true);
    setActionError(null);
    setActionMsg(null);
    try {
      await cancelAgentJob(jobId);
      setActionMsg("已提交取消 Cancel requested");
      reload();
    } catch (e) {
      setActionError(e as Error);
    } finally {
      setCancelling(false);
    }
  };

  const progress = job.progress;
  const terminal = ["COMPLETED", "FAILED", "CANCELLED"].includes(job.status);
  const failure = job.result?.reason || progress.message;

  return (
    <AgentJobShell
      job={job}
      active="overview"
      reload={reload}
      right={
        <Button variant="ghost" size="sm" disabled={terminal || cancelling} onClick={() => void cancel()}>
          {cancelling ? "正在取消…" : "取消 Cancel"}
        </Button>
      }
    >
      <ErrorBox error={actionError} />
      <ErrorBox error={error} />
      {actionMsg ? <div className="degraded" role="status">{actionMsg}</div> : null}
      {job.status === "AWAITING_APPROVAL" ? <Panel title="计划已就绪，等待你确认"><p>请审阅步骤、目标文件和验收标准。批准后才会开始修改代码。</p><a className="btn btn-primary" href={"#/agent/jobs/" + encodeURIComponent(jobId) + "/plan"}>审阅并批准计划 →</a></Panel> : null}
      {job.status === "PLANNING" ? <div className="degraded" role="status">正在生成执行计划，尚未修改代码。<a href={"#/agent/jobs/" + encodeURIComponent(jobId) + "/tools"}>查看模型实时输出 →</a></div> : null}
      {job.status === "FAILED" ? <div className="errorbox" role="alert" title={failure || undefined}><strong>任务未完成</strong><p>{failure ? describePipelineError(String(failure)) : "执行失败，请查看结果和事件记录。"}</p><a href={"#/agent/jobs/" + encodeURIComponent(jobId) + "/result"}>查看失败详情 →</a></div> : null}
      <div className="stat-grid" style={{ marginBottom: 16 }}>
        <StatCard label="状态 Status" value={agentStatusMeta(job.status).label} tone={agentStatusMeta(job.status).tone} />
        <StatCard label="进度 Progress" value={progress.percent + "%"} />
        <StatCard label="计划步骤 Plan steps" value={job.plan ? job.plan.steps.length : 0} />
        <StatCard label="事件 Events" value={job.events_count} />
        <StatCard label="审批 Approvals" value={job.approvals_count} />
      </div>
      <div className="page-grid">
        <Panel
          title="状态时间线 Timeline"
          right={
            <span className="muted" style={{ fontSize: 11 }}>
              实时连接：{sseStateLabel(streamState)}
              {events.length > 0 ? ` · 已收到 ${events.length} 个事件` : ""}
            </span>
          }
        >
          <Timeline job={job} />
          {events.length > 0 ? (
            <>
              <div className="kv-label" style={{ margin: "12px 0 6px" }}>
                最近事件（实时）
              </div>
              {events.slice(-5).reverse().map((ev) => (
                <div key={ev.seq} className="kv">
                  <span className="kv-label">{eventKindLabel(ev.type)}</span>
                  <span className="kv-value mono" title={ev.at}>{fmtTime(ev.at)}</span>
                </div>
              ))}
              <a href={"#/agent/jobs/" + encodeURIComponent(jobId) + "/events"}>查看完整事件记录 →</a>
            </>
          ) : null}
        </Panel>
        <Panel title="任务信息">
          {kv("仓库 Repo", job.repo_path)}
          {kv("任务 Task", job.task_name)}
          {kv("执行器 Worker", job.worker_id || "—")}
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
