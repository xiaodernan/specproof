import { useEffect, useState } from "react";
import {
  apiGet, CertificateData, downloadCapsule, Finding, FindingsData, Invoice, Job, openProgressStream,
  ProgressEvent, StagesData,
  getInvoiceByPeriod, transitionInvoiceStatus,
  streamAiSummary, type AiSummary,
} from "../api";
import {
  Breadcrumbs, Button, Degraded, Empty, ErrorBox, Panel, PreflightCard, Progress, Spinner, StatCard, StatusPill, Table, Term,
  fmtPct, fmtTime, fmtDurationSeconds, kv, shortId, severityPill, severityHint, severityRank, evidenceLabel, stageLabel, verdictTone, verdictLabel,
  type Column, type PreflightResult,
} from "../ui";
import { SameRepoCraftPanel } from "./SameRepoCraftPanel";
import { StageTimeline } from "./StageTimeline";
import { buildMarkdownSummary } from "../ui/copySummary";
import { buildEpicCertificate } from "../ui/epicCertificate";
import { recordRecentJob } from "../ui/recentJobs";
import { describePipelineError, loadFailed, terminalStageNote } from "../ui/errorHints";
import { useI18n } from "../i18n";
import { JOB_DETAIL_BY_LOCALE } from "./jobDetail.copy";
import "../styles/verification.css";

// DEEP tier disclosure (#155): shape written by run_deep_experiments_node.
interface DeepResults {
  verdict_stability?: { repeat_count?: number; classification?: string };
  cache_integrity?: string;
  deep_report_file?: string;
}

interface Summary {
  coverage_reason?: string;
  verdict?: string;
  contracts_total?: number;
  matrix_rows_total?: number;
  matrix_passed?: number;
  matrix_failed?: number;
  matrix_unverified?: number;
  findings?: unknown[];
  capsules?: string[];
  report_path?: string;
  retrieval_note?: string;
  errors?: string[];
  preflight?: PreflightResult;
  deep_note?: string;
  deep_results?: DeepResults;
}

type Tab = "overview" | "stages" | "findings" | "certificate" | "invoice" | "capsule";
const ACTIVE = new Set([
  "QUEUED",
  "PREPARING",
  "CONTRACT_REVIEW",
  "RUNNING",
  "REVIEWING",
  "PENDING",
  "WAITING_FOR_PROVIDER",
]);
const TERMINAL = new Set([
  "VERIFIED",
  "BLOCKED",
  "NEEDS_REVIEW",
  "STALE",
  "CANCELLED",
  "EXPIRED",
  "ERROR",
]);

type JDCopy = typeof JOB_DETAIL_BY_LOCALE.zh;

function buildStatusHelp(c: JDCopy): Record<string, [string, string]> {
  return {
    PENDING: [c.pendingTitle, c.pendingBody],
    QUEUED: [c.queuedTitle, c.queuedBody],
    PREPARING: [c.preparingTitle, c.preparingBody],
    CONTRACT_REVIEW: [c.contractReviewTitle, c.contractReviewBody],
    RUNNING: [c.runningTitle, c.runningBody],
    REVIEWING: [c.reviewingTitle, c.reviewingBody],
    WAITING_FOR_PROVIDER: [c.waitingProviderTitle, c.waitingProviderBody],
    VERIFIED: [c.verifiedTitle, c.verifiedBody],
    BLOCKED: [c.blockedTitle, c.blockedBody],
    NEEDS_REVIEW: [c.needsReviewTitle, c.needsReviewBody],
    FAILED: [c.failedTitle, c.failedBody],
    CANCELLED: [c.cancelledTitle, c.cancelledBody],
    STALE: [c.staleTitle, c.staleBody],
    EXPIRED: [c.expiredTitle, c.expiredBody],
    ERROR: [c.errorTitle, c.errorBody],
  };
}

function depthLabel(depth: string | undefined, c: JDCopy): string {
  if (!depth) return "—";
  const map: Record<string, string> = { FAST: c.depthFast, STANDARD: c.depthStandard, DEEP: c.depthDeep };
  const cn = map[depth];
  return cn ? cn + " · " + depth : depth;
}

function deepClassificationLabel(value: string | undefined, c: JDCopy): string {
  if (!value) return "—";
  const map: Record<string, string> = {
    stable: c.classificationStable,
    flaky: c.classificationFlaky,
    single_run: c.classificationSingle,
    no_runs: c.classificationNoRuns,
    contaminated: c.classificationContaminated,
  };
  const cn = map[value];
  return cn ? cn + " · " + value : value;
}

