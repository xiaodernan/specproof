import { useState } from "react";
import { approveAgentJob } from "../../api";
import { Button, Empty, ErrorBox, Panel, Spinner } from "../../ui";
import { AgentJobShell, useAgentJob } from "../components";
import { stepStatusLabel } from "../util";

export default function AgentPlanReview(props: { jobId: string }) {
  const { jobId } = props;
  const { job, error, loading, reload } = useAgentJob(jobId);
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

  const decide = async (decision: "approve" | "reject", note: string) => {
    setActionError(null);
    setBusy(true);
    try {
      await approveAgentJob(jobId, decision, "plan", note, null);
      reload();
    } catch (e) {
      setActionError(e as Error);
    } finally {
      setBusy(false);
    }
  };

  const plan = job.plan;

  return (
    <AgentJobShell job={job} active="plan">
      <ErrorBox error={actionError} />
      {!plan || plan.steps.length === 0 ? (
        <Panel title="计划审阅">
          <Empty text="该任务尚未生成计划 (规划器未运行 — 诚实空态)" />
        </Panel>
      ) : (
        <>
          <Panel title={"计划 (v" + plan.version + " · " + plan.steps.length + " 步)"}>
            <table className="data">
              <thead>
                <tr>
                  <th>#</th>
                  <th>标题</th>
                  <th>摘要</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {plan.steps.map((s) => (
                  <tr key={s.index}>
                    <td className="mono">{s.index}</td>
                    <td>{s.title}</td>
                    <td className="muted">{s.summary}</td>
                    <td>
                      <span
                        className={
                          "pill " +
                          (s.status === "approved"
                            ? "pill-ok"
                            : s.status === "rejected"
                            ? "pill-bad"
                            : "pill-mute")
                        }
                      >
                        {stepStatusLabel(s.status)}
                      </span>
                    </td>
                    <td>
                      <a
                        className="btn btn-ghost btn-sm"
                        href={"#/agent/jobs/" + jobId + "/plan/" + s.index}
                      >
                        审阅 Review
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
          <Panel title="整计划决策 Whole-plan decision">
            <div style={{ display: "flex", gap: 8 }}>
              <Button disabled={busy} onClick={() => void decide("approve", "")}>
                批准整个计划 Approve plan
              </Button>
              <Button
                variant="danger"
                disabled={busy}
                onClick={() => {
                  const note = window.prompt("拒绝原因 Rejection note (可选):") || "";
                  void decide("reject", note);
                }}
              >
                拒绝计划 Reject plan
              </Button>
            </div>
            <div className="muted" style={{ marginTop: 8 }}>
              批准 → EXECUTING; 拒绝 → FAILED (原因随审批记录保存)
            </div>
          </Panel>
        </>
      )}
    </AgentJobShell>
  );
}
