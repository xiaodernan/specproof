import { useEffect, useState } from "react";
import { cancelAgentJob, type AgentJob } from "../../api";
import { Button, ErrorBox, Panel, Spinner, StatCard, fmtTime, kv, shortId } from "../../ui";
import { recordRecentJob } from "../../ui/recentJobs";
import { describePipelineError } from "../../ui/errorHints";
import { AgentJobShell, ProgressBar, useAgentJob } from "../components";
import { agentStatusMeta, eventKindLabel, isAgentTerminal, sseStateLabel } from "../util";
import { storedLocale } from "../../i18n/strings";

const isZh = (): boolean => storedLocale() === "zh";
const L = (zh: string, en: string): string => (isZh() ? zh : en);


function Timeline({ job }: { job: AgentJob }) {

  const entries: { at: string; text: string; tone: string }[] = [
    { at: job.created_at, text: L("任务创建", "Job created"), tone: "info" },
  ];
  if (job.plan) {
    entries.push({
      at: job.plan.created_at || job.updated_at,
      text: L("计划已生成", "Plan drafted"),
      tone: "warn",
    });
  }
  if (job.status === "EXECUTING") {
    entries.push({ at: job.updated_at, text: L("正在执行计划", "Executing the plan"), tone: "info" });
  }
  entries.push({
    at: job.updated_at,
    text: agentStatusMeta(job.status).label + " · " + job.status,
    tone: agentStatusMeta(job.status).tone,
  });
  return (
    <div className="timeline" aria-label={L("任务状态时间线", "Agent status timeline")}>
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
        <ErrorBox error={error || L("Agent 任务不存在（404）", "Agent job does not exist (404)")} />
        <a href="#/agent">{L("← 返回 Agent 总览", "← Back to the Agent overview")}</a>
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
      setActionMsg(L("已提交取消", "Cancel requested"));
      reload();
    } catch (e) {
      setActionError(e as Error);
    } finally {
      setCancelling(false);
    }
  };

  const progress = job.progress;
  // Same predicate the API enforces: `_require_cancellable`
  // (api/routes/agent_console.py) refuses only what is IN
  // _TERMINAL_CONSOLE_STATUSES, so a status this console has never seen stays
  // cancellable here too. The point of importing the shared set is not a new
  // rule — it is that this page and the server cannot drift apart.
  const terminal = isAgentTerminal(job.status);
  const failure = job.result?.reason || progress.message;

  return (
    <AgentJobShell
      job={job}
      active="overview"
      reload={reload}
      right={
        <Button variant="ghost" size="sm" disabled={terminal || cancelling} onClick={() => void cancel()}>
          {cancelling ? L("正在取消…", "Cancelling…") : L("取消", "Cancel")}
        </Button>
      }
    >
      <ErrorBox error={actionError} />
      <ErrorBox error={error} />
      {actionMsg ? <div className="degraded" role="status">{actionMsg}</div> : null}
      {job.status === "AWAITING_APPROVAL" ? <Panel title={L("计划已就绪，等待你确认", "Plan ready — awaiting your approval")}><p>{L("请审阅步骤、目标文件和验收标准。批准后才会开始修改代码。", "Review the steps, target files and acceptance criteria — the plan only touches code once you approve it.")}</p><a className="btn btn-primary" href={"#/agent/jobs/" + encodeURIComponent(jobId) + "/plan"}>{L("审阅并批准计划 →", "Review and approve the plan →")}</a></Panel> : null}
      {job.status === "PLANNING" ? <div className="degraded" role="status">{L("正在生成执行计划，尚未修改代码。", "Generating the execution plan — no code has been touched yet.")} <a href={"#/agent/jobs/" + encodeURIComponent(jobId) + "/tools"}>{L("查看模型实时输出 →", "Watch the live model output →")}</a></div> : null}
      {job.status === "FAILED" ? <div className="errorbox" role="alert" title={failure || undefined}><strong>{L("任务未完成", "Task did not finish")}</strong><p>{failure ? describePipelineError(String(failure)) : L("执行失败，请查看结果和事件记录。", "Execution failed — see the result and event log.")}</p><a href={"#/agent/jobs/" + encodeURIComponent(jobId) + "/result"}>{L("查看失败详情 →", "See failure details →")}</a></div> : null}
      <div className="stat-grid" style={{ marginBottom: 16 }}>
        <StatCard label={L("状态", "Status")} value={agentStatusMeta(job.status).label} tone={agentStatusMeta(job.status).tone} />
        <StatCard label={L("进度", "Progress")} value={progress.percent + "%"} />
        <StatCard label={L("计划步骤", "Plan steps")} value={job.plan ? job.plan.steps.length : 0} />
        <StatCard label={L("事件", "Events")} value={job.events_count} />
        <StatCard label={L("审批", "Approvals")} value={job.approvals_count} />
      </div>
      <div className="page-grid">
        <Panel
          title={L("状态时间线", "Status timeline")}
          right={
            <span className="muted" style={{ fontSize: 11 }}>
              {L("实时连接：", "Live connection: ")}{sseStateLabel(streamState)}
              {events.length > 0 ? ` · ${L("已收", "")}${events.length}${L(" 个事件", " events")}` : ""}
            </span>
          }
        >
          <Timeline job={job} />
          {events.length > 0 ? (
            <>
              <div className="kv-label">
                {L("最近事件（实时）", "Recent events (live)")}
\1</div>
              {events.slice(-5).reverse().map((ev) => (
                <div key={ev.seq} className="kv">
                  <span className="kv-label">{eventKindLabel(ev.type)}</span>
                  <span className="kv-value mono" title={ev.at}>{fmtTime(ev.at)}</span>
                </div>
              ))}
              <a href={"#/agent/jobs/" + encodeURIComponent(jobId) + "/events"}>{L("查看完整事件记录 →", "Full event log →")}</a>
            </>
          ) : null}
        </Panel>
        <Panel title={L("任务信息", "Task info")}>
          {kv(L("仓库", "Repository"), job.repo_path)}
          {kv(L("任务", "Task"), job.task_name)}
          {kv(L("执行者", "Worker"), job.worker_id || "—")}
          {kv(L("创建", "Created"), job.created_at)}
          {kv(L("更新", "Updated"), job.updated_at)}
          <div className="kv-label">
            {L("当前进度", "Current progress")}
          </div>
          <ProgressBar percent={progress.percent} />
          <div className="muted" style={{ marginTop: 6 }}>
            {progress.message}
          </div>
        </Panel>
      </div>
      <Panel title={L("需求规格", "Spec")}>
        <pre className="json">{job.spec_text}</pre>
      </Panel>
    </AgentJobShell>
  );
}
