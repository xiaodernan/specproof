import { useEffect, useState } from "react";
import { listAgentApprovals } from "../../api";
import { Empty, ErrorBox, Panel, Spinner } from "../../ui";
import { loadFailed } from "../../ui/errorHints";
import { AgentJobShell, ApprovalCard, useAgentJob } from "../components";
import { storedLocale } from "../../i18n/strings";
const isZh = (): boolean => storedLocale() === "zh";
const L = (zh: string, en: string): string => (isZh() ? zh : en);

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
        <ErrorBox error={error || L("任务不存在（404）", "Task not found (404)")} />
        <a href="#/agent">{L("← 返回 Agent 总览", "← Back to Agent overview")}</a>
      </div>
    );
  }

  return (
    <AgentJobShell job={job} active="approvals">
      <Panel title={L("审批记录", "Approvals") + " (" + approvals.length + ")"}>
        {loadFailed(listError) ? (
          <div className="errorbox" role="alert" title={typeof listError === "string" ? listError : listError?.message}>
            {L("审批记录暂时无法加载（请求失败）——这不代表该任务没有审批，请稍后重试。", "The approval log failed to load (request failed); this does not mean the task has none — retry shortly.")}
          </div>
        ) : listError ? (
          <ErrorBox error={listError} />
        ) : approvals.length === 0 ? (
          <Empty text={L("该任务尚无审批记录", "This task has no approvals yet.")} />
        ) : (
          approvals.map((a) => <ApprovalCard key={a.id} approval={a} />)
        )}
      </Panel>
    </AgentJobShell>
  );
}
