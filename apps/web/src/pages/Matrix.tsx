import { useMemo, useState } from "react";
import type { Job, MatrixData } from "../api";
import { useRemoteData } from "../hooks/useRemoteData";
import { Button, Degraded, ErrorBox, Input, Panel, Select, Spinner, StatCard, Table, Term, attributionLabel, checkerLabel, resultPill, shortId } from "../ui";
import { ProductIcon } from "../ui/ProductIcon";
import { QualityEmpty, QualityHeader, QualityPagination } from "./QualityLayout";

const PAGE_SIZE = 25;
const RESULT: Record<string, string> = { PASS: "检查通过", FAIL: "发现不符", UNVERIFIED: "证据不足", DEGRADED: "检查受限" };

type MatrixRow = MatrixData["rows"][number];

export default function Matrix() {
  const [jobId, setJobId] = useState("");
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState(1);
  const jobs = useRemoteData<{ jobs: Job[] }>("/jobs?limit=200");
  const matrix = useRemoteData<MatrixData>(jobId ? "/api/v1/jobs/" + encodeURIComponent(jobId) + "/matrix" : null);
  const { data, error, loading } = matrix;
  const rows = useMemo(() => {
    const query = filter.trim().toLowerCase();
    return (data?.rows ?? []).filter(row => !query || [row.requirement_text, row.contract_id_str, row.result, RESULT[row.result] || ""].join(" ").toLowerCase().includes(query));
  }, [data, filter]);
  const currentPage = Math.min(page, Math.max(1, Math.ceil(rows.length / PAGE_SIZE)));
  const missingEvidence = (data?.rows ?? []).filter(row => !row.evidence_ref?.trim()).length;

  return <div className="quality-page">
    <QualityHeader icon="matrix" eyebrow="REQUIREMENT COVERAGE" title="每条需求，都有落点。" description="把需求、检查结果和证据逐条对应。先看未通过与证据不足的部分，再决定这次变更能否交付。" action={jobId ? <a className="btn btn-secondary" href={"#/jobs/" + encodeURIComponent(jobId)}>查看完整验证 →</a> : <a className="btn btn-primary" href="#/jobs/new">新建验证 →</a>} />
    <div className="quality-brief"><ProductIcon name="shield" /><p><strong>通过不等于全覆盖。</strong> 这里呈现已提取<Term id="contract">规则</Term>的结果；未识别的需求、尚未执行的检查或缺少<Term id="evidence">证据</Term>的结果，仍需要补充验证。</p></div>
    <div className="quality-filters"><Select className="quality-filter-wide" label="选择验证任务" value={jobId} disabled={jobs.loading} onChange={event => { setJobId(event.target.value); setFilter(""); setPage(1); }}><option value="">选择一个任务，查看需求覆盖</option>{(jobs.data?.jobs ?? []).map(job => <option key={job.id} value={job.id}>{shortId(job.id)} · {(job.repo_path || "").split(/[\\/]/).pop()} · {job.base_ref || "?"} → {job.head_ref || "?"}</option>)}</Select><Button variant="ghost" loading={jobId ? matrix.refreshing : jobs.refreshing} onClick={jobId ? matrix.refresh : jobs.refresh}>刷新</Button></div>
    <ErrorBox error={jobs.error || error} />
    {!jobId ? <Panel title="需求与证据"><QualityEmpty icon="matrix" title={jobs.error ? "暂时无法读取任务" : jobs.loading ? "正在读取验证任务" : jobs.data?.jobs.length ? "选择一次验证，展开交付依据" : "还没有可查看的验证"} description={jobs.error ? "请检查服务连接后重试。" : jobs.data?.jobs.length ? "选择器提供最近 200 条任务。查看每条需求是否经过检查，以及证据是否齐全。" : "创建一次变更验收后，即可在这里查看需求和证据的对应关系。"} action={jobs.error ? <Button onClick={jobs.refresh}>重新加载</Button> : !jobs.loading && !jobs.data?.jobs.length ? <a href="#/jobs/new" className="btn btn-primary">创建第一次验证 →</a> : null} /></Panel> : loading ? <Spinner /> : error ? <QualityEmpty icon="matrix" title="暂时无法读取这次验证" description="请稍后重试，也可以前往完整验证页检查任务进度。" action={<Button onClick={matrix.refresh}>重新加载</Button>} /> : data && <>
      {data.degraded && <Degraded reasons={[data.degraded_reason || "部分覆盖数据暂不可用，请稍后刷新。"]} />}
      <div className="quality-metrics"><StatCard label="已提取规则" value={data.counts.total} /><StatCard label="检查通过" value={data.counts.passed} tone="ok" /><StatCard label="发现不符" value={data.counts.failed} tone="bad" /><StatCard label="证据不足" value={data.counts.unverified} tone="warn" /></div>
      {missingEvidence > 0 && <div className="quality-brief quality-warning"><ProductIcon name="guide" /><p><strong>{missingEvidence} 条规则尚无证据引用。</strong> 请结合完整验证报告核查，单独的检查状态无法代替可复核的证据。</p></div>}
      {data.rows_truncated && <div className="quality-brief"><ProductIcon name="guide" /><p><strong>逐条结果较多，此处仅展示前 {data.rows.length} 条（共 {data.rows_total ?? data.rows.length} 条）。</strong> 上方统计取自管线自身的总数，不因展示条数减少而变小。</p></div>}
      <Panel title="需求与证据" right={<Input aria-label="搜索需求" type="search" placeholder="搜索需求、编号或结果" value={filter} onChange={event => { setFilter(event.target.value); setPage(1); }} />}>
        {!rows.length ? <QualityEmpty icon="matrix" title={filter ? "没有匹配的需求" : data.counts.total > 0 ? "有统计数字，但读不到逐条结果" : "这次验证尚无逐条结果"} description={filter ? "换一个关键词，或清除搜索条件。" : data.counts.total > 0 ? `本次验证记录了 ${data.counts.total} 条规则的结果，但逐条明细没能读到（多半是任务在摘要写入前中断）。请把总数视为未经逐条核对，不要据此认为每条需求都有落点。` : "任务可能仍在执行，或尚未提取到可检查的规则。请查看任务详情；没有规则不能视为验收通过。"} action={filter ? <Button onClick={() => setFilter("")}>清除搜索</Button> : <a href={"#/jobs/" + encodeURIComponent(jobId)}>查看任务详情 →</a>} /> : <><Table<MatrixRow>
          className="quality-table"
          rows={rows.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)}
          rowKey={(row, index) => row.contract_id_str + index}
          columns={[
            {
              key: "requirement",
              header: "需求 / 规则编号",
              render: (row) => (
                <>
                  <strong>{row.requirement_text || "未提供需求描述"}</strong>
                  <span className="quality-cell-secondary mono">{row.contract_id_str}</span>
                </>
              ),
            },
            {
              key: "expected",
              header: "预期行为",
              render: (row) => <span className="quality-cell-copy">{row.expected_behavior || "尚未提供"}</span>,
            },
            {
              key: "checker",
              header: "检查方式",
              render: (row) => <span className="mono" title={row.checker_type || undefined}>{checkerLabel(row.checker_type)}</span>,
            },
            {
              key: "result",
              header: "检查结果",
              render: (row) => {
                const result = resultPill(row.result);
                return (
                  <>
                    <span className={"pill " + result.cls}>{result.label}</span>
                    <div className="quality-result-caption">{RESULT[row.result] || "待确认状态"}</div>
                    {/* The pipeline's own next step, when it has one. It is
                        evidence-derived guidance, so an absent value stays
                        absent rather than defaulting to generic advice. */}
                    {row.next_action && (
                      <div className="quality-cell-secondary" title={row.next_action}>
                        下一步：{row.next_action}
                      </div>
                    )}
                  </>
                );
              },
            },
            {
              key: "diff",
              header: "改前 / 改后对照",
              render: (row) => {
                // Absent means the pipeline ran no differential experiment for
                // this rule — never render it as a green side, and never as "—".
                if (!row.base_result && !row.head_result) {
                  return <span className="quality-cell-secondary">未做改前/改后差分实验</span>;
                }
                const side = (value?: string) => {
                  if (!value) return <span className="quality-cell-secondary">无观测</span>;
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
                      {row.attribution ? attributionLabel(row.attribution) : "归因未知"}
                    </div>
                  </>
                );
              },
            },
            {
              key: "evidence",
              header: "证据引用",
              render: (row) => (
                <>
                  <span className="mono muted">{row.evidence_ref || "未知"}</span>
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
