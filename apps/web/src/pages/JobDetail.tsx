import { useEffect, useState } from "react";
import {
  apiGet, CertificateData, downloadCapsule, Finding, FindingsData, Job, openProgressStream,
  ProgressEvent, StagesData,
} from "../api";
import {
  Breadcrumbs, Button, Degraded, Empty, ErrorBox, Panel, PreflightCard, Progress, Spinner, StatCard, StatusPill, Table, Term,
  fmtPct, fmtTime, kv, shortId, severityPill, severityHint, evidenceLabel, stageLabel, verdictTone, verdictLabel,
  type Column, type PreflightResult,
} from "../ui";
import { recordRecentJob } from "../ui/recentJobs";
import { describePipelineError, loadFailed } from "../ui/errorHints";
import "../styles/verification.css";

interface Summary {
  coverage_reason?: string;
  verdict?: string;
  contracts_total?: number;
  matrix_passed?: number;
  matrix_failed?: number;
  matrix_unverified?: number;
  findings?: unknown[];
  capsules?: string[];
  report_path?: string;
  retrieval_note?: string;
  errors?: string[];
  preflight?: PreflightResult;
}

type Tab = "overview" | "stages" | "findings" | "certificate";
const ACTIVE = new Set(["QUEUED", "RUNNING", "PENDING", "WAITING_FOR_PROVIDER"]);
const TERMINAL = new Set(["VERIFIED", "BLOCKED", "STALE", "CANCELLED", "ERROR"]);
const STATUS_HELP: Record<string, [string, string]> = {
  QUEUED: ["验证已创建，等待执行", "执行服务接手后，进度会自动出现在这里。可以先离开，稍后从验证记录继续查看。"],
  RUNNING: ["正在检查代码与需求", "系统正在分析改动、收集证据并核对需求。完成后会自动更新结论。"],
  WAITING_FOR_PROVIDER: ["正在等待模型服务", "任务已保存，模型服务恢复可用后将继续处理。"],
  VERIFIED: ["本次验证通过", "已验证的需求具备支持证据。合并前建议确认需求覆盖范围，以及是否仍有未验证项。"],
  BLOCKED: ["发现需要处理的问题", "先查看风险发现及其证据，再决定如何修改代码。需求矩阵可帮助定位受影响的验收条件。"],
  FAILED: ["本次验证未能完成", "执行失败不代表代码有问题。请查看任务信息中的错误原因，处理环境或服务问题后重新验证。"],
  CANCELLED: ["验证已取消", "本次执行已停止，需要继续时可以创建新的验证任务。"],
  STALE: ["本次验证已过期", "代码版本可能已变化，请基于最新提交重新验证。"],
  ERROR: ["执行遇到错误", "请查看错误原因，处理执行环境或服务问题后重新验证。"],
  UNVERIFIED: ["目前证据不足", "部分需求尚无法确认，请查看未验证项，并补充验收条件、测试或执行环境。"],
};

// Verification depth arrives as an English enum (FAST / STANDARD / DEEP). Gloss
// known values as "中文 · token"; pass an unexpected value through verbatim so
// we never assert a depth the backend didn't report.
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

// Severity ordering for the findings table: the canonical enum values are
// normalized into a rank so sorting puts the most actionable risks first,
// while unrecognized/absent severities sink to the bottom rather than being
// silently re-labeled.
const SEVERITY_RANK: Record<string, number> = {
  BLOCKER: 0, CRITICAL: 0, MAJOR: 1, HIGH: 1, MINOR: 2, MEDIUM: 2, INFO: 3, LOW: 3, NONE: 4,
};
function sevRank(s?: string): number {
  return s ? SEVERITY_RANK[s.toUpperCase()] ?? 9 : 99;
}

