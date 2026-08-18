import { useEffect, useState } from "react";
import { apiGet, EvalData } from "../api";
import { Empty, ErrorBox, Panel, Spinner, StatCard, fmtTime } from "../components";

export default function Eval() {
  const [data, setData] = useState<EvalData | null>(null);
  const [error, setError] = useState<Error | string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiGet<EvalData>("/api/v1/eval/latest")
      .then((d) => setData(d))
      .catch((e) => setError(e as Error))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spinner />;

  const r = data ? data.report : null;

  return (
    <div>
      <div className="page-head">
        <h1>评测 Evaluation</h1>
        <div className="page-sub">PRECISION / RECALL / F1 — 来自 docs/eval/eval-report.results.json</div>
      </div>
      <ErrorBox error={error} />

      {!data ? (
        <Empty text="评测报告不存在 (404 诚实返回 — 先运行评测管线)" />
      ) : (
        <>
          <div className="kv">
            <span className="kv-label">来源 Source</span>
            <span className="kv-value mono">{data.source}</span>
          </div>
          <div className="kv" style={{ marginBottom: 16 }}>
            <span className="kv-label">修改时间</span>
            <span className="kv-value">{fmtTime(data.modified_at)}</span>
          </div>

          <div className="stat-grid" style={{ marginBottom: 16 }}>
            <StatCard label="Precision 精确率" value={r && r.precision != null ? r.precision.toFixed(1) + "%" : "—"} tone="info" />
            <StatCard label="Recall 召回率" value={r && r.recall != null ? r.recall.toFixed(1) + "%" : "—"} tone="ok" />
            <StatCard label="F1" value={r && r.f1 != null ? r.f1.toFixed(1) + "%" : "—"} tone="warn" />
            <StatCard label="总案例" value={r ? (r.total_cases ?? "—") : "—"} />
            <StatCard label="应检出" value={r ? (r.should_detect ?? "—") : "—"} />
            <StatCard label="误报 FP" value={r ? (r.false_positives ?? "—") : "—"} tone={r && r.false_positives ? "bad" : "ok"} />
          </div>

          <Panel title={"案例明细 (" + (r && r.cases ? r.cases.length : 0) + ")"}>
            {!r || !r.cases || r.cases.length === 0 ? (
              <Empty text="无案例明细" />
            ) : (
              <table className="data">
                <thead>
                  <tr>
                    <th>Case</th>
                    <th>Verdict</th>
                    <th>应检出?</th>
                    <th>期望 Severity</th>
                    <th>期望 Contract</th>
                    <th>实际 Contracts</th>
                    <th>匹配 Severities</th>
                  </tr>
                </thead>
                <tbody>
                  {r.cases.map((c, i) => (
                    <tr key={c.case || String(i)}>
                      <td className="mono">{c.case}</td>
                      <td>
                        <span className={"pill " + (c.verdict === "PASS" ? "pill-ok" : c.verdict === "MISS" || c.verdict === "FALSE_POSITIVE" ? "pill-bad" : "pill-run")}>
                          {c.verdict}
                        </span>
                      </td>
                      <td>{c.should_detect ? "是" : "否"}</td>
                      <td className="mono">{c.expected_severity || "—"}</td>
                      <td className="mono">{c.expected_contract || "—"}</td>
                      <td className="mono">{c.contracts_found || "—"}</td>
                      <td className="mono">{c.matched_severities || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}