function invoiceLabel(status: string, c: JDCopy): string {
  if (!status) return "—";
  const map: Record<string, string> = { draft: c.invoiceDraft, issued: c.invoiceIssued, paid: c.invoicePaid, void: c.invoiceVoid };
  const cn = map[status];
  return cn ? cn + " · " + status : status;
}
function invoicePill(status: string): string {
  if (status === "paid") return "pill-ok";
  if (status === "issued") return "pill-run";
  return "pill-mute";
}

function findingColumns(jobId: string, c: JDCopy): Column<Finding>[] {
  return [
    {
      key: "severity",
      header: c.colSeverity,
      sortable: true,
      sortValue: (f) => severityRank(f.severity),
      render: (f) => {
        const sev = severityPill(f.severity);
        const hint = severityHint(f.severity);
        return <span className={"pill " + sev.cls} title={hint ? f.severity + " · " + hint : undefined}>{sev.label}</span>;
      },
    },
    { key: "contract_id", header: c.colCondition, sortable: true, render: (f) => <span className="mono">{f.contract_id || "—"}</span> },
    { key: "evidence_type", header: c.colEvidence, sortable: true, render: (f) => <span className="mono" title={f.evidence_type || ""}>{evidenceLabel(f.evidence_type)}</span> },
    {
      key: "confidence",
      header: c.colConfidence,
      sortable: true,
      align: "right",
      sortValue: (f) => f.confidence ?? -1,
      render: (f) => <span className="mono">{fmtPct(f.confidence)}</span>,
    },
    {
      key: "description",
      header: c.colDescription,
      sortable: true,
      render: (f, i) => (
        <a href={"#/findings/" + jobId + "/" + (f.id || i)}>{(f.description || c.viewDetails).slice(0, 120)}</a>
      ),
    },
    {
      key: "capsule",
      header: c.colCapsule,
      render: (f) =>
        f.capsule_path ? (
          <Button variant="ghost" size="sm" onClick={() => downloadCapsule(jobId, String(f.capsule_path).split("/").pop())}>
            {c.download}
          </Button>
        ) : (
          <span className="muted">—</span>
        ),
    },
  ];
}

interface JobDetailProps {
  jobId: string;
}

