import { useState } from "react";
import { approveAgentJob } from "../../api";
import { Button, Empty, ErrorBox, Panel, Spinner, Table } from "../../ui";
import { AgentJobShell, useAgentJob } from "../components";
import { stepStatusLabel } from "../util";
import { storedLocale } from "../../i18n/strings";
const isZh = (): boolean => storedLocale() === "zh";
const L = (zh: string, en: string): string => (isZh() ? zh : en);

export default function AgentPlanReview(props: { jobId: string }) {
  const { jobId } = props;
  const { job, error, loading, reload } = useAgentJob(jobId);
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
        <Panel title={L("计划审阅", "Plan review")}>
          <Empty text={job.status === "FAILED" ? L("规划失败，请查看任务结果中的原因。", "Planning failed — see the failure cause in the task result.") : L("模型正在生成计划，页面会自动更新；当前尚未修改仓库。", "The model is generating the plan; this page auto-updates. No repo changes have been made yet.")} />
        </Panel>
      ) : (
        <>
          <Panel title={L("计划", "Plan") + " (v" + plan.version + " · " + plan.steps.length + L(" 步", " steps") + ")"}>
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
                { key: "title", header: L("标题", "Title"), render: (s) => s.title },
                {
                  key: "summary",
                  header: L("摘要", "Summary"),
                  render: (s) => <span className="muted">{s.summary}</span>,
                },
                {
                  key: "status",
                  header: L("状态", "Status"),
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
                  header: L("操作", "Action"),
                  render: (s) => (
                    <a
                      className="btn btn-ghost btn-sm"
                      href={"#/agent/jobs/" + jobId + "/plan/" + s.index}
                    >
                      {L("审阅", "Review")}
                    </a>
                  ),
                },
              ]}
            />
          </Panel>
          <Panel title={L("整计划决策", "Whole-plan decision")}>
            <div style={{ display: "flex", gap: 8 }}>
              <Button disabled={busy || job.status !== "AWAITING_APPROVAL"} onClick={() => void decide("approve", "")}>
                {L("批准整个计划", "Approve plan")}
              </Button>
              <Button
                variant="danger"
                disabled={busy || job.status !== "AWAITING_APPROVAL"}
                onClick={() => {
                  const note = window.prompt(L("拒绝原因（可选）", "Rejection note (optional)")) || "";
                  void decide("reject", note);
                }}
              >
                {L("拒绝计划", "Reject plan")}
              </Button>
            </div>
            <div className="muted" style={{ marginTop: 8 }}>
              {L("批准 → EXECUTING；拒绝 → FAILED（原因随审批记录保存）", "Approve → EXECUTING; reject → FAILED (the reason is kept with the approval)")}
            </div>
          </Panel>
        </>
      )}
    </AgentJobShell>
  );
}
