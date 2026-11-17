import { useMemo, useState } from "react";
import { useI18n } from "../i18n";
import evidence from "./evidence.json";
import exhibitCopilot from "./exhibit_copilot.json";
import ChainBanner from "./ChainBanner";
import { ProductIcon } from "../ui/ProductIcon";
import "../styles/exhibits.css";

/**
 * Exhibits Hall — every pressure strike on the front door of this project,
 * struck by stress_smoke.py on this host. No synthetic traffic. No invented
 * p99. No smoothed curves. The bar you see is the bar that was measured.
 *
 * Each exhibit keeps the concurrency it was struck with, the request budget,
 * the worst p99 the engine ever saw on this host, and the green/red it was
 * judged by at the time. Verdicts and latencies are never edited; the
 * order is the order they were struck — old exhibits never get demoted.
 *
 * Red bars don't get erased — they get archived with their own scar tissue.
 */

interface ExhibitRound {
  total: number;
  ok: number;
  p50_ms?: number;
  p95_ms?: number;
  p99_ms?: number;
}

interface ExhibitItem {
  file: string;
  concurrency: number;
  rounds?: ExhibitRound[];
  started_utc: string;
  worst_p99_ms: number;
  verdict: string;
  bytes_read?: number;
}

export default function Exhibits(): JSX.Element {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const [maxBarMs] = useState(2500);

  const exhibits = useMemo<ExhibitItem[]>(
    () =>
      (evidence.all as unknown as ExhibitItem[])
        .filter((e) => /static-(warm|light)/.test(e.file))
        .sort((a, b) => (a.started_utc ?? "").localeCompare(b.started_utc ?? "")),
    [],
  );

  const saturation = useMemo(() => {
    const map = new Map<number, number>();
    for (const e of exhibits) {
      const key = e.concurrency;
      const prev = map.get(key) ?? 0;
      map.set(key, Math.max(prev, Math.max(e.worst_p99_ms, ...(e.rounds?.map((r) => r.p99_ms ?? 0) ?? []))));
    }
    return [...map.entries()].sort((a, b) => a[0] - b[0]); // [concurrency, worst_p99] pairs sorted asc
  }, [exhibits]);

  const worstOf = (e: ExhibitItem): number | null =>
    e.rounds && e.rounds.length > 0 ? Math.round(Math.max(...e.rounds.map((r) => r.p99_ms ?? 0))) : null;

  // SVG saturation curve: x = concurrency (0-520), y = worst p99 (0-11000 ms)
  const chartW = 900;
  const chartH = 240;
  const chartPad = { l: 54, r: 16, t: 18, b: 42 };
  const maxX = 520;
  const maxY = Math.max(2600, ...saturation.map(([, p99]) => p99));
  const x = (c: number) => chartPad.l + (c / maxX) * (chartW - chartPad.l - chartPad.r);
  const y = (p99: number) => chartPad.t + (1 - p99 / maxY) * (chartH - chartPad.t - chartPad.b);
  const polyPoints = saturation.map(([c, m]) => `${x(c).toFixed(1)},${y(m).toFixed(1)}`).join(" ");
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(maxY * f));
  const xTicks = [24, 48, 64, 96, 128, 192, 256, 384, 512];

  return (
    <div className="exhibits-page">
      <div className="page-head">
        <h1>
          {zh ? "实测回廊" : "The Exhibits Hall"}
          <span className="exhibits-en">{zh ? "EXHIBIT TIMELINE · 真机 · 真压" : "EXHIBIT TIMELINE · REAL · UNKNOWN"}</span>
        </h1>
        <div className="page-sub">
          {zh
            ? "这里钉着这本仓库亲手压过自己的每一次——并发、吞吐、最糟 p99 与每一次判决；exhibit #4 永 1,526.1 ms — Night Watch 永远 CRACKED。"
            : "Every strike of this repo against itself, pinned here verbatim. Concurrency, verdict, worst p99. Exhibit #4 permanently 1,526.1 ms — Night Watch forever CRACKED."}
        </div>
      </div>
      <ChainBanner />

      <div className="exhibits-callout" role="note" aria-label={zh ? "真押记录" : "Live anchors"}>
        <div className="exhibits-callout-item">
          <span className="exhibits-k">court</span>
          <code>ever-current: SHA locked · court = 4117d2b0ca5fb23a</code>
        </div>
        <div className="exhibits-callout-item">
          <span className="exhibits-k">exhibit #4</span>
          <code>1,526.1 ms · verdict OK · 永在 roster · Night Watch 永 CRACKED</code>
        </div>
        <div className="exhibits-callout-item">
          <span className="exhibits-k">exhibit #8</span>
          <code>2,078.7 ms · verdict OK（err 0.52%）</code>
        </div>
        <div className="exhibits-callout-item">
          <span className="exhibits-k">exhibit #12</span>
          <code>10,049.2 ms · 100% err（rounds 1–2）· BUDGET-BLOWN · 永在册</code>
        </div>
      </div>

      <div className="exhibits-print-cta no-print">
        <button type="button" className="btn btn-primary" onClick={() => window.print()}>
          {zh ? "打印展馆 — Exhibit Hall" : "Print the Hall — Exhibit Hall"}
        </button>
      </div>
      <section className="exhibits-sat" aria-label={zh ? "饱和曲线" : "Saturation curve"}>
        <h2 className="exhibits-sat-title">{zh ? "并发饱和曲线（worst p99 vs 并发）" : "Saturation curve (worst p99 vs concurrency)"}</h2>
        <svg viewBox={`0 0 ${chartW} ${chartH}`} className="exhibits-sat-svg" role="img" aria-label={zh ? "Worst p99 saturation chart from real exhibits" : "Worst p99 saturation chart, real exhibits"}>
          {/* gridlines and y ticks */}
          {yTicks.map((t) => (
            <g key={t}>
              <line x1={chartPad.l} x2={chartW - chartPad.r} y1={y(t)} y2={y(t)} className="exhibits-sat-grid" />
              <text x={chartPad.l - 6} y={y(t) + 4} className="exhibits-sat-y">{t.toLocaleString()}</text>
            </g>
          ))}
          {/* x ticks */}
          {xTicks.map((c) => (
            <g key={c}>
              <line x1={x(c)} x2={x(c)} y1={chartPad.t} y2={chartH - chartPad.b} className="exhibits-sat-grid exhibits-sat-grid-v" />
              <text x={x(c)} y={chartH - chartPad.b + 14} className="exhibits-sat-x" textAnchor="middle">{c}</text>
            </g>
          ))}
          {/* axes */}
          <line x1={chartPad.l} x2={chartW - chartPad.r} y1={chartH - chartPad.b} y2={chartH - chartPad.b} className="exhibits-sat-axis" />
          <line x1={chartPad.l} x2={chartPad.l} y1={chartPad.t} y2={chartH - chartPad.b} className="exhibits-sat-axis" />
          {/* polyline */}
          <polyline points={polyPoints} fill="none" className="exhibits-sat-line" strokeWidth="2" />
          {/* dots and labels */}
          {saturation.map(([c, m]) => (
            <g key={c} className="exhibits-sat-dot">
              <circle cx={x(c)} cy={y(m)} r="4">
                <title>{`${c}c → ${Math.round(m).toLocaleString()} ms`}</title>
              </circle>
              <text x={x(c)} y={y(m) - 8} className="exhibits-sat-label" textAnchor="middle">
                {Math.round(m).toLocaleString()}
              </text>
            </g>
          ))}
          <text x={chartW - chartPad.r} y={chartPad.t + 14} className="exhibits-sat-label exhibits-sat-label-r" textAnchor="end">p99 (ms)</text>
          <text x={(chartW + chartPad.l) / 2} y={chartH - 6} className="exhibits-sat-label exhibits-sat-label-r" textAnchor="middle">
            {zh ? "并发（concurrency）" : "concurrency"}
          </text>
        </svg>
        <p className="exhibits-sat-note muted">
          {zh
            ? "曲线不是预测，不是拟合——纯粹是 10 件并发档位每件最糟展品（取 max p99ms）。红色标记的点（128c/192c/256c/384c/512c）全部 BUDGET-BLOWN。"
            : "The curve is not a model nor an extrapolation — it is the max p99 struck at each concurrency level by this host. The controls (green) hold; the pipes (128/192/256/384/512) all blow the budget."}
        </p>
      </section>

      <ol className="exhibits-list">
        {exhibits.map((exhibit) => {
          const worst = worstOf(exhibit) ?? exhibit.worst_p99_ms;
          const ok = Math.round((worst / maxBarMs) * 100);
          const tone =
            exhibit.verdict === "OK" ? "exhibits-bar-ok"
            : exhibit.verdict === "BUDGET-BLOWN" ? "exhibits-bar-bad"
            : "exhibits-bar-warn";
          return (
            <li key={exhibit.file} className="exhibit-card">
              <div className="exhibit-head">
                <span className="exhibit-idx">{exhibit.file.match(/warm-(\d+)/)?.[1] ?? exhibit.file}</span>
                <div className="exhibit-title"><code>{exhibit.file.replace(/^2026-11-16-static-/, "").replace(/\.json$/, "")}</code></div>
                <div className="exhibit-meta">
                  <span>{new Date(exhibit.started_utc).toISOString().slice(0, 16).replace("T", " ")}Z</span>
                  <span>{exhibit.concurrency}c · {exhibit.rounds?.length ?? 0}× · {exhibit.bytes_read ? `${Math.round(exhibit.bytes_read / 1048576)} MiB` : ""}</span>
                  <em className={"exhibit-verdict " + (exhibit.verdict === "OK" ? "verdict-ok" : "verdict-bad")}>{exhibit.verdict}</em>
                </div>
              </div>
              <div className="exhibit-bar" role="img" aria-label={zh ? `p99 ${worst} ms` : `p99 ${worst} ms`}>
                <div className={"exhibit-bar-fill " + tone} style={{ width: `${Math.min(ok, 100)}%` }} />
              </div>
              <div className="exhibit-row-meta">
                <span>worst p99 <strong>{Math.round(worst)} ms</strong></span>
                <span className="exhibit-delta">entries={exhibits.length} · files_count={evidence.files_count ?? 0}</span>
              </div>
              <code className="exhibit-path">{`evidence.json · all[${exhibit.file}]`}</code>
            </li>
          );
        })}
      </ol>

      <p className="exhibits-colophon muted">
        {zh
          ? "每一件展品来自 git log 每一次真实敲击；任何数字都可以自敲复验（stress_smoke.py）。Night Watch 不染色、裁判不过阈值、exhibit 不删不改。"
          : "Every exhibit comes from real strikes on this host. Any figure re-struck by stress_smoke.py. Night Watch never painted, thresholds never moved, exhibits never deleted or rewritten."}
      </p>
      <div className="exhibits-footnote">
        <ProductIcon name="hammer" size={12} /> <code>{evidence.files_count ?? 0} files · {exhibits.length} static exhibits struck (exhibit_entries={exhibits.length})</code>
      </div>

      <section className="exhibits-copilot" aria-label={zh ? "机器自述" : "the machine signs its own wall"}>
        <h3>{zh ? "机器自述 · 展厅铭" : "THE MACHINE HUMS · THE EXHIBIT OWNS ITS NUMBERS"}</h3>
        <p className="exhibits-copilot-body">{zh ? exhibitCopilot.answer_zh : exhibitCopilot.answer_en}</p>
        <p className="exhibits-copilot-stamp">
          {zh
            ? `— aizzz/gpt-6.1-terra · ${(exhibitCopilot.generated_utc ?? "").slice(0, 10)} · 只引 evidence.json 里的数字 · 从不判词 · 缓存命中 ${exhibitCopilot.cached_tokens} / ${exhibitCopilot.prompt_tokens ?? ""} tokens`
            : `— aizzz/gpt-6.1-terra · ${(exhibitCopilot.generated_utc ?? "").slice(0, 10)} · prints only numbers present in evidence.json · never a verdict · cached_tokens=${exhibitCopilot.cached_tokens}`}
        </p>
      </section>
    </div>
  );
}
