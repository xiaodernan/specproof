// Phase 3.4 (开发与验收链路缝合): from a verification job's detail page, the
// AI-development jobs recorded for the SAME repository path are one click
// away. The join key is the exact repo path — there is no foreign key
// between the two lanes — so the panel says exactly that, and the metadata
// it matches on is recorded by the running service process (agent console
// meta), which the note states instead of implying a permanent relation.
import { useEffect, useState } from "react";

import { listAgentJobs, type AgentJobSummary } from "../api";
import { agentStatusMeta } from "../agent/util";
import { Empty, ErrorBox, Panel, Spinner, Table, fmtTime, shortId } from "../ui";

function normalizeRepoPath(path: string): string {
  // Windows paths mix separators AND double them (a JSX string attribute
  // passes backslashes through verbatim, so "D:\\repo" really carries two).
  // Collapsing runs of separators to one "/" is the robust normal form;
  // case is left alone — an exact-name mismatch is a real difference the
  // reader can see in the note, not something to hide.
  return path.replace(/[\\/]+/g, "/").replace(/\/+$/, "");
}

export function SameRepoCraftPanel(props: { repoPath?: string | null }) {
  const repoPath = props.repoPath || "";
  const [jobs, setJobs] = useState<AgentJobSummary[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!repoPath) return;
    let alive = true;
    setJobs(null);
    setFailed(false);
    listAgentJobs()
      .then((res) => {
        if (!alive) return;
        const wanted = normalizeRepoPath(repoPath);
        setJobs(
          res.jobs.filter(
            (j) => normalizeRepoPath(j.repo_path || "") === wanted,
          ),
        );
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
        按仓库路径精确匹配本次验证的 <code>{repoPath}</code>，仅涵盖本服务
        进程记录的开发任务元数据（最近列表内）；两条链路之间没有外键，这里
        不是因果断言，只是同一仓库的工作对照。
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
