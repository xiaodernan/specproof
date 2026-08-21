import { useEffect, useMemo, useState } from "react";
import { apiGet, Job } from "../api";
import { Button, Empty, ErrorBox, Panel, Spinner, StatusPill, fmtTime, shortId } from "../ui";

const PAGE_SIZE = 25;

export default function Jobs() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<Error | string | null>(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [textFilter, setTextFilter] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    let alive = true;
    apiGet<{ jobs: Job[] }>("/jobs?limit=200")
      .then((d) => {
        if (alive) setJobs(d.jobs || []);
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

  const statuses = useMemo(() => {
    const s = new Set<string>();
    jobs.forEach((j) => s.add((j.status || "UNKNOWN").toUpperCase()));
    return ["ALL", ...Array.from(s).sort()];
  }, [jobs]);

  const filtered = useMemo(() => {
    return jobs.filter((j) => {
      if (statusFilter !== "ALL" && (j.status || "UNKNOWN").toUpperCase() !== statusFilter) return false;
      if (textFilter) {
        const hay = ((j.id || "") + " " + (j.repo_path || "") + " " + (j.base_ref || "") + " " + (j.head_ref || "")).toLowerCase();
        if (!hay.includes(textFilter.toLowerCase())) return false;
      }
      return true;
    });
  }, [jobs, statusFilter, textFilter]);

  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageSafe = Math.min(page, pages);
  const pageItems = filtered.slice((pageSafe - 1) * PAGE_SIZE, pageSafe * PAGE_SIZE);

  if (loading) return <Spinner />;

  return (
    <div>
      <div className="page-head">
        <h1>任务 Jobs</h1>
        <div className="page-sub">VERIFICATION JOB QUEUE — 状态筛选 / 分页 / 实时进度</div>
      </div>
      <ErrorBox error={error} />

      <Panel
        title={"任务列表 (" + filtered.length + " / " + jobs.length + ")"}
        right={
          <>
            <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}>
              {statuses.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <input
              type="text"
              placeholder="搜索 repo / ref / id"
              value={textFilter}
              onChange={(e) => { setTextFilter(e.target.value); setPage(1); }}
            />
          </>
        }
      >
        {jobs.length === 0 ? (
          <Empty text="暂无任务 — POST /jobs 提交验证任务后在此可见" />
        ) : pageItems.length === 0 ? (
          <Empty text="筛选无结果 (诚实空态)" />
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>ID</th>
                <th>Repository</th>
                <th>Base → Head</th>
                <th>状态</th>
                <th>重试</th>
                <th>更新时间</th>
              </tr>
            </thead>
            <tbody>
              {pageItems.map((j) => (
                <tr key={j.id} style={{ cursor: "pointer" }} onClick={() => (window.location.hash = "#/jobs/" + j.id)}>
                  <td className="mono">{shortId(j.id)}</td>
                  <td className="muted">{j.repo_path || "—"}</td>
                  <td className="mono">{(j.base_ref || "—") + " → " + (j.head_ref || "—")}</td>
                  <td><StatusPill status={j.status || ""} /></td>
                  <td className="mono">{j.retry_count ?? 0}</td>
                  <td className="muted">{fmtTime(j.updated_at || j.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {filtered.length > PAGE_SIZE ? (
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12 }}>
            <Button variant="ghost" size="sm" disabled={pageSafe <= 1} onClick={() => setPage(pageSafe - 1)}>
              上一页
            </Button>
            <span className="muted mono">
              {pageSafe} / {pages}
            </span>
            <Button variant="ghost" size="sm" disabled={pageSafe >= pages} onClick={() => setPage(pageSafe + 1)}>
              下一页
            </Button>
          </div>
        ) : null}
      </Panel>
    </div>
  );
}
