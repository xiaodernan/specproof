import { useEffect, useState } from "react";
import { AgentApproval, listAgentApprovals, listAgentJobs } from "../../api";
import { ErrorBox, Panel, Spinner } from "../../components";
import { ApprovalCard } from "../components";
import { aggregateApprovals } from "../util";

export default function AgentApprovalDetail(props: { approvalId: string }) {
  const { approvalId } = props;
  const [approval, setApproval] = useState<AgentApproval | null>(null);
  const [error, setError] = useState<Error | string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    listAgentJobs()
      .then(async (d) => {
        const perJob = await Promise.all(
          (d.jobs || []).map((j) =>
            listAgentApprovals(j.id)
              .then((r) => ({ job_id: j.id, approvals: r.approvals }))
              .catch(() => ({ job_id: j.id, approvals: [] as AgentApproval[] }))
          )
        );
        const found = aggregateApprovals(perJob).find((a) => a.id === approvalId);
        if (alive) setApproval(found || null);
      })
      .catch((e) => {
        if (alive) setError(e as Error);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [approvalId]);

  if (loading) return <Spinner />;

  return (
    <div>
      <div className="page-head">
        <h1>审批详情 Approval detail</h1>
        <div className="page-sub mono">{approvalId}</div>
      </div>
      <ErrorBox error={error} />
      <Panel title="记录 Record">
        {!approval ? (
          <div className="errorbox">审批记录不存在 (可能已被清理 — 诚实 404 空态)</div>
        ) : (
          <>
            <ApprovalCard approval={approval} />
            <div style={{ marginTop: 12 }}>
              <a className="btn btn-ghost btn-sm" href={"#/agent/jobs/" + approval.job_id}>
                打开任务 Open job
              </a>
            </div>
          </>
        )}
      </Panel>
    </div>
  );
}
