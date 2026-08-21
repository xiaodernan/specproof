import { useCallback, useEffect, useRef, useState } from "react";
import {
  apiGet, CertificateData, downloadCapsule, FindingsData, Job, openProgressStream,
  ProgressEvent, StagesData,
} from "../api";
import {
  Button, Degraded, Empty, ErrorBox, Panel, Spinner, StatCard, StatusPill,
  fmtPct, fmtTime, kv, shortId, severityPill, verdictTone,
} from "../ui";
import { recordRecentJob } from "../ui/recentJobs";

interface Summary {
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
}

type Tab = "overview" | "stages" | "findings" | "certificate";

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
  const [loading, setLoading] = useState(true);
  const [live, setLive] = useState<ProgressEvent[]>([]);
  const [sseState, setSseState] = useState<string>("closed");
  const liveRef = useRef<ProgressEvent[]>([]);

  const loadAll = useCallback(async () => {
    try {
      const [j, s, st, f] = await Promise.all([
        apiGet<{ job: Job }>("/jobs/" + encodeURIComponent(jobId)),
        apiGet<{ summary: Summary }>("/jobs/" + encodeURIComponent(jobId) + "/summary"),
        apiGet<StagesData>("/api/v1/jobs/" + encodeURIComponent(jobId) + "/stages"),
        apiGet<FindingsData>("/api/v1/jobs/" + encodeURIComponent(jobId) + "/findings"),
      ]);
      setJob(j.job);
      setSummary(s.summary || null);
      setStages(st);
      setFindings(f);
      recordRecentJob(
        window.location.hash,
        (j.job.repo_path ? j.job.repo_path + " · " + shortId(j.job.id) : "任务 " + shortId(j.job.id))
      );
    } catch (e) {
      setError(e as Error);
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  const loadStages = useCallback(async () => {
    try {
      const st = await apiGet<StagesData>("/api/v1/jobs/" + encodeURIComponent(jobId) + "/stages");
      setStages(st);
    } catch {
      // keep previous stage snapshot; degradation stays visible
    }
  }, [jobId]);

  const loadCert = useCallback(async () => {
    setCertError(null);
    setCert(null);
    try {
      const c = await apiGet<CertificateData>("/api/v1/jobs/" + encodeURIComponent(jobId) + "/certificate");
      setCert(c);
    } catch (e) {
      const err = e as { status?: number; message?: string };
      if (err && err.status === 404) setCertError("该任务没有持久化的证书/拒绝通知 (管线未签发或尚未运行 — 诚实 404)");
      else setCertError(err && err.message ? err.message : "证书读取失败");
    }
  }, [jobId]);

  useEffect(() => {
    loadAll();
    loadCert();
    const close = openProgressStream(
      jobId,
      (ev) => {
        liveRef.current = [...liveRef.current.slice(-199), ev];
        setLive(liveRef.current);
      },
      (state) => setSseState(state)
    );
    const poll = window.setInterval(loadStages, 5000);
    return () => {
      close();
      window.clearInterval(poll);
    };
  }, [jobId, loadAll, loadCert, loadStages]);

  if (loading) return <Spinner />;
  if (!job) {
    return (
      <div>
        <ErrorBox error={error || "任务不存在 (404)"} />
        <a href="#/jobs">← 返回任务列表</a>
      </div>
    );
  }

  const s = summary;
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
    <div className={"tab" + (tab === t ? " tab-active" : "")} onClick={() => setTab(t)}>
      {label}
    </div>
  );

  return (
    <div>
      <div className="page-head">
        <h1 className="mono">
          任务 {jobId} <StatusPill status={job.status || ""} />
        </h1>
        <div className="page-sub">
          {(job.base_ref || "—") + " → " + (job.head_ref || "—") + " · " + (job.repo_path || "—")}
        </div>
      </div>
      <ErrorBox error={error} />

      <div className="tabs">
        {tabBtn("overview", "概览 Overview")}
        {tabBtn("stages", "阶段 Stages")}
        {tabBtn("findings", "Findings (" + (findings ? findings.count : 0) + ")")}
        {tabBtn("certificate", "证书 Certificate")}
      </div>

      {tab === "overview" ? (
        <>
          {s ? (
            <>
              <div className="stat-grid" style={{ marginBottom: 16 }}>
                <StatCard label="判定 Verdict" value={s.verdict || "—"} tone={verdictTone(s.verdict)} />
                <StatCard label="合约 Contracts" value={s.contracts_total ?? "—"} />
                <StatCard label="PASS" value={s.matrix_passed ?? "—"} tone="ok" />
                <StatCard label="FAIL" value={s.matrix_failed ?? "—"} tone="bad" />
                <StatCard label="UNVERIFIED" value={s.matrix_unverified ?? "—"} tone="warn" />
              </div>
              <div className="page-grid">
                <Panel title="任务信息">
                  {kv("Repo", job.repo_path || "—")}
                  {kv("Base → Head", (job.base_ref || "—") + " → " + (job.head_ref || "—"))}
                  {kv("Depth", job.depth || "—")}
                  {kv("Worker", job.worker_id || "—")}
                  {kv("重试 Retry", String(job.retry_count ?? 0))}
                  {kv("创建 Created", fmtTime(job.created_at))}
                  {kv("更新 Updated", fmtTime(job.updated_at))}
                  {job.last_error ? kv("Last Error", job.last_error) : null}
                </Panel>
                <Panel title="证据与产物 Artifacts">
                  {kv("Report", s.report_path || "—")}
                  {kv("Retrieval", s.retrieval_note || "—")}
                  {s.errors && s.errors.length > 0 ? (
                    <>
                      <div className="kv-label" style={{ margin: "8px 0 4px" }}>Pipeline Errors</div>
                      {s.errors.map((e, i) => (
                        <div key={i} className="errorbox" style={{ marginBottom: 6 }}>{String(e)}</div>
                      ))}
                    </>
                  ) : null}
                </Panel>
              </div>
            </>
          ) : (
            <Empty text="该任务暂无 pipeline summary (尚未完成或未持久化 — 诚实空态)" />
          )}
        </>
      ) : null}

      {tab === "stages" ? (
        <Panel
          title={"阶段时间线 (" + (stages ? stages.event_count : 0) + " 事件 · SSE " + sseState + ")"}
        >
          {stages && stages.degraded ? <Degraded reasons={[stages.degraded_reason || "redis unavailable"]} /> : null}
          {stages && stages.stages.length === 0 ? (
            <Empty text="暂无进度事件 (任务可能尚未开始, 或 Redis 进度流不可用)" />
          ) : (
            stages && stages.stages.map((st) => (
              <div className="stage-row" key={st.node}>
                <span className="stage-node">{st.node}</span>
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
            <div className="kv-label">实时 SSE 控制台 (auto-reconnect)</div>
            <div className="console">
              {live.length === 0
                ? "[等待进度事件…]\n"
                : live
                    .map((ev) => {
                      const stage = ev.stage || ev.node || "";
                      const pct = ev.percentage ?? ev.percent ?? 0;
                      const msg = ev.summary || ev.message || "";
                      return "[" + stage + "] " + (ev.status || "") + " " + pct + "% " + msg;
                    })
                    .join("\n")}
            </div>
          </div>
        </Panel>
      ) : null}

      {tab === "findings" ? (
        <Panel title={"Findings (" + (findings ? findings.count : 0) + ")"}>
          {findings && findings.degraded ? <Degraded reasons={[findings.degraded_reason || "degraded"]} /> : null}
          {!findings || findings.findings.length === 0 ? (
            <Empty text="无 confirmed findings (Review Court 未确认任何问题 — 诚实空态)" />
          ) : (
            <table className="data">
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>Contract</th>
                  <th>Evidence</th>
                  <th>Confidence</th>
                  <th>描述</th>
                  <th>Capsule</th>
                </tr>
              </thead>
              <tbody>
                {findings.findings.map((f, i) => {
                  const sev = severityPill(f.severity);
                  return (
                  <tr key={f.id || String(i)}>
                    <td><span className={"pill " + sev.cls}>{sev.label}</span></td>
                    <td className="mono">{f.contract_id || "—"}</td>
                    <td className="mono">{f.evidence_type || "—"}</td>
                    <td className="mono">{fmtPct(f.confidence)}</td>
                    <td>
                      <a href={"#/findings/" + jobId + "/" + (f.id || i)}>
                        {(f.description || "查看详情").slice(0, 120)}
                      </a>
                    </td>
                    <td>
                      {f.capsule_path ? (
                        <Button variant="ghost" size="sm" onClick={() => downloadCapsule(jobId, String(f.capsule_path).split("/").pop())}>
                          ↓ zip
                        </Button>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </Panel>
      ) : null}

      {tab === "certificate" ? (
        <Panel title="合并证书 / 拒绝通知">
          {certError ? <div className="errorbox">{certError}</div> : null}
          {cert ? (
            <>
              {kv("文件 Path", cert.path)}
              {cert.signed_path ? kv("签名件 Signed", cert.signed_path) : null}
              {cert.signed_statement ? (
                <>
                  <div className="kv-label" style={{ margin: "10px 0 6px" }}>Signed Statement (in-toto style)</div>
                  <pre className="json">{JSON.stringify(cert.signed_statement, null, 2)}</pre>
                </>
              ) : (
                <div className="muted" style={{ margin: "8px 0" }}>
                  无 Ed25519 签名件 (密钥未配置时保持未签名摘要 — 如实呈现)
                </div>
              )}
              <div className="kv-label" style={{ margin: "10px 0 6px" }}>Document</div>
              <pre className="json">{JSON.stringify(cert.document, null, 2)}</pre>
            </>
          ) : null}
        </Panel>
      ) : null}

      {caps.length > 0 ? (
        <Panel title="Capsule 下载">
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
