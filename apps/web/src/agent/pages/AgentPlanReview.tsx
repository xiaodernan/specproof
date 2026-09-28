import { useState } from "react";
import { approveAgentJob } from "../../api";
import { Button, Empty, ErrorBox, Panel, Spinner, Table } from "../../ui";
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
          <Empty text={job.status === "FAILED" ? "规划失败，请查看任务结果中的原因。" : "模型正在生成计划，页面会自动更新；当前尚未修改仓库。"} />
        </Panel>
      ) : (
        <>
          <Panel title={"计划 (v" + plan.version + " · " + plan.steps.length + " 步)"}>
            {/* Through the shared table (#122): 摘要 is free text written by the
                model, and a hand-rolled <td> had no container to scroll in, so
                one long summary widened the whole page instead of the panel. */}
            <Table
              rows={plan.steps}
              rowKey={(s) => String(s.index)}
              columns={[
                {
                  key: "index",
                  header: "#",
                  width: 56,
                  render: (s) => <span className="mono">{s.index}</span>,
                },
                { key: "title", header: "标题", render: (s) => s.title },
                {
                  key: "summary",
                  header: "摘要",
                  render: (s) => <span className="muted">{s.summary}</span>,
                },
                {
                  key: "status",
                  header: "状态",
                  render: (s) => (
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
                  ),
                },
                {
                  key: "review",
                  header: "操作",
                  render: (s) => (
                    <a
                      className="btn btn-ghost btn-sm"
                      href={"#/agent/jobs/" + jobId + "/plan/" + s.index}
                    >
                      审阅 Review
                    </a>
                  ),
                },
              ]}
            />
          </Panel>
          <Panel title="整计划决策 Whole-plan decision">
            <div style={{ display: "flex", gap: 8 }}>
              <Button disabled={busy || job.status !== "AWAITING_APPROVAL"} onClick={() => void decide("approve", "")}>
                批准整个计划 Approve plan
              </Button>
              <Button
                variant="danger"
                disabled={busy || job.status !== "AWAITING_APPROVAL"}
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
