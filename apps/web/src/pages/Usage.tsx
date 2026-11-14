import { useEffect, useState } from "react";
import "../styles/verification.css";
import { getLlmUsageSummary, type LlmUsageSummary, type LlmUsageTrendBucket } from "../api";
import { Degraded, Empty, ErrorBox, Panel, Spinner, StatCard, Table, fmtPct, type Column, type StatTone } from "../ui";
import { interp, useI18n } from "../i18n";

// 窗口选择：覆盖"刚才那几次"到"最近一个月"，与后端窗口上限（30 天）一致。
const WINDOWS = [
  { hours: 1, labelKey: "usage.window.1h" },
  { hours: 24, labelKey: "usage.window.24h" },
  { hours: 24 * 7, labelKey: "usage.window.7d" },
  { hours: 24 * 30, labelKey: "usage.window.30d" },
] as const;

const fmtTokens = (n: number | null | undefined): string => {
  if (typeof n !== "number" || !Number.isFinite(n)) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "k";
  return String(Math.round(n));
};

const fmtMs = (ms: number | null | undefined): string => {
  if (typeof ms !== "number" || !Number.isFinite(ms)) return "—";
  return ms < 1000 ? Math.round(ms) + " ms" : (ms / 1000).toFixed(1) + " s";
};

const hitTone = (rate: number | null | undefined): StatTone => {
  if (typeof rate !== "number") return "mute";
  if (rate >= 0.7) return "ok";
  if (rate >= 0.3) return "warn";
  return "bad";
};

const kindToneLabel = (rate: number | null | undefined): string => {
  if (typeof rate !== "number") return "—";
  return fmtPct(rate);
};

interface KindRow {
  kind: string;
  calls: number;
  prompt_tokens: number;
  cached_tokens: number;
  hit_rate: number | null;
}

const KIND_COLUMNS: Column<KindRow>[] = [
  {
    key: "kind",
    header: "类型 kind",
    sortable: true,
    render: (r) => <span className="mono">{r.kind}</span>,
  },
  {
    key: "calls",
    header: "调用",
    align: "right",
    sortable: true,
    render: (r) => <span className="mono">{r.calls}</span>,
  },
  {
    key: "prompt_tokens",
    header: "Prompt\u2009token",
    align: "right",
    sortable: true,
    render: (r) => <span className="mono">{fmtTokens(r.prompt_tokens)}</span>,
  },
  {
    key: "cached_tokens",
    header: "缓存命中\u2009token",
    align: "right",
    sortable: true,
    render: (r) => <span className="mono">{fmtTokens(r.cached_tokens)}</span>,
  },
  {
    key: "hit_rate",
    header: "命中率",
    align: "right",
    sortable: true,
    sortValue: (r) => (typeof r.hit_rate === "number" ? r.hit_rate : -1),
    render: (r) => <span className="mono">{kindToneLabel(r.hit_rate)}</span>,
  },
];

/** 每小时趋势：柱 = 调用次数（缩放到最大值），折线 = 命中率（0–100%）。纯 SVG。 */
function TrendChart({ trend }: { trend: LlmUsageTrendBucket[] }): JSX.Element {
  const { t } = useI18n();
  const W = 660;
  const H = 132;
  const PAD_L = 6;
  const PAD_R = 6;
  const TOP = 10;
  const BAR_BOTTOM = 96;
  const maxCalls = Math.max(1, ...trend.map((b) => b.calls));
  const n = trend.length;
  const slot = (W - PAD_L - PAD_R) / n;
  const barW = Math.max(3, slot * 0.62);

  const points = trend.map((bucket, i) => {
    const x = PAD_L + i * slot + slot / 2;
    const rate = typeof bucket.hit_rate === "number" ? bucket.hit_rate : null;
    const y = rate === null ? null : TOP + (1 - Math.min(1, Math.max(0, rate))) * (BAR_BOTTOM - TOP);
    return { x, y, rate, bucket };
  });
  const linePath = points
    .filter((p) => p.y !== null)
    .map((p, idx) => `${idx === 0 ? "M" : "L"}${p.x.toFixed(1)},${(p.y as number).toFixed(1)}`)
    .join(" ");

  const fmtHour = (iso: string): string => iso.slice(11, 16);
  const first = trend[0];
  const last = trend[trend.length - 1];

  return (
    <div className="usage-trend">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="每小时调用次数与缓存命中率">
        <line x1={PAD_L} y1={BAR_BOTTOM} x2={W - PAD_R} y2={BAR_BOTTOM} className="usage-trend-axis" />
        {points.map((p, i) => {
          const barH = (p.bucket.calls / maxCalls) * (BAR_BOTTOM - TOP);
          return (
            <rect
              key={i}
              x={p.x - barW / 2}
              y={BAR_BOTTOM - barH}
              width={barW}
              height={Math.max(1.5, barH)}
              rx={2}
              className="usage-trend-bar"
            >
              <title>{fmtHour(p.bucket.bucket_start)} · {p.bucket.calls} 次 · {fmtPct(p.bucket.hit_rate)} 命中</title>
            </rect>
          );
        })}
        {linePath ? <path d={linePath} className="usage-trend-line" fill="none" /> : null}
        {points.map((p, i) => p.y === null ? null : (
          <circle key={"dot" + i} cx={p.x} cy={p.y} r={2.4} className="usage-trend-dot" />
        ))}
      </svg>
      <div className="usage-trend-legend">
        <span className="usage-legend-item"><span className="usage-legend-bar" aria-hidden="true" /> {t("usage.callsOnly")}{first && last ? `（${fmtHour(first.bucket_start)} → ${fmtHour(last.bucket_start)} UTC）` : ""}</span>
        <span className="usage-legend-item"><span className="usage-legend-line" aria-hidden="true" /> {t("usage.hitRateLegend")}</span>
      </div>
    </div>
  );
}

