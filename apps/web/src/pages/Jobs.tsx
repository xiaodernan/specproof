import { useEffect, useMemo, useRef, useState } from "react";
import { apiGet, type Job } from "../api";
import { Button, ErrorBox, Panel, STATUS_LABELS, Spinner, StatusPill, statusLabel, Table, fmtTime, shortId } from "../ui";
import "../styles/verification.css";

const PAGE_SIZE = 25;
const ACTIVE = new Set(["QUEUED", "RUNNING", "PENDING", "WAITING_FOR_PROVIDER", "FAILED"]);
interface JobsPage { jobs: Job[]; total?: number; }

/** 仓库路径 → 展示名（取最后一段目录名）。 */
function repoName(job: Job): string {
  return (job.repo_path || "未命名项目").replace(/[\\/]$/, "").split(/[\\/]/).pop() || "未命名项目";
}

export default function Jobs() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<Error | string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [textFilter, setTextFilter] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const activeRef = useRef(false);

  useEffect(() => {
    if (textFilter.trim() === query) return;
    const timer = window.setTimeout(() => { setQuery(textFilter.trim()); setPage(1); }, 300);
    return () => window.clearTimeout(timer);
  }, [textFilter, query]);

  useEffect(() => {
    let alive = true;
    let inFlight = false;
    const controller = new AbortController();
    const load = async (silent = false) => {
      if (inFlight) return;
      inFlight = true;
      if (!silent) setRefreshing(true);
      const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String((page - 1) * PAGE_SIZE) });
      if (statusFilter !== "ALL") params.set("status", statusFilter);
      if (query) params.set("q", query);
      try {
        const data = await apiGet<JobsPage>("/jobs?" + params.toString(), controller.signal);
        if (!alive) return;
        setJobs(data.jobs || []);
        setTotal(data.total ?? data.jobs?.length ?? 0);
        activeRef.current = (data.jobs || []).some((job) => ACTIVE.has((job.status || "").toUpperCase()));
        setError(null);
      } catch (e) {
        if (alive) setError(e as Error);
      } finally {
        inFlight = false;
        if (alive) { setLoading(false); setRefreshing(false); }
      }
    };
    void load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible" && activeRef.current) void load(true);
    }, 10000);
    return () => { alive = false; controller.abort(); window.clearInterval(timer); };
  }, [page, query, statusFilter, refresh]);

  const summary = useMemo(() => ({
    active: jobs.filter((j) => ACTIVE.has((j.status || "").toUpperCase())).length,
    verified: jobs.filter((j) => (j.status || "").toUpperCase() === "VERIFIED").length,
    attention: jobs.filter((j) => ["FAILED", "BLOCKED", "ERROR"].includes((j.status || "").toUpperCase())).length,
  }), [jobs]);
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="verification-page">
      <div className="page-head verification-heading">
        <div><span className="verification-eyebrow">VERIFICATION HISTORY</span><h1>每次变更，都有依据。</h1><p className="verification-description">跟进代码验证，查看需求覆盖与风险证据。执行中的任务会自动更新。</p></div>
        <Button variant="primary" size="lg" onClick={() => { window.location.hash = "#/jobs/new"; }}>＋ 新建验证</Button>
      </div>
      <div className="verification-summary" aria-label="当前页任务概况">
        <div><strong>{total}</strong><span>符合筛选的验证</span></div>
        <div><strong>{summary.active}</strong><span>本页进行中</span></div>
        <div><strong>{summary.verified}</strong><span>本页通过</span></div>
        <div><strong>{summary.attention}</strong><span>本页需关注</span></div>
      </div>
      <ErrorBox error={error} />
      <Panel title="验证记录" right={<div className="verification-toolbar">
        <input aria-label="搜索验证" type="search" maxLength={256} placeholder="搜索项目、分支或任务编号" value={textFilter} onChange={(e) => setTextFilter(e.target.value)} />
        <select aria-label="验证状态" value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}>
          <option value="ALL">全部状态</option>{Object.entries(STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <Button variant="ghost" size="sm" loading={refreshing} onClick={() => setRefresh((value) => value + 1)}>刷新</Button>
      </div>}>
        {loading ? <Spinner /> : jobs.length === 0 ? (
          <div className="verification-empty"><span aria-hidden="true">◎</span><h3>{error ? "暂时无法读取验证记录" : query || statusFilter !== "ALL" ? "没有找到符合条件的验证" : "从第一次验证开始"}</h3>
            <p>{error ? "请确认服务连接，稍后点击刷新重试。" : query || statusFilter !== "ALL" ? "换个关键词，或清除筛选条件查看全部记录。" : "准备一个 Git 仓库和需求文件，比较两个版本，了解代码改动是否满足预期。"}</p>
            {query || statusFilter !== "ALL" ? <Button onClick={() => { setTextFilter(""); setQuery(""); setStatusFilter("ALL"); setPage(1); }}>清除筛选</Button> : !error ? <Button variant="primary" onClick={() => { window.location.hash = "#/jobs/new"; }}>创建第一次验证 →</Button> : null}
          </div>
        ) : <div className="verification-table-wrap">
          <Table
            rows={jobs}
            rowKey={(job) => job.id}
            columns={[
              {
                key: "repo",
                header: "项目 / 验证编号",
                sortable: true,
                sortValue: (job) => repoName(job),
                render: (job) => (
                  <>
                    <a className="verification-repo" href={"#/jobs/" + encodeURIComponent(job.id)} title={job.repo_path}>
                      {repoName(job)}
                    </a>
                    {!!job.is_demo && <span className="demo-label">演示</span>}
                    <span className="verification-job-id">{shortId(job.id)}</span>
                  </>
                ),
              },
              {
                key: "refs",
                header: "比较版本",
                render: (job) => (
                  <span className="mono">
                    {job.base_ref || "—"} <span className="muted">→</span> {job.head_ref || "—"}
                  </span>
                ),
              },
              {
                key: "status",
                header: "验证状态",
                sortable: true,
                sortValue: (job) => statusLabel(job.status) || "状态未知",
                render: (job) => (
                  // The pill already renders the canonical label; a second
                  // plain-text label is redundant and was allowed to drift.
                  <StatusPill status={job.status || ""} />
                ),
              },
              {
                key: "updated",
                header: "更新时间",
                sortable: true,
                sortValue: (job) => job.updated_at || job.created_at || "",
                render: (job) => <span className="muted">{fmtTime(job.updated_at || job.created_at)}</span>,
              },
              {
                key: "actions",
                header: "",
                align: "right",
                render: (job) => (
                  <a href={"#/jobs/" + encodeURIComponent(job.id)} aria-label={"查看验证 " + shortId(job.id)}>
                    查看 →
                  </a>
                ),
              },
            ]}
          />
        </div>}
        {total > PAGE_SIZE ? <div className="verification-pagination"><span>共 {total} 条验证</span><div><Button variant="ghost" size="sm" disabled={page <= 1 || refreshing} onClick={() => setPage((value) => value - 1)}>上一页</Button><span>{page} / {pages}</span><Button variant="ghost" size="sm" disabled={page >= pages || refreshing} onClick={() => setPage((value) => value + 1)}>下一页</Button></div></div> : null}
      </Panel>
    </div>
  );
}
