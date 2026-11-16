import { useMemo, useState } from "react";
import { useI18n } from "../i18n";
import { ERRATA, type ErratumEntry } from "./errata.copy";
import ChainBanner from "./ChainBanner";
import "../styles/errata.css";

/**
 * 更正卷轴 · The Corrections Scroll —
 * a first-class page for the book's errata scroll, R01..R15.
 *
 * Each entry is a place we actually got it wrong; every anchor links a real
 * ledger entry or a real commit/file. Nothing here is lore.
 *
 * The page is the teacher this repo wished it had before: it does not ask you
 * to take any of its conclusions on faith. It asks you to try.
 */
export default function Errata() {
  const { t, locale } = useI18n();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<string | null>(ERRATA[0].id);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return ERRATA;
    return ERRATA.filter((e) =>
      `${e.id} ${e.category[locale]} ${e.gloss[locale]} ${e.detail[locale]} ${e.anchor}`
        .toLowerCase()
        .includes(q),
    );
  }, [query, locale]);

  return (
    <div className="errata-page">
      <div className="page-head">
        <h1>{t("errata.title")} <span className="errata-en">{t("errata.subtitle")}</span></h1>
        <div className="page-sub" title="ERRATA SCROLL">{t("errata.lead")}</div>
      </div>
      <ChainBanner />

      <label className="errata-search" htmlFor="errata-filter">
        <span className="visually-hidden">{t("errata.searchLabel")}</span>
        <input
          id="errata-filter"
          type="search"
          className="errata-filter"
          placeholder={t("errata.placeholder")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoComplete="off"
          spellCheck={false}
        />
        <span className="errata-count" aria-live="polite">{filtered.length} / {ERRATA.length}</span>
      </label>

      {filtered.length === 0 ? (
        <p className="muted errata-empty">{t("errata.noResult")}</p>
      ) : (
        <ol className="errata-list">
          {filtered.map((entry: ErratumEntry) => {
            const isOpen = open === entry.id;
            return (
              <li key={entry.id} className="errata-item">
                <button
                  type="button"
                  className={"errata-toggle" + (isOpen ? " errata-toggle-open" : "")}
                  aria-expanded={isOpen}
                  aria-controls={"errata-" + entry.id}
                  onClick={() => setOpen(isOpen ? null : entry.id)}
                >
                  <span className="errata-id">{entry.id}</span>
                  <span className="errata-gloss">{entry.gloss[locale]}</span>
                  <span className="errata-cat">{entry.category[locale]}</span>
                </button>
                {isOpen ? (
                  <div className="errata-detail" id={"errata-" + entry.id}>
                    <p>{entry.detail[locale]}</p>
                    <code className="errata-anchor">{entry.anchor}</code>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ol>
      )}

      <p className="muted errata-colophon">{t("errata.colophon")}</p>
    </div>
  );
}
