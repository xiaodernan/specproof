import { useEffect, useMemo, useRef, useState } from "react";
import { apiGet, type Job, type JobsPage } from "../api";
import { Button, ErrorBox, JOB_STATUSES, Panel, Spinner, StatusPill, statusLabel, Table, fmtTime, shortId } from "../ui";
import "../styles/verification.css";
import { useI18n } from "../i18n";
import { JOBS_BY_LOCALE } from "./jobs.copy";

const PAGE_SIZE = 25;
const ACTIVE = new Set(["QUEUED", "RUNNING", "PENDING", "WAITING_FOR_PROVIDER", "FAILED"]);

/** Display name for a job: the last path segment of repo_path. */
export default function Jobs() {
  const { locale } = useI18n();
  const c = JOBS_BY_LOCALE[locale];
  const repoName = (job: Job): string => {
    const fromPath = (job.repo_path || "").replace(/[\/]$/, "").split(/[\/]/).pop();
    return fromPath || c.unnamedRepo;
  };
  const [jobs, setJobs] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<Error | string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [textFilter, setTextFilter] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  // The keyset position of each visited page (#1618), keyed by the page
  // number: cursors[2] is the cursor that FETCHES page 2 (page 1 has none).
  // Paging back and forth therefore costs the same as paging forward -- the
  // server never discards the rows before the page.
  const [cursors, setCursors] = useState<Record<number, string | undefined>>({});
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const activeRef = useRef(false);
  // WHEN this page's rows were read. The page polls on its own, so without
  // this the reader cannot tell a fresh list from a stale one -- and on a
  // verification list "is this current?" is the first question.
  const [lastLoadedAt, setLastLoadedAt] = useState<string | null>(null);

  useEffect(() => {
    if (textFilter.trim() === query) return;
    const timer = window.setTimeout(() => {
      setQuery(textFilter.trim());
      setPage(1);
      setCursors({});
    }, 300);
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
      const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
      const cursor = cursors[page];
      if (cursor) params.set("cursor", cursor);
      else params.set("offset", String((page - 1) * PAGE_SIZE));
      if (statusFilter !== "ALL") params.set("status", statusFilter);
      if (query) params.set("q", query);
      try {
        const data = await apiGet<JobsPage>("/jobs?" + params.toString(), controller.signal);
        if (!alive) return;
        setJobs(data.jobs || []);
        // `total` is required by the shared type, so there is no fallback to
        // fall back to: the page either shows the server's count or the request
        // failed. Substituting the window length here would have printed the
        // page size (25) as if it were the number of matching verifications.
        setTotal(data.total);
        setNextCursor(data.next_cursor ?? null);
        setLastLoadedAt(new Date().toISOString());
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
    // A search term is a FULL SCAN on the server (the filter is four LOCATE
    // calls per row and no index can serve it), so polling it every ten
    // seconds turns the page into a load generator against the production
    // table. The searched view polls three times slower; the unfiltered one
    // -- which the composite index serves -- keeps the quick rhythm.
    const pollMs = query ? 30_000 : 10_000;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible" && activeRef.current) void load(true);
    }, pollMs);
    return () => { alive = false; controller.abort(); window.clearInterval(timer); };
  }, [page, query, statusFilter, refresh, cursors]);

  const summary = useMemo(() => ({
    active: jobs.filter((j) => ACTIVE.has((j.status || "").toUpperCase())).length,
    verified: jobs.filter((j) => (j.status || "").toUpperCase() === "VERIFIED").length,
    attention: jobs.filter((j) => ["FAILED", "BLOCKED", "ERROR"].includes((j.status || "").toUpperCase())).length,
  }), [jobs]);
  // The total-based page count stays for the "N / M" readout; whether a NEXT
  // page exists is decided by the server's cursor, not by the arithmetic.
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="verification-page">
      <div className="page-head verification-heading">
        <div><span className="verification-eyebrow">{c.eyebrow}</span><h1>{c.title}</h1><p className="verification-description">{c.description}</p></div>
        <Button variant="primary" size="lg" onClick={() => { window.location.hash = "#/jobs/new"; }}>{c.newButton}</Button>
      </div>
      <div className="verification-summary" aria-label={c.summaryAria}>
        <div><strong>{total}</strong><span>{c.summaryMatched}</span></div>
        <div><strong>{summary.active}</strong><span>{c.summaryActive}</span></div>
        <div><strong>{summary.verified}</strong><span>{c.summaryVerified}</span></div>
        <div><strong>{summary.attention}</strong><span>{c.summaryAttention}</span></div>
      </div>
      <ErrorBox error={error} />
      <Panel title={c.panelTitle} right={<div className="verification-toolbar">
        <input className="ui-input" aria-label={c.searchAria} type="search" maxLength={256} placeholder={c.searchPlaceholder} value={textFilter} onChange={(e) => setTextFilter(e.target.value)} />
        <select className="ui-select" aria-label={c.statusAria} value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); setCursors({}); }}>
          <option value="ALL">{c.allStatuses}</option>{JOB_STATUSES.map((value) => <option key={value} value={value}>{statusLabel(value)}</option>)}
        </select>
        <Button variant="ghost" size="sm" loading={refreshing} onClick={() => setRefresh((value) => value + 1)}>{c.refresh}</Button>
        {lastLoadedAt ? (
          <span className="verification-freshness" title={c.freshnessTitle}>
            {c.freshnessLabel} {new Date(lastLoadedAt).toLocaleTimeString()}
          </span>
        ) : null}
      </div>}>
        {loading ? <Spinner /> : jobs.length === 0 ? (
          <div className="verification-empty"><span aria-hidden="true">◎</span><h3>{error ? c.errorReadTitle : query || statusFilter !== "ALL" ? c.queryEmptyTitle : c.firstEmptyTitle}</h3>
            <p>{error ? c.errorCopy : query || statusFilter !== "ALL" ? c.queryEmptyCopy : c.firstEmptyCopy}</p>
            {query || statusFilter !== "ALL" ? <Button onClick={() => { setTextFilter(""); setQuery(""); setStatusFilter("ALL"); setPage(1); setCursors({}); }}>{c.clearFilters}</Button> : !error ? <Button variant="primary" onClick={() => { window.location.hash = "#/jobs/new"; }}>{c.emptyAction}</Button> : null}
          </div>
        ) : <div className="verification-table-wrap">
          <Table
            rows={jobs}
            rowKey={(job) => job.id}
            columns={[
              {
                key: "repo",
                header: c.thRepo,
                sortable: true,
                sortValue: (job) => repoName(job),
                render: (job) => (
                  <>
                    <a className="verification-repo" href={"#/jobs/" + encodeURIComponent(job.id)} title={job.repo_path}>
                      {repoName(job)}
                    </a>
                    {job.is_demo ? <span className="demo-label">{c.demoLabel}</span> : null}
                    <span className="verification-job-id">{shortId(job.id)}</span>
                  </>
                ),
              },
              {
                key: "refs",
                header: c.thRefs,
                render: (job) => (
                  <span className="mono">
                    {job.base_ref || "—"} <span className="muted">→</span> {job.head_ref || "—"}
                  </span>
                ),
              },
              {
                key: "status",
                header: c.thStatus,
                sortable: true,
                sortValue: (job) => statusLabel(job.status) || "c.statusUnknown",
                render: (job) => (
                  // The pill already renders the canonical label; a second
                  // plain-text label is redundant and was allowed to drift.
                  <StatusPill status={job.status || ""} />
                ),
              },
              {
                key: "updated",
                header: c.thUpdated,
                sortable: true,
                sortValue: (job) => job.updated_at || job.created_at || "",
                render: (job) => <span className="muted">{fmtTime(job.updated_at || job.created_at)}</span>,
              },
              {
                key: "actions",
                header: "",
                align: "right",
                render: (job) => (
                  <a href={"#/jobs/" + encodeURIComponent(job.id)} aria-label={c.ariaView + shortId(job.id)}>
                    {c.viewLink}
                  </a>
                ),
              },
            ]}
          />
        </div>}
        {total > PAGE_SIZE ? <div className="verification-pagination"><span>{c.paginationTotal(total)}</span><div><Button variant="ghost" size="sm" disabled={page <= 1 || refreshing} onClick={() => setPage((value) => value - 1)}>{c.previousPage}</Button><span>{page} / {pages}</span><Button variant="ghost" size="sm" disabled={!nextCursor || refreshing} onClick={() => { if (!nextCursor) return; setCursors((prev) => ({ ...prev, [page + 1]: nextCursor })); setPage((value) => value + 1); }}>{c.nextPage}</Button></div></div> : null}
      </Panel>
    </div>
  );
}
