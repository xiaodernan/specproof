import { useEffect, useState } from "react";
import { listAgentApprovals } from "../../api";
import { Empty, ErrorBox, Panel, Spinner } from "../../components";
import { AgentJobShell, ApprovalCard, useAgentJob } from "../components";

export default function AgentResult(props: { jobId: string }) {
  const { jobId } = props;
  const { job, error, loading } = useAgentJob(jobId);
  const [gateApprovals, setGateApprovals] = useState<
    import("../../api").AgentApproval[]
  >([]);

  useEffect(() => {
    let alive = true;
    listAgentApprovals(jobId)
      .then((d) => {
        if (alive) setGateApprovals(d.approvals.filter((a) => a.target === "gate"));
      })
      .catch(() => {
        // approvals are auxiliary; the job result stays the source of truth
      });
    return () => {
      alive = false;
    };
  }, [jobId]);

  if (loading) return <Spinner />;
  if (!job) {
    return (
      <div>
        <ErrorBox error={error || "任务不存在 (404)"} />
        <a href="#/agent">← 返回 Agent 总览</a>
      </div>
    );
  }

  const result = job.result;
  const verdictTone =
    job.status === "COMPLETED" ? "ok" : job.status === "FAILED" ? "bad" : "mute";

  return (
    <AgentJobShell job={job} active="result">
      <Panel title="最终结果 Result">
        {!result ? (
          <Empty text="任务尚未进入终态 (无 result — 诚实空态)" />
        ) : (
          <>
            <div className="kv">
              <span className="kv-label">判定 Verdict</span>
              <span className="kv-value">
                <span className={"pill pill-" + (verdictTone === "ok" ? "ok" : verdictTone === "bad" ? "bad" : "mute")}>
                  {result.verdict}
                </span>
              </span>
            </div>
            {result.reason ? (
              <div className="kv">
                <span className="kv-label">原因 Reason</span>
                <span className="kv-value">{result.reason}</span>
              </div>
            ) : null}
            <div className="kv">
              <span className="kv-label">状态 Status</span>
              <span className="kv-value mono">{job.status}</span>
            </div>
            <pre className="json">{JSON.stringify(result, null, 2)}</pre>
          </>
        )}
      </Panel>
      <Panel title={"门禁决策 Gate decisions (" + gateApprovals.length + ")"}>
        {gateApprovals.length === 0 ? (
          <Empty text="无门禁审批记录" />
        ) : (
          gateApprovals.map((a) => <ApprovalCard key={a.id} approval={a} />)
        )}
      </Panel>
    </AgentJobShell>
  );
}
