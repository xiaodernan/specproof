import { useMemo, useState } from "react";
import { useI18n } from "../i18n";
import entries from "./chronicle.json";
import ChainBanner from "./ChainBanner";
import "../styles/chronicle.css";

/**
 * SpecProof Chronicle — the auto-generated 1759-entry digest of the
 * deep-optimization ledger, rendered as a house you can walk through.
 * Every row is a real ledger entry (#130 → #1759). Nothing is lore.
 */
interface ChronicleEntry {
  n: number;
  t: string;
  s: string;
}

const ALL: ChronicleEntry[] = entries as unknown as ChronicleEntry[];
const FIRST = ALL[0]?.n ?? 0;
const LAST = ALL[ALL.length - 1]?.n ?? 0;

export default function Chronicle() {
  const { t } = useI18n();
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return ALL;
    const num = q.match(/#?(\d{1,4})/);
    return ALL.filter((entry) => {
      const hay = `${entry.n} ${entry.t} ${entry.s}`.toLowerCase();
      if (hay.includes(q)) return true;
      if (num && String(entry.n) === num[1]) return true;
      return false;
    });
  }, [query]);

  return (
    <div className="chronicle-page">
      <div className="page-head">
        <h1>{t("chronicle.title")} <span className="chronicle-en">{t("chronicle.subtitle")}</span></h1>
        <div className="page-sub">
          {t("chronicle.lead").replace("{total}", String(ALL.length)).replace("{first}", String(FIRST)).replace("{last}", String(LAST))}
        </div>
      </div>

      <ChainBanner />
      <label className="chronicle-search" htmlFor="chronicle-filter">
        <span className="visually-hidden">{t("chronicle.searchLabel")}</span>
        <input
          id="chronicle-filter"
          type="search"
          className="chronicle-filter"
          placeholder={t("chronicle.placeholder")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoComplete="off"
          spellCheck={false}
        />
        <span className="chronicle-count" aria-live="polite">{filtered.length} / {ALL.length}</span>
      </label>

      <ol className="chronicle-list">
        {filtered.map((entry) => (
          <li key={entry.n} className="chronicle-item">
            <div className="chronicle-row">
              <span className="chronicle-num">#{entry.n}</span>
              <div className="chronicle-body">
                <div className="chronicle-title">{entry.t}</div>
                {entry.s ? <div className="chronicle-snippet">{entry.s}</div> : null}
              </div>
            </div>
          </li>
        ))}
      </ol>

      {filtered.length === 0 ? <p className="chronicle-empty">{t("chronicle.noResult")}</p> : null}
    </div>
  );
}
