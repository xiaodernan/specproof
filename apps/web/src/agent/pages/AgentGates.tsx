import { useState } from "react";
import { approveAgentJob, listAgentApprovals } from "../../api";
import { Button, Empty, ErrorBox, Panel, Spinner } from "../../ui";
import { loadFailed } from "../../ui/errorHints";
import { AgentJobShell, ApprovalCard, useAgentJob } from "../components";

function useGateData(jobId: string) {
  const [approvals, setApprovals] = useState<import("../../api").AgentApproval[]>([]);
  const [error, setError] = useState<Error | string | null>(null);

  const reload = () => {
    let alive = true;
    listAgentApprovals(jobId)
      .then((d) => {
        if (alive) setApprovals(d.approvals.filter((a) => a.target === "gate"));
      })
      .catch((e) => {
        if (alive) setError(e as Error | string);
      });
    return () => {
      alive = false;
    };
  };
  return { approvals, error, reload };
}

export default function AgentGates(props: { jobId: string }) {
  const { jobId } = props;
  const { job, error, loading, reload: reloadJob } = useAgentJob(jobId);
  const gate = useGateData(jobId);
  const [actionError, setActionError] = useState<Error | string | null>(null);
  const [note, setNote] = useState("");
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

  const decide = async (decision: "approve" | "reject") => {
    setActionError(null);
    setBusy(true);
    try {
      await approveAgentJob(jobId, decision, "gate", note.trim(), null);
      reloadJob();
      gate.reload();
    } catch (e) {
      setActionError(e as Error);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AgentJobShell job={job} active="gates">
      <ErrorBox error={actionError} />
      {job.execution_mode ? <Panel title="实际检查结果"><p>此任务的完成状态由执行器和真实检查决定。</p><a href={"#/agent/jobs/" + jobId + "/result"}>查看执行结果与门禁报告 →</a></Panel> :
      <Panel title={"门禁审批 Gate approvals (" + gate.approvals.length + ")"}>
        {loadFailed(gate.error) ? (
          <div className="errorbox" role="alert" title={typeof gate.error === "string" ? gate.error : gate.error?.message}>
            门禁审批暂时无法加载（请求失败）— 这不代表没有门禁审批，请稍后重试。
          </div>
        ) : gate.error ? (
          <ErrorBox error={gate.error} />
        ) : gate.approvals.length === 0 ? (
          <Empty text="尚无门禁审批记录" />
        ) : (
          gate.approvals.map((a) => <ApprovalCard key={a.id} approval={a} />)
        )}
        <div style={{ marginTop: 12 }}>
          <label className="field" htmlFor="gate-note">门禁备注 Gate note (可选)</label>
          <input id="gate-note" type="text" value={note} onChange={(e) => setNote(e.target.value)} />
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <Button disabled={busy} onClick={() => void decide("approve")}>
              通过门禁 Approve gate
            </Button>
            <Button variant="danger" disabled={busy} onClick={() => void decide("reject")}>
              拒绝门禁 Reject gate
            </Button>
          </div>
          <div className="muted" style={{ marginTop: 8 }}>
            通过 → COMPLETED; 拒绝 → FAILED。
          </div>
        </div>
      </Panel>}
    </AgentJobShell>
  );
}