export default function Usage() {
  const { t, locale } = useI18n();
  const [windowHours, setWindowHours] = useState<number>(24);
  const [data, setData] = useState<LlmUsageSummary | null>(null);
  const [error, setError] = useState<Error | string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    const tick = () => {
      getLlmUsageSummary(windowHours)
        .then((d) => { if (alive) setData(d); })
        .catch((e) => { if (alive) setError(e as Error); })
        .finally(() => { if (alive) setLoading(false); });
    };
    tick();
    const t = window.setInterval(tick, 30000);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, [windowHours]);

  const calls = data?.calls ?? 0;
  const emptyLedger = data !== null && calls === 0 && data.trend.length === 0;

  return (
    <div className="usage-page">
      <div className="page-head">
        <h1>{t("usage.title")} <span className="usage-en">{t("usage.subtitle")}</span></h1>
        <div className="page-sub" title="LLM USAGE LEDGER">
          {t("usage.lead")}
        </div>
      </div>

      <div className="usage-window-bar" role="group" aria-label={t("usage.window")}>
        <span className="usage-window-label">{t("usage.window")}</span>
        {WINDOWS.map((w) => (
          <button
            key={w.hours}
            type="button"
            className={"usage-chip" + (windowHours === w.hours ? " usage-chip-active" : "")}
            aria-pressed={windowHours === w.hours}
            onClick={() => setWindowHours(w.hours)}
          >
            {t(w.labelKey)}
          </button>
        ))}
        <span className="usage-generated" title={data?.generated_at}>
          {t("usage.generatedAt")} {data?.generated_at ? new Date(data.generated_at).toLocaleString() : "—"}
        </span>
      </div>

      <ErrorBox error={error} />

      {loading && !data ? (
        <Spinner />
      ) : emptyLedger ? (
        <Panel title={t("usage.emptyTitle")}>
          <Empty text={t("usage.emptyText")} />
        </Panel>
      ) : data ? (
        <>
          <div className="stat-grid" style={{ marginBottom: 12 }}>
            <StatCard label={t("usage.hitRate")} value={fmtPct(data.hit_rate)} tone={hitTone(data.hit_rate)} />
            <StatCard label={t("usage.savedTokens")} value={fmtTokens(data.cached_tokens)} tone={data.cached_tokens > 0 ? "ok" : "mute"} />
            <StatCard label={t("usage.totalTokens")} value={fmtTokens(data.total_tokens)} tone="mute" />
            <StatCard label={t("usage.calls")} value={String(data.calls)} tone="mute" />
            <StatCard label={t("usage.p50")} value={fmtMs(data.latency_p50_ms)} tone="mute" />
            <StatCard label={t("usage.p95")} value={fmtMs(data.latency_p95_ms)} tone={typeof data.latency_p95_ms === "number" && data.latency_p95_ms > 8000 ? "warn" : "mute"} />
          </div>

          <p className="muted usage-basis-note">
            {interp(t("usage.basis"), { basis: `${data.hit_basis_calls} / ${data.calls}` })}
            {locale === "zh" ? " 错误率 " : " Error rate "}{fmtPct(data.error_rate)} · {locale === "zh" ? " 流式占比 " : " Streaming share "}{fmtPct(data.streamed_ratio)}
          </p>

          <Panel title={t("usage.streamShare")}>
            <div className="usage-meter" aria-label={t("usage.streamAria")}>
              <div className="usage-meter-fill" style={{ width: `${((data.streamed_ratio ?? 0) * 100).toFixed(1)}%` }} />
            </div>
            <div className="muted usage-meter-note">
              {fmtPct(data.streamed_ratio)} {locale === "zh" ? "的调用以 stream=true 请求——流式是网关回报缓存用量（cached_tokens）的前提。" : "of the calls were requested with stream=true — streaming is the precondition for the gateway to report cached_tokens."}
            </div>
          </Panel>

          <Panel title={t("usage.byKind")}>
            <Table<KindRow>
              columns={KIND_COLUMNS}
              rows={data.by_kind}
              rowKey={(r) => r.kind}
              emptyTitle="暂无类型记录"
              emptyDescription={t("usage.trendEmpty")}
            />
          </Panel>

          <Panel title={t("usage.trend")}>
            {data.trend.length > 0 ? <TrendChart trend={data.trend} /> : <Empty text={t("usage.trendEmpty")} />}
          </Panel>
        </>
      ) : null}

      {error && !loading ? (
        <Degraded reasons={[t("usage.degraded")]} />
      ) : null}
    </div>
  );
}
