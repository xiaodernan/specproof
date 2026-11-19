import { useMemo } from "react";
import { useI18n } from "../i18n";
import chronicle from "./chronicle.json";
import { ProductIcon } from "../ui/ProductIcon";
import "../styles/recent-knocks.css";

interface KnockEntry {
  n: number;
  t: string;
  s: string;
}

const entries = chronicle as unknown as KnockEntry[];

/**
 * Recent Knocks — the human reader's front row.
 *
 * Chronicle is the whole book, rendered one-entry-per-row, newest last; this
 * page is the orthographic opposite — the last ten strikes, newest first,
 * sized for a reader who has thirty seconds and no context yet.
 *
 * It takes NO model calls and invents NOTHING. It renders exactly what the
 * repo's own ledger wrote and the build's own chronicle.json carries. If the
 * ledger is silent, the page says so honestly (never extrapolated zeroes).
 */
export default function RecentKnocks(): JSX.Element {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const L = (a: string, b: string) => (zh ? a : b);

  const latest = useMemo(
    () => [...entries].sort((a, b) => b.n - a.n).slice(0, 10),
    [],
  );

  const total = entries.length;

  return (
    <div className="recent-knocks-page">
      <header className="page-head">
        <ProductIcon name="scroll" size={28} />
        <h1>
          {L("最近敲门", "Recent Knocks")}{" "}
          <span className="recent-knocks-en">{L("铁证宇宙 · HEAD OF THE BOOK", "SPECROOF · HEAD OF THE BOOK")}</span>
        </h1>
        <div className="page-sub">
          {L(
            "账本最末十卷，一推就看全——不调模型，不编数字，只把账本翻开。你要看的是『刚发生了什么』，不是预演未来。",
            "The ten freshest volumes of the ledger, opened flat — no model, no invented numbers, just the book. This tells you what happened, not what will.",
          )}
        </div>
      </header>

      <ol className="recent-knocks-rail">
        {latest.map((entry, index) => (
          <li key={`${entry.n}-${index}`} className="recent-knock-card">
            <div className="recent-knock-meta">
              <span aria-hidden="true" className="recent-knock-index">
                {String(latest.length - index).padStart(2, "0")}
              </span>
              <code className="recent-knock-n">#{entry.n}</code>
            </div>
            <h2 className="recent-knock-title">{entry.t}</h2>
            {entry.s ? <p className="recent-knock-summary">{entry.s}</p> : null}
          </li>
        ))}
      </ol>

      <p className="recent-knocks-foot">
        {L(
          `共 ${total} 卷。再往上走，书还没写完。`,
          `${total} volumes in total. Keep climbing — the book is not finished.`,
        )}{" "}
        <a href="#/chronicle">{L("→ 读整本", "→ read the whole book")}</a>
      </p>
    </div>
  );
}
