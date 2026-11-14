import { useEffect, useMemo, useState } from "react";
import { apiGet, type Finding, type JobsPage, type Job } from "../api";
import { ErrorBox, Panel, StatCard, fmtTime, evidenceLabel, severityPill } from "../ui";
import "../styles/verification.css";

// 案件档案 · The Case File — 给最近一桩验收的 verdict 装订成可读的「案卷」。
// **绝不用 LLM 编造叙事**：每一句都由服务端真实返回的数字编译而成，
// 缺什么就写什么（未提供），绝不编造。判决仍由确定性证据决定。

interface CaseSummary {
  verdict?: string;
  contracts_total?: number;
  matrix_passed?: number;
  matrix_failed?: number;
  matrix_unverified?: number;
  capsules?: string[];
  report_path?: string;
  errors?: string[];
}

const EVIDENCE_TIER: Record<string, { tier: string; rank: number }> = {
  base_pass_head_fail: { tier: "铁", rank: 1 },
  differential_execution: { tier: "铁", rank: 2 },
  probe_differential: { tier: "半铁", rank: 3 },
  static_analysis: { tier: "静", rank: 4 },
  constitution_check: { tier: "静", rank: 5 },
  java_source_diff: { tier: "静", rank: 5 },
  runtime_diff: { tier: "铁", rank: 2 },
  differential_diff: { tier: "铁", rank: 2 },
  source_diff: { tier: "静", rank: 5 },
  manual_review: { tier: "文", rank: 7 },
  checker_failed: { tier: "坏", rank: 6 },
  self_test_diff: { tier: "文", rank: 7 },
};

const tierOf = (e?: string): { tier: string; rank: number } =>
  (e && EVIDENCE_TIER[e]) || { tier: "?", rank: 9 };

const verdictEpic = (v: string | undefined | null): string => {
  if (!v) return "待议";
  if (v === "VERIFIED") return "验讫";
  if (v === "BLOCKED") return "受阻";
  if (v === "NEEDS_REVIEW") return "待议";
  if (v === "FAILED") return "执行未成";
  if (v === "CANCELLED") return "中辍";
  return v;
};

function unwrap<T>(wrapped: T | { summary?: T } | { job?: T } | null | undefined): T | null {
  if (!wrapped) return null;
  if (typeof wrapped !== "object") return wrapped as T;
  const obj = wrapped as Record<string, unknown>;
  if ("summary" in obj && obj.summary !== undefined) return obj.summary as T;
  if ("job" in obj && obj.job !== undefined) return obj.job as T;
  return wrapped as T;
}

