import { useState } from "react";
import { approveAgentJob, listAgentApprovals } from "../../api";
import { Empty, ErrorBox, Panel, Spinner } from "../../components";
import { AgentJobShell, ApprovalCard, useAgentJob } from "../components";

function useGateData(jobId: string) {
  const [approvals, setApprovals] = useState<import("../../api").AgentApproval[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reload = () => {
    let alive = true;
    listAgentApprovals(jobId)
      .then((d) => {
        if (alive) setApprovals(d.approvals.filter((a) => a.target === "gate"));
      })
      .catch((e) => {
        if (alive) setError(e instanceof Error ? e.message : String(e));
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
      <Panel title={"门禁审批 Gate approvals (" + gate.approvals.length + ")"}>
        {gate.error ? <div className="errorbox">{gate.error}</div> : null}
        {gate.approvals.length === 0 ? (
          <Empty text="尚无门禁审批记录" />
        ) : (
          gate.approvals.map((a) => <ApprovalCard key={a.id} approval={a} />)
        )}
        <div style={{ marginTop: 12 }}>
          <label className="field">门禁备注 Gate note (可选)</label>
          <input type="text" value={note} onChange={(e) => setNote(e.target.value)} />
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <button className="btn" disabled={busy} onClick={() => void decide("approve")}>
              通过门禁 Approve gate
            </button>
            <button className="btn btn-danger" disabled={busy} onClick={() => void decide("reject")}>
              拒绝门禁 Reject gate
            </button>
          </div>
          <div className="muted" style={{ marginTop: 8 }}>
            通过 → COMPLETED; 拒绝 → FAILED。
          </div>
        </div>
      </Panel>
    </AgentJobShell>
  );
}
