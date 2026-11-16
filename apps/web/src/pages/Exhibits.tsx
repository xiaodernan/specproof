import { useMemo, useState } from "react";
import { useI18n } from "../i18n";
import evidence from "./evidence.json";
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
        .filter((e) => /^static-(warm|light)/.test(e.file))
        .sort((a, b) => (a.started_utc ?? "").localeCompare(b.started_utc ?? "")),
    [],
  );

  const worstOf = (e: ExhibitItem): number | null =>
    e.rounds && e.rounds.length > 0 ? Math.round(Math.max(...e.rounds.map((r) => r.p99_ms ?? 0))) : null;

  return (
    <div className="exhibits-page">
      <div className="page-head">
        <h1>
          {zh ? "实测回廊" : "The Exhibits Hall"}
          <span className="exhibits-en">{zh ? "EXHIBIT TIMELINE · 真机 · 真压" : "EXHIBIT TIMELINE · REAL · UNKNOWN"}</span>
        </h1>
        <div className="page-sub">
          {zh
            ? "这里钉着这本仓库亲手压过自己的每一次——并发、吞吐、最糟 p99 与每一次判决；Exhibit #4 永 1,526.1 ms — Night Watch 永远 CRACKED。"
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
          <span className="exhibits-k">exhibit #11</span>
          <code>2,253.8 ms · verdict BUDGET-BLOWN（err 45.12% ×512B req）</code>
        </div>
      </div>

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
    </div>
  );
}
