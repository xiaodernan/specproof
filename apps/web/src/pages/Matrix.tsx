import { useMemo, useState } from "react";
import type { Job, MatrixData } from "../api";
import { useRemoteData } from "../hooks/useRemoteData";
import { Button, Degraded, ErrorBox, Input, Panel, Select, Spinner, StatCard, Table, Term, attributionLabel, checkerLabel, dependencyInstallLabel, executionSurfaceLabel, executionSurfaceTone, resultCaption, resultPill, shortId } from "../ui";
import { ProductIcon } from "../ui/ProductIcon";
import { QualityEmpty, QualityHeader, QualityPagination } from "./QualityLayout";
import { useI18n } from "../i18n";
import { MATRIX_BY_LOCALE } from "./matrix.copy";

const PAGE_SIZE = 25;

/** A count the pipeline never recorded is not the same fact as a recorded 0. */
function countText(value: number | null, unmeasured: string): string | number {
  return value === null ? unmeasured : value;
}

type MatrixRow = MatrixData["rows"][number];

export default function Matrix() {
  const { locale } = useI18n();
  const c = MATRIX_BY_LOCALE[locale];
  const [jobId, setJobId] = useState("");
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState(1);
  const jobs = useRemoteData<{ jobs: Job[] }>("/jobs?limit=200");
  const matrix = useRemoteData<MatrixData>(jobId ? "/api/v1/jobs/" + encodeURIComponent(jobId) + "/matrix" : null);
  const { data, error, loading } = matrix;
  const rows = useMemo(() => {
    const query = filter.trim().toLowerCase();
    return (data?.rows ?? []).filter(row => !query || [row.requirement_text, row.contract_id_str, row.result, resultCaption(row.result)].join(" ").toLowerCase().includes(query));
  }, [data, filter]);
  const currentPage = Math.min(page, Math.max(1, Math.ceil(rows.length / PAGE_SIZE)));
  const missingEvidence = (data?.rows ?? []).filter(row => !row.evidence_ref?.trim()).length;

  return <div className="quality-page">
    <QualityHeader icon="matrix" eyebrow={c.eyebrow} title={c.title} description={c.description} action={jobId ? <a className="btn btn-secondary" href={"#/jobs/" + encodeURIComponent(jobId)}>{c.viewFull}</a> : <a className="btn btn-primary" href="#/jobs/new">{c.newButton}</a>} />
    <div className="quality-brief"><ProductIcon name="shield" /><p><strong>{c.briefStrong}</strong> {c.briefBody}<Term id="contract">{c.briefTermContract}</Term>{c.briefTail}<Term id="evidence">{c.briefTermEvidence}</Term></p></div>
    <div className="quality-filters"><Select className="quality-filter-wide" label={c.selectLabel} value={jobId} disabled={jobs.loading} onChange={event => { setJobId(event.target.value); setFilter(""); setPage(1); }}><option value="">{c.selectPlaceholder}</option>{(jobs.data?.jobs ?? []).map(job => <option key={job.id} value={job.id}>{shortId(job.id)} · {(job.repo_path || "").split(/[\\/]/).pop()} · {job.base_ref || c.selectOption} → {job.head_ref || c.selectOption}</option>)}</Select><Button variant="ghost" loading={jobId ? matrix.refreshing : jobs.refreshing} onClick={jobId ? matrix.refresh : jobs.refresh}>{c.refresh}</Button></div>
    <ErrorBox error={jobs.error || error} />
    {!jobId ? <Panel title={c.matrixPanelTitle}><QualityEmpty icon="matrix" title={jobs.error ? c.readFailedTitle : jobs.loading ? c.loadingJobsTitle : jobs.data?.jobs.length ? c.selectJobTitle : c.jobsEmptyTitle} description={jobs.error ? c.jobsErrorDescription : jobs.data?.jobs.length ? c.matrixHasJobsDescription : c.jobsEmptyDescription} action={jobs.error ? <Button onClick={jobs.refresh}>{c.reload}</Button> : !jobs.loading && !jobs.data?.jobs.length ? <a href="#/jobs/new" className="btn btn-primary">{c.createFirst}</a> : null} /></Panel> : loading ? <Spinner /> : error ? <QualityEmpty icon="matrix" title={c.matrixReadFailedTitle} description={c.matrixReadFailedDescription} action={<Button onClick={matrix.refresh}>{c.reload}</Button>} /> : data && <>
      {data.degraded && <Degraded reasons={[data.degraded_reason || c.degradedFallback]} />}
      <div className="quality-metrics"><StatCard label={c.metricTotal} value={countText(data.counts.total, c.unmeasured)} /><StatCard label={c.metricPassed} value={countText(data.counts.passed, c.unmeasured)} tone="ok" /><StatCard label={c.metricFailed} value={countText(data.counts.failed, c.unmeasured)} tone="bad" /><StatCard label={c.metricUnverified} value={countText(data.counts.unverified, c.unmeasured)} tone="warn" /></div>
      {missingEvidence > 0 && <div className="quality-brief quality-warning"><ProductIcon name="guide" /><p><strong>{c.missingEvidenceStrong(missingEvidence)}</strong> {locale === "zh" ? "这些没有留下证据的行，其状态无法成为合并判据。" : "Rows without evidence cannot gate a merge."}</p></div>}
      {data.rows_truncated && <div className="quality-brief"><ProductIcon name="guide" /><p><strong>{c.truncationStrong(data.rows.length, data.rows_total ?? data.rows.length)}</strong> {data.counts.total === null ? c.truncationNullNote : c.truncationNote}</p></div>}
      <Panel title={c.matrixPanelTitle} right={<Input aria-label={c.filterAria} type="search" placeholder={c.filterPlaceholder} value={filter} onChange={event => { setFilter(event.target.value); setPage(1); }} />}>
        {!rows.length ? <QualityEmpty icon="matrix" title={filter ? c.filterNoMatchTitle : data.counts.total === null ? c.totalNullTitle : data.counts.total > 0 ? c.totalPositiveEmptyTitle : c.totalZeroTitle} description={filter ? c.filterNoMatchDescription : data.counts.total === null ? c.totalNullDescription : data.counts.total > 0 ? c.totalPositiveEmptyDescription : c.totalZeroDescription} action={filter ? <Button onClick={() => setFilter("")}>{c.clearFilter}</Button> : <a href={"#/jobs/" + encodeURIComponent(jobId)}>{c.viewFull2}</a>} /> : <><Table<MatrixRow>
          className="quality-table"
          rows={rows.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)}
          rowKey={(row, index) => row.contract_id_str + index}
          columns={[
            {
              key: "requirement",
              header: c.colReq,
              render: (row) => (
                <>
                  <strong>{row.requirement_text || c.noRequirement}</strong>
                  <span className="quality-cell-secondary mono">{row.contract_id_str}</span>
                </>
              ),
            },
            {
              key: "expected",
              header: c.colExpected,
              render: (row) => <span className="quality-cell-copy">{row.expected_behavior || c.noExpected}</span>,
            },
            {
              key: "checker",
              header: c.colChecker,
              render: (row) => <span className="mono" title={row.checker_type || undefined}>{checkerLabel(row.checker_type)}</span>,
            },
            {
              key: "result",
              header: c.colResult,
              render: (row) => {
                const result = resultPill(row.result);
                return (
                  <>
                    <span className={"pill " + result.cls}>{result.label}</span>
                    <div className="quality-result-caption">{resultCaption(row.result)}</div>
                    {/* The pipeline's own next step, when it has one. It is
                        evidence-derived guidance, so an absent value stays
                        absent rather than defaulting to generic advice. */}
                    {row.next_action && (
                      <div className="quality-cell-secondary" title={row.next_action}>
                        {c.nextStepPrefix}{row.next_action}
                      </div>
                    )}
                  </>
                );
              },
            },
            {
              key: "diff",
              header: c.colDiff,
              render: (row) => {
                // Absent means the pipeline ran no differential experiment for
                // this rule — never render it as a green side, and never as zero.
                if (!row.base_result && !row.head_result) {
                  return <span className="quality-cell-secondary">{c.noDifferentialExperiment}</span>;
                }
                const side = (value?: string) => {
                  if (!value) return <span className="quality-cell-secondary">{c.missingSide}</span>;
                  const pill = resultPill(value);
                  return <span className={"pill " + pill.cls} title={value}>{pill.label}</span>;
                };
                return (
                  <>
                    <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                      {side(row.base_result)}
                      <span aria-hidden>→</span>
                      {side(row.head_result)}
                    </span>
                    <div className="quality-result-caption">
                      {row.attribution ? attributionLabel(row.attribution) : c.attributionUnknown}
                    </div>
                    {/* Safety disclosure: where the differential ran the change's
                        own tests. A host run had no sandbox, and that is the
                        reader's business, not an internal detail. */}
                    {row.execution_surface && (
                      <div
                        className={"quality-execution-surface tone-" + executionSurfaceTone(row.execution_surface)}
                        title={row.execution_surface}
                      >
                        {executionSurfaceLabel(row.execution_surface)}
                      </div>
                    )}
                    {row.dependency_install && (
                      <div
                        className="quality-execution-surface tone-mute"
                        title={row.dependency_install}
                      >
                        {dependencyInstallLabel(row.dependency_install)}
                      </div>
                    )}
                  </>
                );
              },
            },
            {
              key: "evidence",
              header: c.colEvidence,
              render: (row) => (
                <>
                  <span className="mono muted">{row.evidence_ref || c.evidenceEmpty}</span>
                  {row.unverified_reason && (
                    <div className="quality-cell-secondary" title={row.unverified_reason}>
                      {row.unverified_reason}
                    </div>
                  )}
                </>
              ),
            },
          ]}
        /><QualityPagination page={currentPage} pageSize={PAGE_SIZE} total={rows.length} onChange={setPage} /></>}
      </Panel>
    </>}
  </div>;
}
