import { useMemo, useState } from "react";
import type { ContractsData } from "../api";
import { useDebouncedValue, useRemoteData } from "../hooks/useRemoteData";
import { Button, Degraded, ErrorBox, Input, Panel, Select, Spinner, StatCard, Table, Term, checkerLabel, contractStatusLabel, CONTRACT_STATUS_CN, fmtTime } from "../ui";
import { ProductIcon } from "../ui/ProductIcon";
import { QualityEmpty, QualityHeader, QualityPagination } from "./QualityLayout";
import { useI18n } from "../i18n";
import { CONTRACTS_BY_LOCALE } from "./contracts.copy";

const PAGE_SIZE = 25;

type ContractRule = ContractsData["contracts"][number];

export default function Contracts() {
  const { locale } = useI18n();
  const c = CONTRACTS_BY_LOCALE[locale];
  const [status, setStatus] = useState("all");
  const [repoFilter, setRepoFilter] = useState("");
  const [page, setPage] = useState(1);
  const repo = useDebouncedValue(repoFilter);
  const { data, error, loading, refreshing, refresh } = useRemoteData<ContractsData>(
    "/api/v1/contracts?status=" + status + (repo ? "&repo_path=" + encodeURIComponent(repo) : ""),
  );
  const counts = useMemo(() => {
    const result: Record<string, number> = {};
    data?.contracts.forEach(rule => { const key = rule.status.toUpperCase(); result[key] = (result[key] || 0) + 1; });
    return result;
  }, [data]);
  const contracts = data?.contracts ?? [];
  const currentPage = Math.min(page, Math.max(1, Math.ceil(contracts.length / PAGE_SIZE)));
  const filtered = status !== "all" || !!repo;
  const clear = () => { setStatus("all"); setRepoFilter(""); setPage(1); };

  return <div className="quality-page">
    <QualityHeader icon="contracts" eyebrow={c.eyebrow} title={c.title} description={c.description} action={<Button variant="ghost" loading={refreshing} onClick={refresh}>{c.refresh}</Button>} />
    <div className="quality-brief"><ProductIcon name="guide" /><p><strong>{c.briefStrong}</strong> {c.briefBodyBefore}<Term id="contract">{c.briefTerm}</Term>{c.briefBodyAfter}<a href="#/guide">{c.briefGuideLink}</a></p></div>
    <div className="quality-filters">
      <Select label={c.filterStatusLabel} value={status} onChange={event => { setStatus(event.target.value); setPage(1); }}><option value="all">{c.allStatuses}</option>{Object.entries(CONTRACT_STATUS_CN).map(([value, label]) => <option key={value} value={value.toLowerCase()}>{label}</option>)}</Select>
      <Input className="quality-filter-wide" label={c.filterRepoLabel} type="search" value={repoFilter} placeholder={c.filterRepoPlaceholder} maxLength={512} onChange={event => { setRepoFilter(event.target.value); setPage(1); }} />
      {(filtered || !!repoFilter) && <Button variant="ghost" onClick={clear}>{c.clearFilters}</Button>}
    </div>
    <ErrorBox error={error} />
    {loading ? <Spinner /> : error ? <QualityEmpty icon="contracts" title={c.emptyReadTitle} description={c.emptyReadDescription} action={<Button onClick={refresh}>{c.retry}</Button>} /> : data && <>
      {data.degraded && <Degraded reasons={[c.degradedReason]} />}
      <div className="quality-metrics" aria-label={c.metricsAria}><StatCard label={c.metricCounting} value={data.count} tone="info" /><StatCard label={c.metricApproved} value={counts.APPROVED ?? 0} tone="ok" /><StatCard label={c.metricProposed} value={counts.PROPOSED ?? 0} tone="warn" /><StatCard label={c.metricRejected} value={(counts.REJECTED ?? 0) + (counts.REVOKED ?? 0)} tone="mute" /></div>
      <Panel title={c.matrixTitle} right={<span className="muted">{c.matrixNote}</span>}>
        {!contracts.length ? <QualityEmpty icon="contracts" title={filtered ? c.emptyFilteredTitle : c.emptyAllTitle} description={filtered ? c.emptyFilteredDescription : c.emptyAllDescription} action={filtered ? <Button onClick={clear}>{c.clearFilters}</Button> : <a className="btn btn-primary" href="#/jobs/new">{c.ctaNewJobs}</a>} /> : <>
          <Table<ContractRule>
            className="quality-table"
            rows={contracts.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)}
            rowKey={(rule) => rule.id}
            columns={[
              {
                key: "requirement",
                header: c.colRequirement,
                render: (rule) => (
                  <>
                    <strong>{rule.requirement || c.noRequirement}</strong>
                    <span className="quality-cell-secondary mono">{rule.id} · v{rule.version}</span>
                    {rule.requirement_ref && <span className="quality-cell-secondary">{c.requirementRef}{rule.requirement_ref}</span>}
                  </>
                ),
              },
              {
                key: "expected",
                header: c.colExpected,
                render: (rule) => <span className="quality-cell-copy">{rule.expected_behavior || c.noExpected}</span>,
              },
              {
                key: "status",
                header: c.colStatus,
                render: (rule) => {
                  const code = rule.status.toUpperCase();
                  const cls = code === "APPROVED" ? "pill-ok" : code === "PROPOSED" ? "pill-run" : "pill-mute";
                  return <span className={"pill " + cls} title={rule.status}>{contractStatusLabel(rule.status)}</span>;
                },
              },
              {
                key: "checker",
                header: c.colChecker,
                render: (rule) => <span className="mono" title={rule.checker_type || undefined}>{checkerLabel(rule.checker_type)}</span>,
              },
              {
                key: "repo",
                header: c.colRepo,
                render: (rule) => (
                  <>
                    <span className="quality-cell-copy mono">{rule.repo_path}</span>
                    <span className="quality-cell-secondary">{fmtTime(rule.created_at)}</span>
                  </>
                ),
              },
            ]}
          /><QualityPagination page={currentPage} pageSize={PAGE_SIZE} total={contracts.length} onChange={setPage} />
        </>}
      </Panel>
    </>}
  </div>;
}
