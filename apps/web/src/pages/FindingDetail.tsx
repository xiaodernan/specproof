import { useEffect, useState } from "react";
import { apiGet, downloadCapsule, FindingsData } from "../api";
import { Button, Degraded, Empty, ErrorBox, Panel, Spinner, Term, fmtPct, kv, severityPill, severityHint, evidenceLabel } from "../ui";

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
  const sevHint = severityHint(f.severity);
  const impact = f.impact_path ? JSON.stringify(f.impact_path, null, 2) : null;

  return (
    <div>
      <div className="page-head">
        <h1 className="mono">
          风险详情 {f.id} <span className={"pill " + sev.cls}>{sev.label}</span>
        </h1>
        {sevHint ? <p className="severity-hint">{sevHint}</p> : null}
        <div className="page-sub">
          任务 {jobId} · 验收条件 {f.contract_id || "—"}
        </div>
      </div>
      <ErrorBox error={error} />
      {data.degraded ? <Degraded reasons={[data.degraded_reason || "degraded"]} /> : null}

      <div className="page-grid">
        <Panel title="基本信息">
          {kv("严重程度", sev.label + (sevHint ? " · " + sevHint.split("——")[0] : ""))}
          {kv("对应验收条件", f.contract_id || "—")}
          {kv("证据方式", evidenceLabel(f.evidence_type))}
          {kv("置信度", fmtPct(f.confidence))}
          {kv("代码位置", f.location || "—")}
          {kv("问题类型", f.type || "—")}
          {kv(<Term id="capsule">复现包</Term>, f.capsule_path ? String(f.capsule_path) : "—")}
        </Panel>
        <Panel title="问题描述">
          <p>{f.description || "无描述"}</p>
        </Panel>
      </div>

      <Panel title="影响路径">
        {impact ? <pre className="json">{impact}</pre> : <Empty text="该风险暂无影响路径记录（诚实空态：未编造调用链）。" />}
      </Panel>

      <Panel title={<Term id="evidence">证据来源</Term>}>
        <table className="data">
          <tbody>
            <tr><td className="kv-label">证据方式</td><td className="mono">{evidenceLabel(f.evidence_type)}</td></tr>
            <tr><td className="kv-label">代码位置</td><td className="mono">{f.location || "—"}</td></tr>
            <tr><td className="kv-label">置信度</td><td className="mono">{fmtPct(f.confidence)}</td></tr>
          </tbody>
        </table>
      </Panel>

      <div style={{ display: "flex", gap: 10 }}>
        <a className="btn btn-ghost" href={"#/jobs/" + jobId}>← 返回任务</a>
        {f.capsule_path ? (
          <Button variant="secondary" onClick={() => downloadCapsule(jobId, String(f.capsule_path).split("/").pop())}>
            下载复现包 ↓
          </Button>
        ) : null}
      </div>
    </div>
  );
}
