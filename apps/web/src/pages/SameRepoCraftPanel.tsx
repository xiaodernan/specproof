// Phase 3.4 (开发与验收链路缝合): from a verification job's detail page, the
// AI-development jobs recorded for the SAME repository path are one click
// away. The join key is the repo path — there is no foreign key between the
// two lanes — and since §30.2 持久化关联 the path lives as a durable,
// separator-normalized agent_jobs.repo_path column: this panel asks the
// server to filter on it (one request, no client-side filtering) instead of
// matching over the first page of an uncapped list with in-process metadata
// that a restart forgot. Rows created before the column existed carry no
// durable path and are honestly absent here — the note says so.
import { useEffect, useState } from "react";

import { listAgentJobs, type AgentJobSummary } from "../api";
import { agentStatusMeta } from "../agent/util";
import { Empty, ErrorBox, Panel, Spinner, Table, fmtTime, shortId } from "../ui";

export function SameRepoCraftPanel(props: { repoPath?: string | null }) {
  const repoPath = props.repoPath || "";
  const [jobs, setJobs] = useState<AgentJobSummary[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!repoPath) return;
    let alive = true;
    setJobs(null);
    setFailed(false);
    listAgentJobs(undefined, repoPath)
      .then((res) => {
        if (!alive) return;
        // The server matched on the durable repo_path column; no client-side filter.
        setJobs(res.jobs);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, [repoPath]);

  if (!repoPath) return null;

  const columns = [
    {
      key: "task",
      header: "开发任务",
      render: (j: AgentJobSummary) => (
        <a href={"#/agent/jobs/" + encodeURIComponent(j.id)} title={j.id}>
          {j.task_name || shortId(j.id)}
        </a>
      ),
    },
    {
      key: "status",
      header: "状态",
      render: (j: AgentJobSummary) => {
        const meta = agentStatusMeta(j.status);
        return <span className="pill pill-mute" title={j.status}>{meta.label}</span>;
      },
    },
    {
      key: "created_at",
      header: "创建时间",
      render: (j: AgentJobSummary) => <span className="muted">{fmtTime(j.created_at)}</span>,
    },
  ];

  return (
    <Panel title="AI 开发任务（同仓库）">
      <p className="muted" style={{ marginTop: 0 }}>
        开发任务创建时登记的仓库路径（已归一分隔符，大小写不作归一）与本仓库
        <code>{repoPath}</code> 持久化匹配，重启后依然可查。两条链路之间没有
        外键，这里不是因果断言，只是同一仓库的工作对照；在本字段启用前创建的
        旧记录可能没有登记路径，因而不在此列出。
      </p>
      {failed ? (
        <ErrorBox error="开发任务列表暂时无法读取（请求失败）— 这不代表没有同仓库任务，请稍后重试。" />
      ) : jobs === null ? (
        <Spinner />
      ) : jobs.length === 0 ? (
        <Empty text="同仓库路径下没有开发任务记录。" />
      ) : (
        <Table columns={columns} rows={jobs} rowKey={(j: AgentJobSummary) => j.id} />
      )}
    </Panel>
  );
}
