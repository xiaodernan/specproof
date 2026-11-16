import { useState } from "react";
import { approveAgentJob } from "../../api";
import { Button, ErrorBox, Panel, Spinner } from "../../ui";
import { AgentJobShell, useAgentJob } from "../components";
import { approvalDecisionLabel, stepStatusLabel } from "../util";
import { storedLocale } from "../../i18n/strings";
const isZh = (): boolean => storedLocale() === "zh";
const L = (zh: string, en: string): string => (isZh() ? zh : en);

export default function AgentPlanStep(props: { jobId: string; stepIndex: number }) {
  const { jobId, stepIndex } = props;
  const { job, error, loading, reload } = useAgentJob(jobId);
  const [note, setNote] = useState("");
  const [actionError, setActionError] = useState<Error | string | null>(null);
  const [busy, setBusy] = useState(false);

  if (loading) return <Spinner />;
  if (!job) {
    return (
      <div>
        <ErrorBox error={error || L("任务不存在（404）", "Task not found (404)")} />
        <a href="#/agent">{L("← 返回 Agent 总览", "← Back to Agent overview")}</a>
      </div>
    );
  }

  const plan = job.plan;
  const step = plan && plan.steps[stepIndex];

  const decide = async (decision: "approve" | "reject") => {
    setActionError(null);
    setBusy(true);
    try {
      await approveAgentJob(jobId, decision, "step", note.trim(), stepIndex);
      reload();
    } catch (e) {
      setActionError(e as Error);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AgentJobShell job={job} active="plan">
      <ErrorBox error={actionError} />
      {!step ? (
        <Panel title={L("步骤审阅", "Step review")}>
          <div className="errorbox">
            {L("步骤 #", "Step #")}{stepIndex} {L("不存在（计划共 ", "does not exist (the plan has ")}{plan ? plan.steps.length : 0} {L(" 步）", " steps)")}
          </div>
          <a href={"#/agent/jobs/" + jobId + "/plan"}>{L("← 返回计划", "← Back to the plan")}</a>
        </Panel>
      ) : (
        <Panel title={L("步骤 #", "Step #") + stepIndex + " · " + step.title}>
          <div className="kv">
            <span className="kv-label">{L("摘要", "Summary")}</span>
            <span className="kv-value">{step.summary}</span>
          </div>
          <div className="kv">
            <span className="kv-label">{L("状态", "Status")}</span>
            <span className="kv-value">
              <span
                className={
                  "pill " +
                  (step.status === "approved"
                    ? "pill-ok"
                    : step.status === "rejected"
                    ? "pill-bad"
                    : "pill-mute")
                }
              >
                {stepStatusLabel(step.status)}
              </span>
            </span>
          </div>
          {step.approval ? (
            <>
              <div className="kv">
                <span className="kv-label">{L("决策", "Decision")}</span>
                <span className="kv-value mono" title={step.approval.decision}>
                  {approvalDecisionLabel(step.approval.decision)}
                </span>
              </div>
              {step.approval.note ? (
                <div className="kv">
                  <span className="kv-label">{L("备注", "Note")}</span>
                  <span className="kv-value">{step.approval.note}</span>
                </div>
              ) : null}
            </>
          ) : null}
          {job.execution_mode ? <p>{L("请在完整计划页审阅全部步骤后批准执行。", "Review the whole plan on the full plan page before approving execution.")}<a href={"#/agent/jobs/" + jobId + "/plan"}>{L("返回计划 →", "Back to the plan →")}</a></p> : <>
          <label className="field" htmlFor="plan-step-note">{L("审批备注（可选）", "Approval note (optional)")}</label>
          <input id="plan-step-note" type="text" value={note} onChange={(e) => setNote(e.target.value)} />
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <Button disabled={busy} onClick={() => void decide("approve")}>
              {L("批准本步", "Approve step")}
            </Button>
            <Button variant="danger" disabled={busy} onClick={() => void decide("reject")}>
              {L("拒绝本步", "Reject step")}
            </Button>
            <a className="btn btn-ghost" href={"#/agent/jobs/" + jobId + "/plan"}>
              {L("返回", "Back")}
            </a>
          </div>
          <div className="muted" style={{ marginTop: 8 }}>
            {L("全部步骤批准后任务进入 EXECUTING；任一步骤拒绝则任务 FAILED。", "Every approved step moves the task into EXECUTING; any rejected step fails the task.")}
          </div></>}
        </Panel>
      )}
    </AgentJobShell>
  );
}
