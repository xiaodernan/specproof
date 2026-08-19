import { useEffect, useState } from "react";
import { apiGet, Job, MatrixData } from "../api";
import { Degraded, Empty, ErrorBox, Panel, Spinner, resultPill, shortId } from "../ui";

export default function Matrix() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobId, setJobId] = useState("");
  const [data, setData] = useState<MatrixData | null>(null);
  const [error, setError] = useState<Error | string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    apiGet<{ jobs: Job[] }>("/jobs?limit=200")
      .then((d) => setJobs(d.jobs || []))
      .catch((e) => setError(e as Error));
  }, []);

  useEffect(() => {
    if (!jobId) {
      setData(null);
      return;
    }
    let alive = true;
    setLoading(true);
    setError(null);
    apiGet<MatrixData>("/api/v1/jobs/" + encodeURIComponent(jobId) + "/matrix")
      .then((d) => {
        if (alive) setData(d);
      })
      .catch((e) => {
        if (alive) setError(e as Error);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [jobId]);

  return (
    <div>
      <div className="page-head">
        <h1>需求矩阵 Requirement-to-Evidence Matrix</h1>
        <div className="page-sub">CONTRACT × RESULT × EVIDENCE — 每行一条需求合约与证据引用</div>
      </div>
      <ErrorBox error={error} />

      <Panel
        title="选择任务"
        right={
          <select value={jobId} onChange={(e) => setJobId(e.target.value)}>
            <option value="">— 选择 job —</option>
            {jobs.map((j) => (
              <option key={j.id} value={j.id}>
                {shortId(j.id)} · {(j.base_ref || "") + "→" + (j.head_ref || "")} · {j.status}
              </option>
            ))}
          </select>
        }
      />

      {!jobId ? (
        <Empty text="选择一个任务以查看需求-证据矩阵" />
      ) : loading ? (
        <Spinner />
      ) : data ? (
        <>
          {data.degraded ? <Degraded reasons={[data.degraded_reason || "degraded"]} /> : null}
          <div className="stat-grid" style={{ marginBottom: 16 }}>
            <div className="stat"><div className="stat-value">{data.counts.total}</div><div className="stat-label">合约总数</div></div>
            <div className="stat"><div className="stat-value" style={{ color: "var(--success)" }}>{data.counts.passed}</div><div className="stat-label">PASS</div></div>
            <div className="stat"><div className="stat-value" style={{ color: "var(--danger)" }}>{data.counts.failed}</div><div className="stat-label">FAIL</div></div>
            <div className="stat"><div className="stat-value" style={{ color: "var(--warning)" }}>{data.counts.unverified}</div><div className="stat-label">UNVERIFIED</div></div>
          </div>
          <Panel title={"矩阵行 (" + data.rows.length + ")"}>
            {data.rows.length === 0 ? (
              <Empty text="contracts 表无该任务行 (摘要计数仍显示在上方 — 诚实空态)" />
            ) : (
              <table className="data">
                <thead>
                  <tr>
                    <th>Contract ID</th>
                    <th>Requirement</th>
                    <th>Checker</th>
                    <th>Expected Behavior</th>
                    <th>Result</th>
                    <th>Evidence Ref</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((r, i) => {
                    const res = resultPill(r.result);
                    return (
                    <tr key={r.contract_id_str + String(i)}>
                      <td className="mono">{r.contract_id_str}</td>
                      <td>{r.requirement_text}</td>
                      <td className="mono">{r.checker_type}</td>
                      <td className="muted">{r.expected_behavior}</td>
                      <td>
                        <span className={"pill " + res.cls}>{res.label}</span>
                      </td>
                      <td className="mono muted">
                        {r.evidence_ref ? r.evidence_ref : "未知"}
                      </td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </Panel>
        </>
      ) : null}
    </div>
  );
}
