import { useState } from "react";
import {
  apiGet, CertificateData, downloadCapsule, Finding, FindingsData, Job, openProgressStream,
  ProgressEvent, StagesData,
  // #245: invoice status transition
  getInvoiceByPeriod, transitionInvoiceStatus,
} from "../api";
import { Invoice } from "../pages/Billing";
import {
  Breadcrumbs, Button, Degraded, Empty, ErrorBox, Panel, PreflightCard, Progress, Spinner, StatCard, StatusPill, Table, Term,
  fmtTime, kv, shortId, severityPill, severityHint, severityRank, evidenceLabel, stageLabel, verdictTone, verdictLabel,
  type Column, type PreflightResult,
} from "../ui";
import { fmtPct } from "../ui";
import { SameRepoCraftPanel } from "./SameRepoCraftPanel";
import { describePipelineError, terminalStageNote } from "../ui/errorHints";
import "../styles/verification.css";

// DEEP tier disclosure (#155): shape written by run_deep_experiments_node.
// Only declared keys are rendered; anything the node adds later is ignored
// here rather than guessed at.
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
const ACTIVE = new Set(["QUEUED", "RUNNING", "PENDING", "WAITING_FOR_PROVIDER"]);
const TERMINAL = new Set(["VERIFIED", "BLOCKED", "STALE", "CANCELLED", "ERROR"]);

const STATUS_HELP: Record<string, [string, string]> = {
  PENDING: ["验证已创建，正在排队", "系统已受理，等待执行服务接手。进度会自动出现在这里，可以先离开。"],
  QUEUED: ["验证已创建，等待执行", "执行服务接手后，进度会自动出现在这里。可以先离开，稍后从验证记录继续查看。"],
  RUNNING: ["正在检查代码与需求", "系统正在分析改动、收集证据并核对需求。完成后会自动更新结论。"],
  WAITING_FOR_PROVIDER: ["正在等待模型服务", "任务已保存，模型服务恢复可用后将继续处理。"],
  VERIFIED: ["本次验证通过", "已验证的需求具备支持证据。合并前建议确认需求覆盖范围，以及是否仍有未验证项。"],
  BLOCKED: ["发现需要处理的问题", "先查看风险发现及其证据，再决定如何修改代码。需求矩阵可帮助定位受影响的验收条件。"],
  FAILED: ["本次验证未能完成", "执行失败不代表代码有问题。请查看任务信息中的错误原因，处理环境或服务问题后重新验证。"],
  CANCELLED: ["验证已取消", "本次执行已停止，需要继续时可以创建新的验证任务。"],
  STALE: ["本次验证已过期", "代码版本可能已变化，请基于最新提交重新验证。"],
  ERROR: ["执行遇到错误", "请查看错误原因，处理执行环境或服务问题后重新验证。"],
};

const DEPTH_LABELS: Record<string, string> = {
  FAST: "快速验证",
  STANDARD: "标准验证",
  DEEP: "深度验证",
};
function depthLabel(depth: string | undefined): string {
  if (!depth) return "—";
  const cn = DEPTH_LABELS[depth];
  return cn ? cn + " · " + depth : depth;
}

const DEEP_CLASSIFICATION_LABELS: Record<string, string> = {
  stable: "结论稳定",
  flaky: "结论不稳定",
  single_run: "仅单次运行",
  no_runs: "无重复运行",
  contaminated: "环境受污染",
};
function deepClassificationLabel(value: string | undefined): string {
  if (!value) return "—";
  const cn = DEEP_CLASSIFICATION_LABELS[value];
  return cn ? cn + " · " + value : value;
}

const INVOICE_LABELS: Record<string, string> = {
  draft: "草稿",
  issued: "已开具",
  paid: "已支付",
  void: "已作废",
};
function invoiceLabel(status: string): string {
  if (!status) return "—";
  const cn = INVOICE_LABELS[status];
  return cn ? cn + " · " + status : status;
}
function invoicePill(status: string): string {
  if (status === "paid") return "pill-ok";
  if (status === "issued") return "pill-run";
  return "pill-mute";
}

