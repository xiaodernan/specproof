import { useEffect, useState } from "react";
import { AgentApproval, AgentJobSummary, listAgentApprovals, listAgentJobs } from "../../api";
import { Empty, ErrorBox, Panel, Spinner, fmtTime, shortId } from "../../ui";
import { loadFailed } from "../../ui/errorHints";
import { ApprovalCard } from "../components";
import { aggregateApprovals, approvalDecisionLabel } from "../util";

export default function AgentApprovalsInbox() {
  const [approvals, setApprovals] = useState<AgentApproval[]>([]);
  const [jobs, setJobs] = useState<AgentJobSummary[]>([]);
  const [error, setError] = useState<Error | string | null>(null);
  const [failedJobReads, setFailedJobReads] = useState(0);
  const [loading, setLoading] = useState(true);
  const [decisionFilter, setDecisionFilter] = useState("ALL");

  useEffect(() => {
    let alive = true;
    listAgentJobs()
      .then(async (d) => {
        const list = d.jobs || [];
        const perJob = await Promise.all(
          list.map((j) =>
            listAgentApprovals(j.id)
              .then((r) => ({ job_id: j.id, approvals: r.approvals }))
              .catch(() => {
                if (alive) setFailedJobReads((n) => n + 1);
                return { job_id: j.id, approvals: [] as AgentApproval[] };
              })
          )
        );
        if (!alive) return;
        setJobs(list);
        setApprovals(aggregateApprovals(perJob));
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
  }, []);

  if (loading) return <Spinner />;

  const label = jobs.reduce((acc: Record<string, string>, j) => {
    acc[j.id] = j.task_name;
    return acc;
  }, {});

  const filtered =
    decisionFilter === "ALL"
      ? approvals
      : approvals.filter((a) => a.decision === decisionFilter);

  return (
    <div>
      <div className="page-head">
        <h1>审批收件箱 Approvals inbox</h1>
        <div className="page-sub">
          跨任务审批记录 (计划/步骤/门禁) — 按时间倒序
        </div>
      </div>
      <ErrorBox error={error} />
      <Panel
        title={"审批 (" + filtered.length + " / " + approvals.length + ")"}
        right={
          <select
            aria-label="按处理状态筛选 Filter by decision"
            value={decisionFilter}
            onChange={(e) => setDecisionFilter(e.target.value)}
          >
            {["ALL", "approve", "reject"].map((s) => (
              <option key={s} value={s}>
                {s === "ALL" ? "全部决策 All" : approvalDecisionLabel(s)}
              </option>
            ))}
          </select>
        }
      >
        {loadFailed(error) ? (
          <div className="errorbox" role="alert">
            审批列表暂时无法加载（请求失败）— 这不代表没有审批，请稍后重试。
          </div>
        ) : filtered.length === 0 ? (
          failedJobReads > 0 ? (
            <div className="errorbox" role="alert">
              有 {failedJobReads} 个任务的审批无法读取（请求失败）— 这不代表没有审批，请稍后重试。
            </div>
          ) : (
            <Empty text="尚无审批记录 — 计划审阅/步骤审阅/门禁的每个决策都会出现在这里" />
          )
        ) : (
          <>
            {failedJobReads > 0 && (
              <div className="errorbox" role="alert">
                有 {failedJobReads} 个任务的审批无法读取，列表可能不完整。
              </div>
            )}
            {filtered.map((a) => (
            <div key={a.id} className="inbox-row">
              <a href={"#/agent/approvals/" + a.id} style={{ flex: 1, textDecoration: "none" }}>
                <ApprovalCard approval={a} jobLabel={(label[a.job_id] || shortId(a.job_id)) + " · " + fmtTime(a.created_at)} />
              </a>
              <a className="btn btn-ghost btn-sm" href={"#/agent/jobs/" + a.job_id}>
                打开任务
              </a>
            </div>
          ))}
          </>
        )}
      </Panel>
    </div>
  );
}
