import { useEffect, useState } from "react";
import { apiGet, downloadCapsule, FindingsData } from "../api";
import { Button, Degraded, Empty, ErrorBox, Panel, Spinner, fmtPct, kv, severityPill } from "../ui";

export default function FindingDetail(props: { jobId: string; findingId: string }) {
  const { jobId, findingId } = props;
  const [data, setData] = useState<FindingsData | null>(null);
  const [error, setError] = useState<Error | string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    apiGet<FindingsData>("/api/v1/jobs/" + encodeURIComponent(jobId) + "/findings")
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

  if (loading) return <Spinner />;
  if (!data) return <ErrorBox error={error || "加载失败"} />;

  const f = data.findings.find((x) => String(x.id) === findingId || String(x.id || "") === "");
  if (!f) {
    return (
      <div>
        <ErrorBox error={"finding " + findingId + " 不存在于任务 " + jobId} />
        <a href={"#/jobs/" + jobId}>← 返回任务</a>
      </div>
    );
  }

  const sev = severityPill(f.severity);
  const impact = f.impact_path ? JSON.stringify(f.impact_path, null, 2) : null;

  return (
    <div>
      <div className="page-head">
        <h1 className="mono">
          Finding {f.id} <span className={"pill " + sev.cls}>{sev.label}</span>
        </h1>
        <div className="page-sub">
          任务 {jobId} · 契约 {f.contract_id || "—"}
        </div>
      </div>
      <ErrorBox error={error} />
      {data.degraded ? <Degraded reasons={[data.degraded_reason || "degraded"]} /> : null}

      <div className="page-grid">
        <Panel title="元数据 Metadata">
          {kv("Severity", sev.label)}
          {kv("Contract", f.contract_id || "—")}
          {kv("Evidence Type", f.evidence_type || "—")}
          {kv("Confidence", fmtPct(f.confidence))}
          {kv("Location", f.location || "—")}
          {kv("Type", f.type || "—")}
          {kv("Capsule", f.capsule_path ? String(f.capsule_path) : "—")}
        </Panel>
        <Panel title="描述 Description">
          <p>{f.description || "无描述"}</p>
        </Panel>
      </div>

      <Panel title="影响路径 Impact Path">
        {impact ? <pre className="json">{impact}</pre> : <Empty text="该 finding 无 impact_path 记录 (诚实空态)" />}
      </Panel>

      <Panel title="证据 Evidence">
        <table className="data">
          <tbody>
            <tr><td className="kv-label">evidence_type</td><td className="mono">{f.evidence_type || "—"}</td></tr>
            <tr><td className="kv-label">location</td><td className="mono">{f.location || "—"}</td></tr>
            <tr><td className="kv-label">confidence</td><td className="mono">{fmtPct(f.confidence)}</td></tr>
          </tbody>
        </table>
      </Panel>

      <div style={{ display: "flex", gap: 10 }}>
        <a className="btn btn-ghost" href={"#/jobs/" + jobId}>← 返回任务</a>
        {f.capsule_path ? (
          <Button variant="secondary" onClick={() => downloadCapsule(jobId, String(f.capsule_path).split("/").pop())}>
            下载 Bug Capsule ↓
          </Button>
        ) : null}
      </div>
    </div>
  );
}