function findingColumns(jobId: string): Column<Finding>[] {
  return [
    {
      key: "severity",
      header: "严重程度",
      sortable: true,
      sortValue: (f) => sevRank(f.severity),
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

export default function JobDetail(props: { jobId: string }) {
  const { jobId } = props;
  const [tab, setTab] = useState<Tab>("overview");
  const [job, setJob] = useState<Job | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [stages, setStages] = useState<StagesData | null>(null);
  const [findings, setFindings] = useState<FindingsData | null>(null);
  const [cert, setCert] = useState<CertificateData | null>(null);
  const [certError, setCertError] = useState<string | null>(null);
  const [error, setError] = useState<Error | string | null>(null);
  const [artifactError, setArtifactError] = useState<string | null>(null);
  // Per-artifact: did the read genuinely FAIL (network/5xx) vs return empty/404?
  // A failed risk scan must never be rendered as a clean "no findings" scan.
  const [summaryLoadFailed, setSummaryLoadFailed] = useState(false);
  const [findingsLoadFailed, setFindingsLoadFailed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [live, setLive] = useState<ProgressEvent[]>([]);
  const [sseState, setSseState] = useState<string>("closed");
  const [refresh, setRefresh] = useState(0);

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
      setArtifactError(failed.length ? "部分验证结果暂时无法读取，任务状态仍可查看。点击刷新可重试。" : null);
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
              const stage = { node, status: event.status || "", percent: event.percentage ?? event.percent ?? 0, message: event.summary || event.message || "", at: event.ts || "", event_id: String(event.sequence ?? event.seq ?? "") };
              const rows = currentStages?.stages || [];
              return { job_id: jobId, stages: rows.some((row) => row.node === node) ? rows.map((row) => row.node === node ? stage : row) : [...rows, stage], event_count: (currentStages?.event_count || 0) + 1, degraded: false, degraded_reason: null };
            });
          }, (state) => { if (alive) setSseState(state); });
        }
        if (initial || (terminal && currentStatus !== previousStatus)) await loadArtifacts();
        previousStatus = currentStatus;
        if (initial) recordRecentJob("#/jobs/" + encodeURIComponent(jobId), (current.repo_path || "验证") + " · " + shortId(current.id));
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
    return () => {
      alive = false;
      controller.abort();
      closeStream?.();
      window.clearInterval(poll);
    };
  }, [jobId, refresh]);

  useEffect(() => {
    if (tab !== "certificate") return;
    const controller = new AbortController();
    let alive = true;
    setCertError(null);
    apiGet<CertificateData>("/api/v1/jobs/" + encodeURIComponent(jobId) + "/certificate", controller.signal)
      .then((data) => { if (alive) setCert(data); })
      .catch((e: { status?: number; message?: string }) => {
        if (alive) setCertError(e.status === 404 ? "暂未生成验证报告，任务完成后可再次查看。" : e.message || "报告读取失败");
      });
    return () => { alive = false; controller.abort(); };
  }, [tab, jobId, job?.status]);

  if (loading) return <Spinner />;
  if (!job) {
    return (
      <div>
        <ErrorBox error={error || "任务不存在 (404)"} />
        <Button onClick={() => setRefresh((value) => value + 1)}>重试</Button>{" "}
        <a href="#/jobs">← 返回任务列表</a>
      </div>
    );
  }

  const s = summary;
  const status = (job.status || "").toUpperCase();
  const statusHelp = STATUS_HELP[status] || ["查看本次验证结果", "结合需求覆盖与风险证据判断本次改动，未验证项需要进一步确认。"];
  const latest = live[live.length - 1];
  const findingCount = findings ? findings.count : 0;
  // Answer "下一步做什么" with one primary action chosen from the outcome,
  // instead of a fixed link that ignores whether there are risks to review.
  const nextAction: { label: string; run: () => void } | null =
    status === "BLOCKED" && findingCount > 0
      ? { label: "查看 " + findingCount + " 条风险并处理 →", run: () => setTab("findings") }
      : status === "VERIFIED"
      ? { label: "查看验证报告 →", run: () => setTab("certificate") }
      : status === "UNVERIFIED" || !!s?.coverage_reason
      ? { label: "了解如何补全验证 →", run: () => { window.location.hash = "#/guide"; } }
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
  });

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
      <ErrorBox error={error || artifactError} />
      {summary?.coverage_reason && <div className="degraded" role="status"><strong>验收覆盖不足</strong><p>{summary.coverage_reason}</p><a href="#/guide">了解支持的验收方式 →</a></div>}
      <div className="verification-detail-banner" aria-live="polite"><h2>{summary?.coverage_reason ? "覆盖不足，暂不能确认验收通过" : statusHelp[0]}</h2><p>{summary?.coverage_reason ? "本次没有形成可执行的检查项。请完善验收条件，或接入对应检查器后重新验收。" : statusHelp[1]}</p>
        {ACTIVE.has(status) ? <Progress value={latest?.percentage ?? latest?.percent ?? 0} label={latest?.summary || latest?.message || "等待执行进度"} showValue /> : null}
        {nextAction ? <div className="next-action" role="group" aria-label="下一步操作"><span>下一步：</span><Button size="sm" variant="primary" onClick={nextAction.run}>{nextAction.label}</Button></div> : null}
        <div style={{ display: "flex", gap: 12, marginTop: 18 }}><Button size="sm" variant="ghost" onClick={() => setRefresh((value) => value + 1)}>刷新结果</Button><a href="#/matrix">查看需求覆盖 →</a></div>
      </div>

      <div className="tabs" role="tablist" aria-label="验证详情">
        {tabBtn("overview", "验证概览")}
        {tabBtn("stages", "执行进度")}
        {tabBtn("findings", "风险发现 (" + (findings ? findings.count : 0) + ")")}
        {tabBtn("certificate", "验证报告")}
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
              </div>
            </>
          ) : summaryLoadFailed ? (
            <div className="errorbox" role="alert">验证结果暂时无法读取（请求失败）— 这不代表没有结果，请点击刷新重试。</div>
          ) : (
            <Empty text="验证结果尚未生成。执行完成后，这里会展示结论、需求覆盖与风险证据。" />
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
          </Panel>
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
                    .join("\n")}
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

      {caps.length > 0 ? (
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
}
