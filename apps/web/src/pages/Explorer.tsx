import { useEffect, useMemo, useState } from "react";
import { apiGet, type Finding, type JobsPage, type Job } from "../api";
import { ErrorBox, Panel, StatCard, fmtTime, evidenceLabel, severityPill } from "../ui";
import { useI18n } from "../i18n";
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

// The CSS class is an ASCII slug; the glyph shown to the reader stays the
// Chinese character (铁/半铁/静/坏/文/?). Keeping the two apart is what
// lets the stylesheet minify — a Chinese class name breaks the build.
const TIER_SLUG: Record<string, string> = {
  "铁": "iron",
  "半铁": "semi-iron",
  "静": "quiet",
  "坏": "broken",
  "文": "script",
  "?": "unknown",
};

const tierSlug = (tier: string): string => TIER_SLUG[tier] || "unknown";

const verdictEpicEn = (v: string | undefined | null): string => {
  if (!v) return "PENDING";
  if (v === "VERIFIED") return "SEALED";
  if (v === "BLOCKED") return "BLOCKED";
  if (v === "NEEDS_REVIEW") return "TO REVIEW";
  if (v === "FAILED") return "RUN FAILED";
  if (v === "CANCELLED") return "CANCELLED";
  return v;
};

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
  const { t, locale } = useI18n();
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
        <div className="page-head"><h1>{t("explorer.title")} <span className="case-en">{t("explorer.subtitle")}</span></h1></div>
        <ErrorBox error={error} />
      </div>
    );
  }

  return (
    <div className="case-explorer-page">
      <div className="page-head">
        <h1>{t("explorer.title")} <span className="case-en">{t("explorer.subtitle")}</span></h1>
        <div className="page-sub" title="CASE FILE — IRON EVIDENCE ONLY">
          {t("explorer.lead")}
        </div>
      </div>

      <Panel title={t("explorer.sealPanel")}>
        {loading ? (
          <p className="muted">{t("explorer.loading")}</p>
        ) : !job ? (
          <p className="muted">{t("explorer.empty")}</p>
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
              {locale === "zh" ? verdictEpic(verdictWord) : verdictEpicEn(verdictWord)}
            </div>
            <div className="case-meta">
              <div className="case-meta-row"><span className="case-meta-key">{t("explorer.repo")}</span><code className="case-meta-val">{job.repo_path ?? "未提供"}</code></div>
              <div className="case-meta-row"><span className="case-meta-key">{t("explorer.change")}</span><code className="case-meta-val">{job.base_ref ?? "未提供"} → {job.head_ref ?? "未提供"}</code></div>
              <div className="case-meta-row"><span className="case-meta-key">{t("explorer.opened")}</span><code className="case-meta-val">{job.created_at ? fmtTime(job.created_at) : "未提供"}</code></div>
              <div className="case-meta-row"><span className="case-meta-key">{t("explorer.caseNo")}</span><code className="case-meta-val">{job.id}</code></div>
            </div>
          </div>
        )}
      </Panel>

      {job ? (
        <>
          <div className="stat-grid" style={{ marginBottom: 12 }}>
            <StatCard label={t("explorer.conditions")} value={summary?.contracts_total ?? "未提供"} tone="mute" />
            <StatCard label={t("explorer.passed")} value={summary?.matrix_passed ?? "未提供"} tone="ok" />
            <StatCard label={t("explorer.failed")} value={summary?.matrix_failed ?? "未提供"} tone={summary?.matrix_failed ? "bad" : "ok"} />
            <StatCard label={t("explorer.unverified")} value={summary?.matrix_unverified ?? "未提供"} tone={summary?.matrix_unverified ? "warn" : "ok"} />
          </div>

          <Panel title={t("explorer.evidencePanel")}>
            {findings.length === 0 ? (
              <p className="muted">{t("explorer.noFindings")}</p>
            ) : (
              <div className="case-evidence-grid">
                {findings.slice(0, 8).map((f, i) => {
                  const { tier } = tierOf(f.evidence_type);
                  return (
                    <div className={"case-evidence tier-" + tierSlug(tier)} key={(f.id ?? i) + String(f.contract_id ?? "") + String(i)}>
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
              {locale === "zh"
                ? `${ironCount} 项铁证 · ${steelCount} 项静证 · 共 ${findings.length} 桩发现。此案${summary && summary.verdict ? `被判为「${verdictEpic(summary.verdict)}」` : "未获裁决"}——${job.status ? `执行轨迹：${job.status}` : ""}。AI 在本案中没有作决定，证据替它开口。`
                : `${ironCount} iron · ${steelCount} quiet · ${findings.length} findings in all. This case was judged 「${verdictEpic(summary && summary.verdict)}」${job.status ? ` — trail: ${job.status}` : ""}. The AI did not decide; the evidence spoke.`}
            </p>
          </Panel>

          <Panel title={t("explorer.capsulePanel")}>
            <div className="case-capsule-list">
              {summary?.capsules && summary.capsules.length > 0
                ? summary.capsules.slice(0, 5).map((c) => <code key={c} className="case-capsule">{c}</code>)
                : <span className="muted">{t("explorer.noCapsule")}</span>}
              {summary?.report_path ? <div className="case-report-path"><span className="case-meta-key">{t("explorer.reportPath")}</span><code>{summary.report_path}</code></div> : null}
            </div>
          </Panel>
        </>
      ) : null}
    </div>
  );
}