function findingColumns(jobId: string): Column<Finding>[] {
  return [
    {
      key: "severity",
      header: "严重程度",
      sortable: true,
      sortValue: (f) => severityRank(f.severity),
      render: (f) => {
        const sev = severityPill(f.severity);
        const hint = severityHint(f.severity);
        return <span className={"pill " + sev.cls} title={hint ? f.severity + " · " + hint : undefined}>{sev.label}</span>;
      },
    },
    { key: "contract_id", header: "验收条件", sortable: true, render: (f) => <span className="mono">{f.contract_id || "—"}</span> },
    { key: "evidence_type", header: "证据方式", sortable: true, render: (f) => <span className="mono" title={f.evidence_type || ""}>{evidenceLabel(f.evidence_type)}</span> },
    {
      key: "confidence",
      header: "置信度",
      sortable: true,
      align: "right",
      sortValue: (f) => f.confidence ?? -1,
      render: (f) => <span className="mono">{fmtPct(f.confidence)}</span>,
    },
    {
      key: "description",
      header: "描述",
      sortable: true,
      render: (f, i) => (
        <a href={"#/findings/" + jobId + "/" + (f.id || i)}>{(f.description || "查看详情").slice(0, 120)}</a>
      ),
    },
    {
      key: "capsule",
      header: "复现包",
      render: (f) =>
        f.capsule_path ? (
          <Button variant="ghost" size="sm" onClick={() => downloadCapsule(jobId, String(f.capsule_path).split("/").pop())}>
            下载
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
  const [tab, setTab] = useState<Tab>("overview");
  const [job, setJob] = useState<Job | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [stages, setStages] = useState<StagesData | null>(null);
  const [findings, setFindings] = useState<FindingsData | null>(null);
  const [cert, setCert] = useState<CertificateData | null>(null);
  const [certError, setCertError] = useState<string | null>(null);
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

  // #245: derive the billing period from the job's created_at (YYYY-MM)
  const jobPeriod = job?.created_at
    ? new Date(job.created_at).toISOString().slice(0, 7)
    : new Date().toISOString().slice(0, 7);

  // #245: render invoice tab content (extracted to avoid nested ternary parsing issues)
  const renderInvoiceContent = () => {
    if (invoiceLoading) return <Spinner />;
    if (invoiceError) return <div className="errorbox" role="alert">读取发票失败：{invoiceError}</div>;
    if (!invoice) return <Empty text="该周期暂无发票。计费 cron 在次月月初会自动生成草稿。" />;

    return (
      <>
        <div className="stat-grid" style={{ marginBottom: 16 }}>
          <StatCard label="发票 Invoice" value={invoice.id} sub={invoice.period} />
          <StatCard label="状态 Status" value={<span className={"pill " + invoicePill(invoice.status)}>{invoiceLabel(invoice.status)}</span>} />
          <StatCard label="合计 Total" value={invoice.currency + " " + invoice.total.toFixed(2)} tone="info" />
          <StatCard label="行项目 Line Items" value={String((invoice.line_items ?? []).length)} />
        </div>

        <Panel title="行项目 Line Items">
          {invoice.line_items && invoice.line_items.length > 0 ? (
            <Table
              columns={[
                { key: "metric", header: "指标 Metric" },
                { key: "amount", header: "数量 Amount", align: "right" as const },
                { key: "unit_price", header: "单价 Unit Price", align: "right" as const },
                { key: "amount_total", header: "金额 Amount", align: "right" as const },
              ]}
              rows={invoice.line_items}
              rowKey={(item, i) => String(i)}
              emptyTitle="无行项目"
            />
          ) : (
            <Empty text="无行项目" />
          )}
        </Panel>

        <div style={{ marginTop: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Button
            variant="primary"
            size="sm"
            disabled={invoiceTransitioning || invoice.status === "issued" || invoice.status === "paid"}
            onClick={() => transitionStatus("issued")}
          >
            {invoice.status === "draft" ? "开具 Issued" : "已开具 Issued"}
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={invoiceTransitioning || invoice.status !== "issued"}
            onClick={() => transitionStatus("paid")}
          >
            {invoice.status === "paid" ? "已支付 Paid" : "标记支付 Paid"}
          </Button>
          {invoiceTransitionError && (
            <span className="errorbox" style={{ marginLeft: "auto" }}>{invoiceTransitionError}</span>
          )}
        </div>
      </>
    );
  };

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

  // ... rest of the component (useEffect, render, etc.)

  const s = summary;
  const status = (job.status || "").toUpperCase();
  const statusHelp = STATUS_HELP[status] || ["查看本次验证结果", "结合需求覆盖与风险证据判断本次改动，未验证项需要进一步确认。"];
  const latest = live[live.length - 1];
  const findingCount = findings ? findings.count : 0;
  // #169: `coverage_reason` is ONE joined string for every non-VERIFIED outcome
  // (evidence/verdict.py emits 零检查 / 记录格式与覆盖不一致 / 「存在 N 项已确认问题」 /
  // 「执行过程有错误」, and release_gate_veto adds the 「RELEASE 档发布门」 refusals).
  // Only a recorded row count of 0 proves「没有形成可执行的检查项」; an absent count —
  // a summary persisted before rows reached the summary (agent/worker.py
  //::_matrix_rows_for_summary) — is unknown, and must not be read as 0.
  const rowsTotal = typeof s?.matrix_rows_total === "number" ? s.matrix_rows_total : null;
  // Answer "下一步做什么" with one primary action chosen from the outcome,
  // instead of a fixed link that ignores whether there are risks to review.
  const nextAction: { label: string; run: () => void } | null =
    status === "BLOCKED" && findingCount > 0
      ? { label: "查看 " + findingCount + " 条风险并处理 →", run: () => setTab("findings") }
      : status === "VERIFIED"
      ? { label: "查看验证报告 →", run: () => setTab("certificate") }
      : !!s?.coverage_reason && rowsTotal === 0
      ? { label: "了解如何补全验证 →", run: () => { window.location.hash = "#/guide"; } }
      : s?.coverage_reason
      ? { label: "逐项查看未确认的验收条件 →", run: () => { window.location.hash = "#/matrix"; } }
      : null;
  const caps: string[] = [];
  if (findings) {
    findings.findings.forEach((f) => {
      if (f.capsule_path) caps.push(String(f.capsule_path));
    });
  }
  (s && s.capsules ? s.capsules : []).forEach((c) => {
    const name = String(c).split("/").pop() || String(c);
    if (!caps.includes(name)) caps.push(name);
  }

  // Guard clause: return early if job is null (after loading)
  if (!job) {
    return <div className="verification-page">加载中...</div>;
  }

  const tabBtn = (t: Tab, label: string) => (
    <button type="button" role="tab" aria-selected={tab === t} className={"tab" + (tab === t ? " tab-active" : "")} onClick={() => setTab(t)}>
      {label}
    </button>
  );

  return (
    <div className="verification-page">
      <Breadcrumbs items={[{ label: "验证记录", href: "#/jobs" }, { label: "验证详情" }]} />
      <div className="page-head">
        <h1>
          验证 {shortId(jobId)} <StatusPill status={job.status || ""} />
        </h1>
        <div className="page-sub">
          {(job.base_ref || "—") + " → " + (job.head_ref || "—") + " · " + (job.repo_path || "—")}
        </div>
      </div>
      <ErrorBox error={artifactError} />
      {summary?.coverage_reason && <div className="degraded" role="status"><strong>本次验收结论未能确认</strong><p>{summary.coverage_reason}</p>{rowsTotal === 0 ? <a href="#/guide">了解支持的验收方式 →</a> : <a href="#/matrix">逐项查看未确认的验收条件 →</a>}</div>}
      <div className="verification-detail-banner" aria-live="polite"><h2>{summary?.coverage_reason ? rowsTotal === 0 ? "覆盖不足，暂不能确认验收通过" : "本次不能确认验收通过" : statusHelp[0]}</h2><p>{summary?.coverage_reason ? rowsTotal === 0 ? "本次没有形成可执行的检查项。请完善验收条件，或接入对应检查器后重新验收。" : rowsTotal === null ? "请查看上方原因，并结合需求覆盖与风险证据判断本次结论。" : "本次已形成 " + rowsTotal + " 项检查，结论仍不能确认为通过。请查看上方原因，并结合需求覆盖与风险证据判断。" : statusHelp[1]}</p>
      {ACTIVE.has(status) ? <Progress value={latest?.percentage ?? latest?.percent ?? 0} label={latest?.summary || latest?.message || "等待执行进度"} showValue /> : null}
      {nextAction ? <div className="next-action" role="group" aria-label="下一步操作"><span>下一步：</span><Button size="sm" variant="primary" onClick={nextAction.run}>{nextAction.label}</Button></div> : null}
      <div style={{ display: "flex", gap: 12, marginTop: 18 }}><Button size="sm" variant="ghost" onClick={() => setRefresh((value) => value + 1)}>刷新结果</Button><a href="#/matrix">查看需求覆盖 →</a><a href={"#/audit?job=" + encodeURIComponent(jobId)}>查看这个作业的审计轨迹 →</a></div>
      </div>

      <div className="tabs" role="tablist" aria-label="验证详情">
        {tabBtn("overview", "验证概览")}
        {tabBtn("stages", "执行进度")}
        {tabBtn("findings", "风险发现 (" + (findings ? findings.count : 0) + ")")}
        {tabBtn("certificate", "验证报告")}
        {tabBtn("invoice", "发票")}
      </div>

      {tab === "overview" ? (
        <>
          {s ? (
            <>
              <div className="stat-grid" style={{ marginBottom: 16 }}>
                <StatCard label="验证结论" value={verdictLabel(s.verdict)} tone={verdictTone(s.verdict)} />
                <StatCard label="验收条件" value={s.contracts_total ?? "—"} />
                <StatCard label="已通过" value={s.matrix_passed ?? "—"} tone="ok" />
                <StatCard label="未通过" value={s.matrix_failed ?? "—"} tone="bad" />
                <StatCard label="尚未验证" value={s.matrix_unverified ?? "—"} tone="warn" />
              </div>
              <div>
                <PreflightCard preflight={s.preflight} />
                <Panel title="证据与产物">
                  {kv("报告路径", s.report_path || "—")}
                  {kv("检索说明", s.retrieval_note || "—")}
                  {s.errors && s.errors.length > 0 ? (
                    <>
                      <div className="kv-label" style={{ margin: "8px 0 4px" }}>执行记录</div>
                      {s.errors.map((e, i) => (
                        <div key={i} className="errorbox" style={{ marginBottom: 6 }} title={String(e)}>{describePipelineError(String(e))}</div>
                      ))}
                    </>
                  ) : null}
                </Panel>
                {s.deep_results && Object.keys(s.deep_results).length > 0 ? (
                  <Panel title="DEEP 深度验证披露">
                    {kv("执行说明", s.deep_note || "—")}
                    {s.deep_results.verdict_stability
                      ? kv(
                          "结论稳定性",
                          deepClassificationLabel(s.deep_results.verdict_stability.classification)
                            + (s.deep_results.verdict_stability.repeat_count
                              ? "（" + s.deep_results.verdict_stability.repeat_count + " 次重复运行）"
                              : ""),
                        )
                      : null}
                    {s.deep_results.cache_integrity ? kv("缓存完整性", s.deep_results.cache_integrity) : null}
                    {s.deep_results.deep_report_file ? kv("深度报告", s.deep_results.deep_report_file) : null}
                  </Panel>
                ) : null}
              </div>
            </>
          ) : summaryLoadFailed ? (
            <div className="errorbox" role="alert">验证结果暂时无法读取（请求失败）— 这不代表没有结果，请点击刷新重试。</div>
          ) : ACTIVE.has(status) ? (
            <Empty text="验证仍在执行中，完成后这里会展示结论、需求覆盖与风险证据。" />
          ) : status === "FAILED" ? (
            <>
              <Empty text="这一轮以执行失败结束，记录里没有验证摘要。" />
              <p className="degraded">失败不会随刷新补出摘要：结论、覆盖与风险要在一次新的验证里重新产生。下方"最近执行错误"说明这一轮失败的原因，"执行进度"说明它停在哪一步。</p>
            </>
          ) : TERMINAL.has(status) ? (
            <>
              <Empty text="任务已进入终态，但记录里没有验证摘要。" />
              <p className="degraded">这条不会随刷新补上。终态与摘要现在是同一条写入，因此读不到摘要意味着这一轮的证据当时就没有落库（多为该改动之前完成的历史任务）。可以用"执行进度"和"风险发现"判断这一轮走到哪里，需要结论时重新发起验证。</p>
            </>
          ) : (
            <>
              <Empty text={"任务状态为 " + (status || "（空）") + "，这是本页面未识别的状态，且记录里没有验证摘要。"} />
              <p className="muted">未识别状态既不等于已终态，也不等于仍在执行，所以这里不下结论。</p>
            </>
          )}
          <Panel title="任务信息">
            {kv("项目路径", job.repo_path || "—")}
            {kv("比较版本", (job.base_ref || "—") + " → " + (job.head_ref || "—"))}
            {kv("需求文件", job.spec_path || "—")}
            {kv("验证模式", depthLabel(job.depth))}
            {kv("重试次数", String(job.retry_count ?? 0))}
            {kv("创建时间", fmtTime(job.created_at))}
            {kv("更新时间", fmtTime(job.updated_at))}
            {job.last_error ? <div className="kv-label" style={{ margin: "8px 0 4px" }}>最近执行错误</div> : null}
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
          title={"执行阶段 · " + (sseState === "open" ? "实时更新中" : ACTIVE.has(status) ? "正在连接进度" : "执行已结束")}
        >
          {stages && stages.degraded ? <Degraded reasons={[stages.degraded_reason || "redis unavailable"]} /> : null}
          {stages && stages.stages.length === 0 ? (
            <Empty text="暂无执行进度，任务可能尚未开始。" />
          ) : (
            stages && stages.stages.map((st) => (
              <div className="stage-row" key={st.node}>
                <span className="stage-node" title={st.node}>{stageLabel(st.node)}</span>
                <span className="stage-msg">{st.message || st.status}</span>
                <div className="bar" style={{ width: 120, margin: 0 }}>
                  <div className="bar-fill" style={{ width: Math.min(100, st.percent) + "%" }} />
                </div>
                <span className="stage-pct">{st.percent}%</span>
                <StatusPill status={st.status} />
              </div>
            ))
          )}
          <div style={{ marginTop: 14 }}>
            <div className="kv-label">实时执行日志</div>
            <div className="console">
              {live.length === 0
                ? "[等待进度事件…]\n"
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
        <Panel title={"风险发现 (" + (findings ? findings.count : 0) + ")"}>
          {findings && findings.degraded ? <Degraded reasons={[findings.degraded_reason || "degraded"]} /> : null}
          {findingsLoadFailed ? (
            <div className="errorbox" role="alert">风险扫描结果暂时无法读取（请求失败）— 无法确认是否存在风险，请勿据此判定为安全；点击刷新重试。</div>
          ) : !findings || findings.findings.length === 0 ? (
            <Empty text="暂未发现已确认的问题。请同时检查需求覆盖情况；没有风险记录不代表所有需求均已验证。" />
          ) : (
            <Table<Finding>
              columns={findingColumns(jobId)}
              rows={findings.findings}
              rowKey={(f, i) => f.id || String(i)}
            />
          )}
        </Panel>
      ) : null}

      {tab === "certificate" ? (
        <Panel title={<Term id="certificate">合并证书 / 拒绝通知</Term>}>
          {certError ? <div className="errorbox">{certError}</div> : null}
          {cert ? (
            <>
              {kv("证书文件", cert.path)}
              {cert.signed_path ? kv("签名文件", cert.signed_path) : null}
              {cert.signed_statement ? (
                <>
                  <div className="kv-label" style={{ margin: "10px 0 6px" }}>签名声明（in-toto 风格，供审计核验）</div>
                  <pre className="json">{JSON.stringify(cert.signed_statement, null, 2)}</pre>
                </>
              ) : (
                <div className="muted" style={{ margin: "8px 0" }}>
                  暂无 Ed25519 签名文件（未配置签名密钥时，仅提供未签名摘要 —— 如实呈现，不伪造可信签名）。
                </div>
              )}
              <div className="kv-label" style={{ margin: "10px 0 6px" }}>证书内容（原始 JSON）</div>
              <pre className="json">{JSON.stringify(cert.document, null, 2)}</pre>
            </>
          ) : null}
        </Panel>
      ) : null}

      {tab === "invoice" ? (
        <Panel title="发票 Invoice">
          {renderInvoiceContent()}
        </Panel>
      ) : null}

      {tab === "capsule" ? (
        <Panel title={<Term id="capsule">复现包下载</Term>}>
          {caps.map((c) => (
            <Button key={c} variant="ghost" size="sm" style={{ marginRight: 8 }} onClick={() => downloadCapsule(jobId, c.split("/").pop())}>
              ↓ {c.split("/").pop()}
            </Button>
          ))}
        </Panel>
      ) : null}
    </div>
  );
};

export default JobDetail;