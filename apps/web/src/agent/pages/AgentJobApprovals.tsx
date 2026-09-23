import { useEffect, useState } from "react";
import { listAgentApprovals } from "../../api";
import { Empty, ErrorBox, Panel, Spinner } from "../../ui";
import { loadFailed } from "../../ui/errorHints";
import { AgentJobShell, ApprovalCard, useAgentJob } from "../components";

export default function AgentJobApprovals(props: { jobId: string }) {
  const { jobId } = props;
  const { job, error, loading } = useAgentJob(jobId);
  const [approvals, setApprovals] = useState<
    import("../../api").AgentApproval[]
  >([]);
  const [listError, setListError] = useState<Error | string | null>(null);

  useEffect(() => {
    let alive = true;
    listAgentApprovals(jobId)
      .then((d) => {
        if (alive) setApprovals(d.approvals);
      })
      .catch((e) => {
        if (alive) setListError(e as Error | string);
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

  return (
    <AgentJobShell job={job} active="approvals">
      <Panel title={"审批记录 Approvals (" + approvals.length + ")"}>
        {loadFailed(listError) ? (
          <div className="errorbox" role="alert" title={typeof listError === "string" ? listError : listError?.message}>
            审批记录暂时无法加载（请求失败）— 这不代表该任务没有审批，请稍后重试。
          </div>
        ) : listError ? (
          <ErrorBox error={listError} />
        ) : approvals.length === 0 ? (
          <Empty text="该任务尚无审批记录" />
        ) : (
          approvals.map((a) => <ApprovalCard key={a.id} approval={a} />)
        )}
      </Panel>
    </AgentJobShell>
  );
}
