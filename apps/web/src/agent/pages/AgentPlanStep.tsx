import { useState } from "react";
import { approveAgentJob } from "../../api";
import { ErrorBox, Panel, Spinner } from "../../components";
import { AgentJobShell, useAgentJob } from "../components";
import { stepStatusLabel } from "../util";

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
        <ErrorBox error={error || "任务不存在 (404)"} />
        <a href="#/agent">← 返回 Agent 总览</a>
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
        <Panel title="步骤审阅">
          <div className="errorbox">
            步骤 #{stepIndex} 不存在 (计划共 {plan ? plan.steps.length : 0} 步)
          </div>
          <a href={"#/agent/jobs/" + jobId + "/plan"}>← 返回计划</a>
        </Panel>
      ) : (
        <Panel title={"步骤 #" + stepIndex + " · " + step.title}>
          <div className="kv">
            <span className="kv-label">摘要 Summary</span>
            <span className="kv-value">{step.summary}</span>
          </div>
          <div className="kv">
            <span className="kv-label">状态 Status</span>
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
                <span className="kv-label">决策 Decision</span>
                <span className="kv-value mono">{step.approval.decision}</span>
              </div>
              {step.approval.note ? (
                <div className="kv">
                  <span className="kv-label">备注 Note</span>
                  <span className="kv-value">{step.approval.note}</span>
                </div>
              ) : null}
            </>
          ) : null}
          <label className="field">审批备注 Note (可选)</label>
          <input type="text" value={note} onChange={(e) => setNote(e.target.value)} />
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <button className="btn" disabled={busy} onClick={() => void decide("approve")}>
              批准本步 Approve step
            </button>
            <button className="btn btn-danger" disabled={busy} onClick={() => void decide("reject")}>
              拒绝本步 Reject step
            </button>
            <a className="btn btn-ghost" href={"#/agent/jobs/" + jobId + "/plan"}>
              返回 Back
            </a>
          </div>
          <div className="muted" style={{ marginTop: 8 }}>
            全部步骤批准后任务进入 EXECUTING; 任一步骤拒绝则任务 FAILED。
          </div>
        </Panel>
      )}
    </AgentJobShell>
  );
}