function JobDetail({ jobId }: JobDetailProps): JSX.Element {
  const { locale } = useI18n();
  const c = JOB_DETAIL_BY_LOCALE[locale];
  const STATUS_HELP = buildStatusHelp(c);
  const depthLabelOf = (depth: string | undefined) => depthLabel(depth, c);
  const deepClassificationLabelOf = (value: string | undefined) => deepClassificationLabel(value, c);
  const invoiceLabelOf = (status: string) => invoiceLabel(status, c);
  const [tab, setTab] = useState<Tab>("overview");
  const [job, setJob] = useState<Job | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [stages, setStages] = useState<StagesData | null>(null);
  const [findings, setFindings] = useState<FindingsData | null>(null);
  const [aiSummary, setAiSummary] = useState<AiSummary | null>(null);
  const [aiSummaryState, setAiSummaryState] = useState<"idle" | "loading" | "error">("idle");
  const [aiSummaryError, setAiSummaryError] = useState<string | null>(null);
  const [aiSummaryStream, setAiSummaryStream] = useState("");
  const [aiSummaryCopied, setAiSummaryCopied] = useState(false);
  const loadAiSummary = async (): Promise<void> => {
    if (aiSummaryState === "loading") return;
    setAiSummaryState("loading");
    setAiSummaryError(null);
    setAiSummaryStream("");
    streamAiSummary(
      jobId,
      (piece) => setAiSummaryStream((current) => current + piece),
      (full) => {
        setAiSummary(full);
        setAiSummaryState("idle");
      },
      (detail) => {
        setAiSummaryState("error");
        setAiSummaryError(detail);
      },
    );
  };
  const copyAiSummary = async (): Promise<void> => {
    if (!aiSummary) return;
    try {
      await navigator.clipboard.writeText(aiSummary.summary);
      setAiSummaryCopied(true);
      window.setTimeout(() => setAiSummaryCopied(false), 2000);
    } catch {
      setAiSummaryError(c.copyFailed);
    }
  };
  const [cert, setCert] = useState<CertificateData | null>(null);
  const [certError, setCertError] = useState<string | null>(null);
  const [copyLinkState, setCopyLinkState] = useState<"idle" | "copied">("idle");
  const [briefCopied, setBriefCopied] = useState(false);
  const [epicCopied, setEpicCopied] = useState(false);
  const [error, setError] = useState<Error | string | null>(null);
  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [invoiceLoading, setInvoiceLoading] = useState(false);
  const [invoiceError, setInvoiceError] = useState<string | null>(null);
  const [invoiceTransitioning, setInvoiceTransitioning] = useState(false);
  const [invoiceTransitionError, setInvoiceTransitionError] = useState<string | null>(null);
  const [artifactError, setArtifactError] = useState<string | null>(null);
  const [findingsLoadFailed, setFindingsLoadFailed] = useState(false);
  const [summaryLoadFailed, setSummaryLoadFailed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [live, setLive] = useState<ProgressEvent[]>([]);
  const [sseState, setSseState] = useState<string>("closed");
  const [refresh, setRefresh] = useState(0);

  const jobPeriod = job?.created_at
    ? new Date(job.created_at).toISOString().slice(0, 7)
    : new Date().toISOString().slice(0, 7);

  useEffect(() => {
    let alive = true;
    let inFlight = false;
    let terminal = false;
    let previousStatus = "";
    let closeStream: (() => void) | undefined;
    const controller = new AbortController();
    const signal = controller.signal;
    const jobPath = "/jobs/" + encodeURIComponent(jobId);
    const artifactPath = "/api/v1" + jobPath;
    setLoading(true); setJob(null); setSummary(null); setStages(null); setFindings(null);
    setLive([]); setError(null); setArtifactError(null); setSummaryLoadFailed(false); setFindingsLoadFailed(false); setCert(null); setCertError(null); setTab("overview");

    const loadArtifacts = async () => {
      const results = await Promise.allSettled([
        apiGet<{ summary: Summary }>(jobPath + "/summary", signal),
        apiGet<StagesData>(artifactPath + "/stages", signal),
        apiGet<FindingsData>(artifactPath + "/findings", signal),
      ]);
      if (!alive) return;
      const [s, st, f] = results;
      if (s.status === "fulfilled") setSummary(Object.keys(s.value.summary || {}).length ? s.value.summary : null);
      if (st.status === "fulfilled") setStages(st.value);
      if (f.status === "fulfilled") setFindings(f.value);
      setSummaryLoadFailed(s.status === "rejected" && loadFailed(s.reason));
      setFindingsLoadFailed(f.status === "rejected" && loadFailed(f.reason));
      const failed = results.filter((result) => result.status === "rejected");
      setArtifactError(failed.length ? c.artifactLoadFailed : null);
    };

    const load = async (initial = false) => {
      if (inFlight || !alive) return;
      inFlight = true;
      try {
        const { job: current } = await apiGet<{ job: Job }>(jobPath, signal);
        if (!alive) return;
        setJob(current);
        setError(null);
        const currentStatus = (current.status || "").toUpperCase();
        terminal = TERMINAL.has(currentStatus);
        if (terminal) { closeStream?.(); closeStream = undefined; }
        else if (!closeStream) {
          closeStream = openProgressStream(jobId, (event) => {
            if (!alive) return;
            setLive((events) => {
              if (event.sequence !== undefined && events.some((item) => item.sequence === event.sequence)) return events;
              return [...events.slice(-199), event];
            });
            const node = event.stage || event.node;
            if (node) setStages((currentStages) => {
              const stage = { node, status: event.status || "", percent: event.percentage ?? event.percent ?? 0, message: event.summary || event.message || "", at: event.ts || "", event_id: String(event.sequence ?? event.seq ?? ""), started_at: event.ts || "", duration_seconds: null, event_count: 0, failed_at: event.status === "failed" ? (event.ts || "") : "", artifact_refs: [...(event.artifacts ?? [])] };
              const rows = currentStages?.stages || [];
              return { job_id: jobId, stages: rows.some((row) => row.node === node) ? rows.map((row) => row.node === node ? stage : row) : [...rows, stage], event_count: (currentStages?.event_count || 0) + 1, degraded: false, degraded_reason: null };
            });
          }, (state) => { if (alive) setSseState(state); });
        }
        if (initial || (terminal && currentStatus !== previousStatus)) await loadArtifacts();
        previousStatus = currentStatus;
        if (initial) recordRecentJob("#/jobs/" + encodeURIComponent(jobId), (current.repo_path || c.unnamedRepo) + " · " + shortId(current.id));
      } catch (e) {
        if (alive) setError(e as Error);
      } finally {
        inFlight = false;
        if (alive) setLoading(false);
      }
    };
    void load(true);
    const poll = window.setInterval(() => {
      if (!terminal && document.visibilityState === "visible") void load();
    }, 5000);
    return () => { alive = false; controller.abort(); closeStream?.(); window.clearInterval(poll); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, refresh]);

  useEffect(() => {
    if (tab !== "certificate") return;
    const controller = new AbortController();
    let alive = true;
    setCertError(null);
    apiGet<CertificateData>("/api/v1/jobs/" + encodeURIComponent(jobId) + "/certificate", controller.signal)
      .then((data) => { if (alive) setCert(data); })
      .catch((e: { status?: number; message?: string }) => {
        if (alive) setCertError(e.status === 404 ? c.reportPending : e.message || c.reportLoadFailed);
      });
    return () => { alive = false; controller.abort(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, jobId, job?.status]);

  // #245: the invoice effect
  useEffect(() => {
    if (tab !== "invoice") return;
    let alive = true;
    setInvoiceLoading(true);
    setInvoiceError(null);
    getInvoiceByPeriod(jobPeriod)
      .then((data) => { if (alive) setInvoice(data); })
      .catch((e: { message?: string }) => {
        if (alive) setInvoiceError(e.message || c.invoiceReadFailed);
      })
      .finally(() => { if (alive) setInvoiceLoading(false); });
    return () => { alive = false; };
  }, [tab, jobPeriod]);

  // #245: transition invoice status
  const transitionStatus = async (targetStatus: "issued" | "paid") => {
    if (!invoice) return;
    setInvoiceTransitioning(true);
    setInvoiceTransitionError(null);
    try {
      const updated = await transitionInvoiceStatus(invoice.period, targetStatus);
      setInvoice(updated);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setInvoiceTransitionError(msg);
    } finally {
      setInvoiceTransitioning(false);
    }
  };

  // Guard clause: the job read itself can fail (network / 404).
  if (loading) return <Spinner />;
  if (!job) {
    return (
      <div>
        <ErrorBox error={error || c.taskNotFound} />
        <Button onClick={() => setRefresh((value) => value + 1)}>{c.retry}</Button>{" "}
        <a href="#/jobs">{c.backToJobs}</a>
      </div>
    );
  }

  const s = summary;
  const status = (job.status || "").toUpperCase();
  const statusHelp = STATUS_HELP[status] || [c.viewThisVerdict, c.followMatrix];
  const latest = live[live.length - 1];
  const findingCount = findings ? findings.count : 0;
  const rowsTotal = typeof s?.matrix_rows_total === "number" ? s.matrix_rows_total : null;
  const nextAction: { label: string; run: () => void } | null =
    status === "BLOCKED" && findingCount > 0
      ? { label: c.findingsBlocked(findingCount), run: () => setTab("findings") }
      : status === "VERIFIED"
      ? { label: c.viewCertificate, run: () => setTab("certificate") }
      : !!s?.coverage_reason && rowsTotal === 0
      ? { label: c.learnGaps, run: () => { window.location.hash = "#/guide"; } }
      : s?.coverage_reason
      ? { label: c.viewUnverified, run: () => { window.location.hash = "#/matrix"; } }
      : null;
  const caps: string[] = [];
  if (findings) {
    findings.findings.forEach((f) => {
      if (f.capsule_path) caps.push(String(f.capsule_path));
    });
  }
  (s && s.capsules ? s.capsules : []).forEach((cc) => {
    const name = String(cc).split("/").pop() || String(cc);
    if (!caps.includes(name)) caps.push(name);
  });

  const tabBtn = (t: Tab, label: string) => (
    <button type="button" role="tab" aria-selected={tab === t} className={"tab" + (tab === t ? " tab-active" : "")} onClick={() => setTab(t)}>
      {label}
    </button>
  );

  return (
    <div className="verification-page">
      <Breadcrumbs items={[{ label: c.jobsLabel, href: "#/jobs" }, { label: c.detailLabel }]} />
      <div className="page-head">
        <h1>
          {c.detailLabel} {shortId(jobId)} <StatusPill status={job.status || ""} />{job.is_demo ? <span className="demo-label">{c.demoLabel}</span> : null}
        </h1>
        <div className="page-sub">
          {(job.base_ref || "—") + " → " + (job.head_ref || "—") + " · " + (job.repo_path || "—")}
        </div>
      </div>
      <ErrorBox error={error || artifactError} />
      {summary?.coverage_reason && <div className="degraded" role="status"><strong>{c.verdictAndEvidence}</strong><p>{summary.coverage_reason}</p>{rowsTotal === 0 ? <a href="#/guide">{c.learnGaps}</a> : <a href="#/matrix">{c.viewUnverified}</a>}</div>}

      <div className="verification-detail-banner" aria-live="polite"><h2>{summary?.coverage_reason ? rowsTotal === 0 ? c.cannotConfirm : c.verdictUnmeasurable : statusHelp[0]}</h2><p>{summary?.coverage_reason ? rowsTotal === 0 ? c.notPassedConfirmation : rowsTotal === null ? c.checkFailed : c.notPassedSummary + " " + rowsTotal + c.runStepsInline : statusHelp[1]}</p>
      {ACTIVE.has(status) ? <Progress value={latest?.percentage ?? latest?.percent ?? 0} label={latest?.summary || latest?.message || c.waitingProgress} showValue /> : null}
      {nextAction ? <div className="next-action" role="group" aria-label={c.nextSteps}><span>{c.nextStepColon}</span><Button size="sm" variant="primary" onClick={nextAction.run}>{nextAction.label}</Button></div> : null}
      <div style={{ display: "flex", gap: 12, marginTop: 18, flexWrap: "wrap", alignItems: "center" }}><Button size="sm" variant="ghost" onClick={() => setRefresh((value) => value + 1)}>{c.refresh}</Button><Button size="sm" variant="ghost" onClick={() => { const md = buildMarkdownSummary({ job: job ?? { id: jobId, base_ref: null, head_ref: null, repo_path: null, spec_path: null, status: null }, summary: summary ? { verdict: summary.verdict ?? null, contracts_total: summary.contracts_total ?? null, matrix_passed: summary.matrix_passed ?? null, matrix_failed: summary.matrix_failed ?? null, matrix_unverified: summary.matrix_unverified ?? null, errors: (summary.errors ?? []) as string[] } : null, findings: findings?.findings ?? [] }); navigator.clipboard.writeText(md).catch(() => {}); setBriefCopied(true); window.setTimeout(() => setBriefCopied(false), 2000); }}>{briefCopied ? c.copiedBadge : c.copyMarkdown}</Button><Button size="sm" variant="ghost" onClick={() => { const md = buildEpicCertificate({ job: job ?? { id: jobId, base_ref: null, head_ref: null, repo_path: null, spec_path: null, status: null }, summary: summary ? { verdict: summary.verdict ?? null, contracts_total: summary.contracts_total ?? null, matrix_passed: summary.matrix_passed ?? null, matrix_failed: summary.matrix_failed ?? null, matrix_unverified: summary.matrix_unverified ?? null, errors: (summary.errors ?? []) as string[] } : null, findings: findings?.findings ?? [] }); navigator.clipboard.writeText(md).catch(() => {}); setEpicCopied(true); window.setTimeout(() => setEpicCopied(false), 2000); }}>{epicCopied ? c.copiedBadge : c.copyEpicCertificate}</Button><a href="#/matrix">{c.viewCoverage}</a><a href={"#/audit?job=" + encodeURIComponent(jobId)}>{c.auditTrail}</a></div>
      </div>

      <div className="tabs" role="tablist" aria-label={c.detailLabel}>
        {tabBtn("overview", c.tabOverview)}
        {tabBtn("stages", c.stages)}
        {tabBtn("findings", c.findingsLabel + " (" + (findings ? findings.count : 0) + ")")}
        {tabBtn("certificate", c.tabReport)}
        {tabBtn("invoice", c.tabInvoice)}
        {tabBtn("capsule", c.capsuleHeaderTitle)}
      </div>

      {tab === "overview" ? (
        <>
          {s ? (
            <>
              <div className="stat-grid" style={{ marginBottom: 16 }}>
                <StatCard label={c.verdictLabel} value={verdictLabel(s.verdict)} tone={verdictTone(s.verdict)} />
                <StatCard label={c.colCondition} value={s.contracts_total ?? "—"} />
                <StatCard label={c.verdictEvidenceOk} value={s.matrix_passed ?? "—"} tone="ok" />
                <StatCard label={c.notPassed} value={s.matrix_failed ?? "—"} tone="bad" />
                <StatCard label={c.unverified} value={s.matrix_unverified ?? "—"} tone="warn" />
              </div>
              <Panel
                title={c.aiReading}
                right={<Button size="sm" variant="ghost" onClick={loadAiSummary} disabled={aiSummaryState === "loading"}>{aiSummaryState === "loading" ? c.explaining : aiSummary ? c.reexplain : c.aiReadingThis}</Button>}
              >
                {aiSummaryState === "loading" || aiSummaryStream || aiSummary ? (
                  <>
                    <div className={"ai-summary-body tone-" + verdictTone(s.verdict)}>
                      <p className="ai-summary-text">
                        {aiSummary ? aiSummary.summary : aiSummaryStream}
                        {aiSummaryState === "loading" ? <span className="ai-summary-caret" aria-hidden="true">▍</span> : null}
                      </p>
                      {aiSummary ? (
                        <div className="ai-summary-meta">
                          <span>{aiSummary.cached ? c.cacheHit : c.modelDirect + (aiSummary.model_latency_ms != null ? " · " + (aiSummary.model_latency_ms / 1000).toFixed(1) + "s" : "")}</span>
                          <span>{c.aiReadingNotVerdict}</span>
                          <button type="button" className="ai-summary-copy" onClick={copyAiSummary}>{aiSummaryCopied ? c.copiedBadge : c.copySummary}</button>
                        </div>
                      ) : (
                        <div className="ai-summary-meta">
                          <span>{aiSummaryStream.length ? c.streamingDesc : c.readingEvidence}</span>
                        </div>
                      )}
                    </div>
                    {aiSummaryState === "error" && aiSummaryStream ? (
                      <div className="ai-summary-error-partial">
                        <p className="muted">{c.explainInterrupted}</p>
                        <p className="ai-summary-stream-error">{aiSummaryError || c.aiReadingUnavailable}</p>
                      </div>
                    ) : null}
                  </>
                ) : aiSummaryState === "error" ? (
                  <ErrorBox error={aiSummaryError || c.aiReadingUnavailable} />
                ) : (
                  <p className="muted">{c.aiReadingHint}</p>
                )}
              </Panel>
              <div>
                <PreflightCard preflight={s.preflight} />
                <Panel title={c.evidenceArtifacts}>
                  {kv(c.reportPath, s.report_path || "—")}
                  {kv(c.retrievalNote, s.retrieval_note || "—")}
                  {s.errors && s.errors.length > 0 ? (
                    <>
                      <div className="kv-label" style={{ margin: "8px 0 4px" }}>{c.executionLog}</div>
                      {s.errors.map((e, i) => (
                        <div key={i} className="errorbox" style={{ marginBottom: 6 }} title={String(e)}>{describePipelineError(String(e))}</div>
                      ))}
                    </>
                  ) : null}
                  <details className="evidence-fold" aria-label={c.evidenceFold}>
                    <summary>{c.evidenceFold}{caps.length ? c.evidenceFoldSuffix(caps.length) : ""}</summary>
                    <div className="evidence-fold-body">
                      {caps.length
                        ? caps.slice(0, 5).map((cc) => (
                            <div key={cc} className="kv">
                              <span className="kv-label">{c.capsuleLabel}</span>
                              <span className="kv-value">{cc}</span>
                            </div>
                          ))
                        : <div className="kv"><span className="kv-label">{c.capsuleLabel}</span><span className="kv-value">{c.noCapsule}</span></div>}
                      {kv(c.signatureMaterials, s?.capsules ? String(s.capsules.length) + " " : c.memoryOnly)}
                      {kv(c.sseProgress, (live && live.length ? String(live.length) + " " + c.frames : c.zeroFrames))}
                    </div>
                  </details>
                </Panel>
                {s.deep_results && Object.keys(s.deep_results).length > 0 ? (
                  <Panel title={c.deepDisclosure}>
                    {kv(c.deepExplanation, s.deep_note || "—")}
                    {s.deep_results.verdict_stability
                      ? kv(
                          c.verdictStability,
                          deepClassificationLabelOf(s.deep_results.verdict_stability.classification)
                            + (s.deep_results.verdict_stability.repeat_count
                              ? c.repeatRunsPrefix(s.deep_results.verdict_stability.repeat_count)
                              : ""),
                        )
                      : null}
                    {s.deep_results.cache_integrity ? kv(c.cacheIntegrity, s.deep_results.cache_integrity) : null}
                    {s.deep_results.deep_report_file ? kv(c.deepReport, s.deep_results.deep_report_file) : null}
                  </Panel>
                ) : null}
              </div>
            </>
          ) : summaryLoadFailed ? (
            <div className="errorbox" role="alert">{c.summaryLoadFailedView}</div>
          ) : ACTIVE.has(status) ? (
            <Empty text={c.activeRunView} />
          ) : status === "FAILED" ? (
            <>
              <Empty text={c.failedTerminalView} />
              <p className="degraded">{c.failedTerminalBody}</p>
            </>
          ) : TERMINAL.has(status) ? (
            <>
              <Empty text={c.terminalNoSummary} />
              <p className="degraded">{c.terminalNoSummaryBody}</p>
            </>
          ) : (
            <>
              <Empty text={c.unknownState + (status || c.emptyParen) + c.unknownStateTail} />
              <p className="muted">{c.unknownStateBody}</p>
            </>
          )}
          <Panel title={c.taskInfo}>
            {kv(c.repoPath, job.repo_path || "—")}
            {kv(c.compareRefs, (job.base_ref || "—") + " → " + (job.head_ref || "—"))}
            {kv(c.specPath, job.spec_path || "—")}
            {kv(c.verifyMode, depthLabelOf(job.depth))}
            {kv(c.retryCount, String(job.retry_count ?? 0))}
            {kv(c.createdAt, fmtTime(job.created_at))}
            {kv(c.updatedAt, fmtTime(job.updated_at))}
            {job.last_error ? <div className="kv-label" style={{ margin: "8px 0 4px" }}>{c.lastErrorLabel}</div> : null}
            {job.last_error ? <div role="alert" className="errorbox" title={job.last_error}>{describePipelineError(String(job.last_error))}</div> : null}
            {job.last_error && terminalStageNote(String(job.last_error)) ? (
              <div className="kv-label" title={job.last_error}>{terminalStageNote(String(job.last_error))}</div>
            ) : null}
          </Panel>
          <SameRepoCraftPanel repoPath={job.repo_path} />
        </>
      ) : null}
      {tab === "stages" ? (
        <Panel
          title={c.executionStages + (sseState === "open" ? c.realtime : ACTIVE.has(status) ? c.connecting : c.terminal)}
        >
          {stages && stages.degraded ? <Degraded reasons={[stages.degraded_reason || "redis unavailable"]} /> : null}
          {stages && stages.stages.length === 0 ? (
            <Empty text={c.noStagesYet} />
          ) : (
            stages && (
              <>
                <div style={{ marginBottom: "var(--sp-3)" }}>
                  <StageTimeline stages={stages.stages} />
                </div>
                {stages.stages.map((st) => (
                  <div className="stage-row" key={st.node}>
                    <span className="stage-node" title={st.node}>{stageLabel(st.node)}</span>
                    <span className="stage-msg">{st.message || st.status}</span>
                    <div className="bar" style={{ width: 120, margin: 0 }}>
                      <div className="bar-fill" style={{ width: Math.min(100, st.percent) + "%" }} />
                    </div>
                    <span className="stage-duration" title={st.started_at ? c.startedAtPrefix + st.started_at : undefined}>{fmtDurationSeconds(st.duration_seconds)}</span>
                    {st.failed_at ? <span className="stage-failed-at" title={st.failed_at}>{c.failedAtPrefix + fmtTime(st.failed_at)}</span> : null}
                    {st.artifact_refs && st.artifact_refs.length > 0 ? (
                      <span className="stage-artifacts" title={st.artifact_refs.join("\n")}>
                        {st.artifact_refs.slice(0, 3).map((ref) => (
                          <span key={ref} className="stage-artifact" title={ref}>{ref}</span>
                        ))}
                        {st.artifact_refs.length > 3 ? <span className="stage-artifact">+{st.artifact_refs.length - 3}</span> : null}
                      </span>
                    ) : null}
                    <span className="stage-pct">{st.percent}%</span>
                    <StatusPill status={st.status} />
                  </div>
                ))}
              </>
            )
          )}
          <div style={{ marginTop: 14 }}>
            <div className="kv-label">{c.realtimeLog}</div>
            <div className="console">
              {live.length === 0
                ? "[" + c.waitingProgressEvents + "]\n"
                : live
                    .map((ev) => {
                      const stage = ev.stage || ev.node || "";
                      const pct = ev.percentage ?? ev.percent ?? 0;
                      const msg = ev.summary || ev.message || "";
                      return "[" + (stage ? stageLabel(stage) : "") + "] " + (ev.status || "") + " " + pct + "% " + msg;
                    })
                    .join("\n")
              }
            </div>
          </div>
        </Panel>
      ) : null}

      {tab === "findings" ? (
        <Panel title={c.findingsLabel + " (" + (findings ? findings.count : 0) + ")"}>
          {findings && findings.degraded ? <Degraded reasons={[findings.degraded_reason || "degraded"]} /> : null}
          {findingsLoadFailed ? (
            <div className="errorbox" role="alert">{c.findingsLoadFailedView}</div>
          ) : !findings || findings.findings.length === 0 ? (
            <Empty text={c.noFindings} />
          ) : (
            <Table<Finding>
              columns={findingColumns(jobId, c)}
              rows={findings.findings}
              rowKey={(f, i) => f.id || String(i)}
            />
          )}
        </Panel>
      ) : null}

      {tab === "certificate" ? (
        <Panel title={<Term id="certificate">{c.certificate}</Term>}>
          {certError ? <div className="errorbox">{certError}</div> : null}
          {cert ? (
            <>
              {kv(c.certificateFile, cert.path)}
              {cert.signed_path ? kv(c.signedFile, cert.signed_path) : null}
              {cert.signed_statement ? (
                <>
                  <div className="kv-label">{c.signedStatement}</div>
                  <pre className="json">{JSON.stringify(cert.signed_statement, null, 2)}</pre>
                </>
              ) : (
                <div className="muted" style={{ margin: "8px 0" }}>
                  {c.noSignedFile}
                </div>
              )}
              <div className="kv-label">{c.certificateContent}</div>
              <pre className="json">{JSON.stringify(cert.document, null, 2)}</pre>
            </>
          ) : null}
        </Panel>
      ) : null}

      {tab === "invoice" ? (
        <Panel title={c.tabInvoice}>
          {(() => {
            if (invoiceLoading) return <Spinner />;
            if (invoiceError) return <div className="errorbox" role="alert">{c.invoiceReadFailedPrefix}{invoiceError}</div>;
            if (!invoice) return <Empty text={c.periodNoInvoice} />;
            return (
              <>
                <div className="stat-grid" style={{ marginBottom: 16 }}>
                  <StatCard label={c.tabInvoice} value={invoice.id} sub={invoice.period} />
                  <StatCard label={c.statusLabel} value={<span className={"pill " + invoicePill(invoice.status)}>{invoiceLabelOf(invoice.status)}</span>} />
                  <StatCard label={c.totalLabel} value={invoice.currency + " " + invoice.total.toFixed(2)} tone="info" />
                  <StatCard label={c.lineItemsLabel} value={String((invoice.line_items ?? []).length)} />
                </div>
                <Panel title={c.lineItemsLabel}>
                  {invoice.line_items && invoice.line_items.length > 0 ? (
                    <Table
                      columns={[
                        { key: "metric", header: c.metricLabel },
                        { key: "amount", header: c.quantityLabel, align: "right" as const },
                        { key: "unit_price", header: c.unitPriceLabel, align: "right" as const },
                        { key: "amount_total", header: c.amountLabel, align: "right" as const },
                      ]}
                      rows={invoice.line_items}
                      rowKey={(_item, i) => String(i)}
                      emptyTitle={c.noLineItems}
                    />
                  ) : (
                    <Empty text={c.noLineItems} />
                  )}
                </Panel>
                <div style={{ marginTop: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <Button
                    variant="primary"
                    size="sm"
                    disabled={invoiceTransitioning || invoice.status === "issued" || invoice.status === "paid"}
                    onClick={() => transitionStatus("issued")}
                  >
                    {invoice.status === "draft" ? c.issueButton : c.alreadyIssued}
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    disabled={invoiceTransitioning || invoice.status !== "issued"}
                    onClick={() => transitionStatus("paid")}
                  >
                    {invoice.status === "paid" ? c.alreadyPaid : c.markPaid}
                  </Button>
                  {invoiceTransitionError && (
                    <span className="errorbox" style={{ marginLeft: "auto" }}>{invoiceTransitionError}</span>
                  )}
                </div>
              </>
            );
          })()}
        </Panel>
      ) : null}

      {tab === "capsule" ? (
        <Panel title={<Term id="capsule">{c.capsuleHeaderTitle}</Term>}>
          <div>
            {caps.map((cc) => (
              <Button key={cc} variant="ghost" size="sm" style={{ marginRight: 8, marginBottom: 8 }} onClick={() => downloadCapsule(jobId, cc.split("/").pop())}>
                ⬇ {cc.split("/").pop()}
              </Button>
            ))}
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                const link = `${window.location.origin}${window.location.pathname}#/jobs/${encodeURIComponent(jobId)}`;
                navigator.clipboard.writeText(link).catch(() => {
                  /* clipboard may be denied; nothing to fall back to */
                });
                setCopyLinkState("copied");
                window.setTimeout(() => setCopyLinkState("idle"), 2000);
              }}
            >
              {copyLinkState === "copied" ? c.copiedBadge : c.copyReviewLink}
            </Button>
            <p className="muted" style={{ fontSize: "var(--text-xs)", marginTop: "var(--sp-2)" }}>
              {c.reviewLinkExplain}
            </p>
          </div>
        </Panel>
      ) : null}
    </div>
  );
}

export default JobDetail;