export default function Explorer() {
  const [job, setJob] = useState<Job | null>(null);
  const [summary, setSummary] = useState<CaseSummary | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | string | null>(null);

  const queryJobId = useMemo(() => {
    try {
      const m = window.location.hash.match(/[?&]job=([^&]+)/);
      return m ? decodeURIComponent(m[1]) : null;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        if (queryJobId) {
          const [jw, s, f] = await Promise.all([
            apiGet<{ job: Job }>("/jobs/" + encodeURIComponent(queryJobId)),
            apiGet<{ summary?: CaseSummary }>("/jobs/" + encodeURIComponent(queryJobId) + "/summary"),
            apiGet<{ findings: Finding[] }>("/api/v1/jobs/" + encodeURIComponent(queryJobId) + "/findings"),
          ]);
          if (alive) { setJob(jw?.job ?? null); setSummary(unwrap(s)); setFindings(f.findings || []); }
        } else {
          const list = await apiGet<JobsPage>("/jobs?limit=1");
          const latest = list.jobs?.[0];
          if (!latest) {
            if (alive) { setJob(null); setLoading(false); }
            return;
          }
          const [s, f] = await Promise.all([
            apiGet<{ summary?: CaseSummary }>("/jobs/" + encodeURIComponent(latest.id) + "/summary"),
            apiGet<{ findings: Finding[] }>("/api/v1/jobs/" + encodeURIComponent(latest.id) + "/findings"),
          ]);
          if (alive) { setJob(latest); setSummary(unwrap(s)); setFindings(f.findings || []); }
        }
      } catch (e) {
        if (alive) setError(e as Error);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [queryJobId]);

  const ironCount = findings.filter((f) => tierOf(f.evidence_type).rank <= 2).length;
  const steelCount = findings.filter((f) => tierOf(f.evidence_type).rank >= 4).length;
  const verdictWord = summary?.verdict ?? "";

  if (error) {
    return (
      <div className="case-explorer-page">
        <div className="page-head"><h1>案件档案 <span className="case-en">The Case File</span></h1></div>
        <ErrorBox error={error} />
      </div>
    );
  }

  return (
    <div className="case-explorer-page">
      <div className="page-head">
        <h1>案件档案 <span className="case-en">The Case File</span></h1>
        <div className="page-sub" title="CASE FILE — IRON EVIDENCE ONLY">
          一份装订机与印章构成的案卷——所有字句都来自服务器返回的数字，没有 LLM 给的文学一致性。
        </div>
      </div>

      <Panel title="印章">
        {loading ? (
          <p className="muted">装订前翻检…</p>
        ) : !job ? (
          <p className="muted">本机没有一桩验收记录尚可装订。先去完成一次验收，再来翻案。</p>
        ) : (
          <div className="case-verdict-block">
            <div
              className={
                "case-seal" +
                (verdictWord === "VERIFIED" ? " case-seal-verified"
                  : verdictWord === "BLOCKED" ? " case-seal-blocked"
                  : " case-seal-pending")
              }
            >
              {verdictEpic(verdictWord)}
            </div>
            <div className="case-meta">
              <div className="case-meta-row"><span className="case-meta-key">仓库</span><code className="case-meta-val">{job.repo_path ?? "未提供"}</code></div>
              <div className="case-meta-row"><span className="case-meta-key">变更</span><code className="case-meta-val">{job.base_ref ?? "未提供"} → {job.head_ref ?? "未提供"}</code></div>
              <div className="case-meta-row"><span className="case-meta-key">开卷日期</span><code className="case-meta-val">{job.created_at ? fmtTime(job.created_at) : "未提供"}</code></div>
              <div className="case-meta-row"><span className="case-meta-key">案卷号</span><code className="case-meta-val">{job.id}</code></div>
            </div>
          </div>
        )}
      </Panel>

      {job ? (
        <>
          <div className="stat-grid" style={{ marginBottom: 12 }}>
            <StatCard label="验收条件" value={summary?.contracts_total ?? "未提供"} tone="mute" />
            <StatCard label="已通过" value={summary?.matrix_passed ?? "未提供"} tone="ok" />
            <StatCard label="未通过" value={summary?.matrix_failed ?? "未提供"} tone={summary?.matrix_failed ? "bad" : "ok"} />
            <StatCard label="未验证" value={summary?.matrix_unverified ?? "未提供"} tone={summary?.matrix_unverified ? "warn" : "ok"} />
          </div>

          <Panel title="铁证清单">
            {findings.length === 0 ? (
              <p className="muted">此案无发现——这不等于没有缺陷，只等于本次验收未逮到。缺什么铁证，就该补什么证据。</p>
            ) : (
              <div className="case-evidence-grid">
                {findings.slice(0, 8).map((f, i) => {
                  const { tier } = tierOf(f.evidence_type);
                  return (
                    <div className={"case-evidence tier-" + tier} key={(f.id ?? i) + String(f.contract_id ?? "") + String(i)}>
                      <span className="case-evidence-letter">{tier}</span>
                      <div className="case-evidence-body">
                        <div className="case-evidence-head">
                          <span className="case-evidence-contract">{f.contract_id ?? "未提供"}</span>
                          {(() => {
                            const pill = severityPill(String(f.severity ?? "MINOR"));
                            return <span className={"pill " + pill.cls} title={pill.label}>{pill.label}</span>;
                          })()}
                        </div>
                        <div className="case-evidence-type">{evidenceLabel(f.evidence_type)}</div>
                        {f.description ? <p className="case-evidence-desc">{f.description}</p> : null}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
            <p className="case-verdict-tally">
              {ironCount} 项铁证 · {steelCount} 项静证 · 共 {findings.length} 桩发现。
              此案{summary?.verdict ? `被判为「${verdictEpic(summary.verdict)}」` : "未获裁决"}——
              {job.status ? `执行轨迹：${job.status}` : ""}。AI 在本案中没有作决定，证据替它开口。
            </p>
          </Panel>

          <Panel title="案卷索取">
            <div className="case-capsule-list">
              {summary?.capsules && summary.capsules.length > 0
                ? summary.capsules.slice(0, 5).map((c) => <code key={c} className="case-capsule">{c}</code>)
                : <span className="muted">本卷未交出复现包（可能是 DEMO 演示卷——请看全程）</span>}
              {summary?.report_path ? <div className="case-report-path"><span className="case-meta-key">报告路径</span><code>{summary.report_path}</code></div> : null}
            </div>
          </Panel>
        </>
      ) : null}
    </div>
  );
}
