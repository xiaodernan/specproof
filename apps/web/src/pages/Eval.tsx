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
import { useI18n } from "../i18n";
import { EVAL_BY_LOCALE } from "./eval.copy";

type EvalCase = NonNullable<NonNullable<EvalData["report"]["cases"]>[number]>;

type EvalCopy = (typeof EVAL_BY_LOCALE)["zh"];

function makeColumns(c: EvalCopy): Column<EvalCase>[] {
  return [
    { key: "case", header: c.colCase, sortable: true, render: (k) => <span className="mono">{k.case}</span> },
    {
      key: "verdict",
      header: c.colVerdict,
      sortable: true,
      // Keep the canonical English token (audit) and add the Chinese gloss;
      // raw stays in title. Unknown verdicts pass through verbatim (no gloss).
      render: (k) => {
        const cn = k.verdict ? evalVerdictLabel(k.verdict) : "";
        const glossed = !!cn && cn !== k.verdict;
        return (
          <span className={pillClass(k.verdict)} title={k.verdict || ""}>
            {k.verdict || c.emptyPlaceholder}
            {glossed ? " · " + cn : ""}
          </span>
        );
      },
    },
    {
      key: "should_detect",
      header: c.colShouldDetect,
      align: "center",
      sortable: true,
      sortValue: (k) => (k.should_detect ? 1 : 0),
      render: (k) => <>{k.should_detect ? c.yesGlyph : c.noGlyph}</>,
    },
    {
      key: "expected_severity",
      header: c.colExpectedSeverity,
      sortable: true,
      render: (k) =>
        k.expected_severity ? (
          <span className={`pill ${severityPill(k.expected_severity).cls}`} title={severityHint(k.expected_severity) || k.expected_severity}>
            {severityPill(k.expected_severity).label}
          </span>
        ) : (
          <span className="mono">{c.emptyPlaceholder}</span>
        ),
    },
    { key: "expected_contract", header: c.colExpectedContract, sortable: true, render: (k) => <span className="mono">{k.expected_contract || c.emptyPlaceholder}</span> },
    { key: "contracts_found", header: c.colContractsFound, render: (k) => <span className="mono">{k.contracts_found || c.emptyPlaceholder}</span> },
    { key: "matched_severities", header: c.colMatchedSeverities, render: (k) => <span className="mono">{k.matched_severities || c.emptyPlaceholder}</span> },
  ];
}

function pillClass(verdict?: string): string {
  return verdict === "PASS"
    ? "pill pill-ok"
    : verdict === "MISS" || verdict === "FALSE_POSITIVE"
    ? "pill pill-bad"
    : "pill pill-run";
}

export default function Eval() {
  const { locale } = useI18n();
  const c = EVAL_BY_LOCALE[locale];
  const columns = makeColumns(c);
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
        <h1>{c.title}</h1>
        <div className="page-sub">{c.sub}</div>
      </div>

      {failed ? (
        // A failed request is NOT "no report": say so honestly and offer a retry.
        <>
          <ErrorBox error={error} />
          <div style={{ marginTop: 12 }}>
            <Button variant="ghost" onClick={() => setReload((n) => n + 1)}>
              {c.retry}
            </Button>
          </div>
        </>
      ) : !data ? (
        <Empty text={c.notFoundText} />
      ) : (
        <>
          <div className="kv">
            <span className="kv-label">{c.sourceLabel}</span>
            <span className="kv-value mono">{data.source}</span>
          </div>
          <div className="kv" style={{ marginBottom: 16 }}>
            <span className="kv-label">{c.modifiedLabel}</span>
            <span className="kv-value">{fmtTime(data.modified_at)}</span>
          </div>

          <div className="stat-grid" style={{ marginBottom: 16 }}>
            <StatCard label={c.statPrecision} value={r && r.precision != null ? r.precision.toFixed(1) + "%" : c.emptyPlaceholder} tone="info" />
            <StatCard label={c.statRecall} value={r && r.recall != null ? r.recall.toFixed(1) + "%" : c.emptyPlaceholder} tone="ok" />
            <StatCard label={c.statF1} value={r && r.f1 != null ? r.f1.toFixed(1) + "%" : c.emptyPlaceholder} tone="warn" />
            <StatCard label={c.statTotal} value={r ? (r.total_cases ?? c.emptyPlaceholder) : c.emptyPlaceholder} />
            <StatCard label={c.statShouldDetect} value={r ? (r.should_detect ?? c.emptyPlaceholder) : c.emptyPlaceholder} />
            <StatCard label={c.statFalsePositives} value={r ? (r.false_positives ?? c.emptyPlaceholder) : c.emptyPlaceholder} tone={r && r.false_positives ? "bad" : "ok"} />
          </div>

          <Panel title={c.casesPanelTitle(r && r.cases ? r.cases.length : 0)}>
            <Table<EvalCase>
              columns={columns}
              rows={r?.cases ?? []}
              rowKey={(k, i) => k.case || String(i)}
              emptyTitle={c.emptyCasesTitle}
            />
          </Panel>
        </>
      )}
    </div>
  );
}
