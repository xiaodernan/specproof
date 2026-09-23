import { useEffect, useState } from "react";
import { apiGet, EvalData, ApiError } from "../api";
import {
  Button,
  Empty,
  ErrorBox,
  Panel,
  Spinner,
  StatCard,
  Table,
  evalVerdictLabel,
  fmtTime,
  severityHint,
  severityPill,
  type Column,
} from "../ui";

type EvalCase = NonNullable<NonNullable<EvalData["report"]["cases"]>[number]>;

function pillClass(verdict?: string): string {
  return verdict === "PASS"
    ? "pill pill-ok"
    : verdict === "MISS" || verdict === "FALSE_POSITIVE"
    ? "pill pill-bad"
    : "pill pill-run";
}

const CASE_COLUMNS: Column<EvalCase>[] = [
  { key: "case", header: "案例 Case", sortable: true, render: (c) => <span className="mono">{c.case}</span> },
  {
    key: "verdict",
    header: "判定 Verdict",
    sortable: true,
    // Keep the canonical English token (audit) and add the Chinese gloss;
    // raw stays in title. Unknown verdicts pass through verbatim (no gloss).
    render: (c) => {
      const cn = c.verdict ? evalVerdictLabel(c.verdict) : "";
      const glossed = !!cn && cn !== c.verdict;
      return (
        <span className={pillClass(c.verdict)} title={c.verdict || ""}>
          {c.verdict || "—"}
          {glossed ? " · " + cn : ""}
        </span>
      );
    },
  },
  {
    key: "should_detect",
    header: "应检出?",
    align: "center",
    sortable: true,
    sortValue: (c) => (c.should_detect ? 1 : 0),
    render: (c) => <>{c.should_detect ? "是" : "否"}</>,
  },
  {
    key: "expected_severity",
    header: "期望严重度",
    sortable: true,
    render: (c) =>
      c.expected_severity ? (
        <span className={`pill ${severityPill(c.expected_severity).cls}`} title={severityHint(c.expected_severity) || c.expected_severity}>
          {severityPill(c.expected_severity).label}
        </span>
      ) : (
        <span className="mono">—</span>
      ),
  },
  { key: "expected_contract", header: "期望契约 Contract", sortable: true, render: (c) => <span className="mono">{c.expected_contract || "—"}</span> },
  { key: "contracts_found", header: "实际检出契约", render: (c) => <span className="mono">{c.contracts_found || "—"}</span> },
  { key: "matched_severities", header: "匹配严重度 Severities", render: (c) => <span className="mono">{c.matched_severities || "—"}</span> },
];

export default function Eval() {
  const [data, setData] = useState<EvalData | null>(null);
  const [error, setError] = useState<Error | string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    apiGet<EvalData>("/api/v1/eval/latest")
      .then((d) => { if (alive) setData(d); })
      .catch((e) => { if (alive) setError(e as Error); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [reload]);

  if (loading) return <Spinner />;

  const r = data ? data.report : null;
  // A 404 is an honest "no report has been generated yet", not a failure.
  // Anything else (network, 5xx) is a real read error and must not be
  // mislabelled to the user as "the report doesn't exist".
  const notFound = error instanceof ApiError && error.status === 404;
  const failed = !!error && !notFound;

  return (
    <div>
      <div className="page-head">
        <h1>评测 Evaluation</h1>
        <div className="page-sub">精确率 / 召回率 / F1 — 数据来自评测管线的报告文件</div>
      </div>

      {failed ? (
        // A failed request is NOT "no report": say so honestly and offer a retry.
        <>
          <ErrorBox error={error} />
          <div style={{ marginTop: 12 }}>
            <Button variant="ghost" onClick={() => setReload((n) => n + 1)}>
              重新加载
            </Button>
          </div>
        </>
      ) : !data ? (
        <Empty text="尚无评测报告——评测管线还未运行过，或没有生成报告文件。这不是读取失败。" />
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
            <Table<EvalCase>
              columns={CASE_COLUMNS}
              rows={r?.cases ?? []}
              rowKey={(c, i) => c.case || String(i)}
              emptyTitle="无案例明细"
            />
          </Panel>
        </>
      )}
    </div>
  );
}
