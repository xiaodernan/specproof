import { useMemo, useState } from "react";
import { useI18n } from "../i18n";
import { LEXICON, type LexiconEntry } from "./lexicon.copy";
import "../styles/verification.css";

/**
 * 铁证词典 · Iron Lexicon — the 14 entries of
 * docs/world/APPENDIX_IRON_LEXICON.md, readable in one tap.
 *
 * Search filters as you type; the match is over term + gloss + iron prose,
 * in both languages, so an English query finds a Chinese entry and vice
 * versa. Nothing on this page is lore — every anchor opens a real file.
 */
export default function Lexicon() {
  const { t, locale } = useI18n();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return LEXICON;
    return LEXICON.filter((entry) =>
      [
        entry.term,
        entry.anchor,
        entry.gloss.zh,
        entry.gloss.en,
        entry.iron.zh,
        entry.iron.en,
      ]
        .join(" ")
        .toLowerCase()
        .includes(q),
    );
  }, [query]);

  return (
    <div className="lexicon-page">
      <div className="page-head">
        <h1>{t("lexicon.title")} <span className="lexicon-en">{t("lexicon.subtitle")}</span></h1>
        <div className="page-sub" title="IRON LEXICON">{t("lexicon.lead")}</div>
      </div>

      <label className="lexicon-search" htmlFor="lexicon-filter">
        <span className="visually-hidden">{t("lexicon.searchLabel")}</span>
        <input
          id="lexicon-filter"
          type="search"
          className="lexicon-filter"
          placeholder={t("lexicon.placeholder")}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          autoComplete="off"
          spellCheck={false}
        />
        <span className="lexicon-count" aria-live="polite">
          {filtered.length} / {LEXICON.length}
        </span>
      </label>

      {filtered.length === 0 ? (
        <p className="muted lexicon-empty">{t("lexicon.noResult")}</p>
      ) : (
        <ul className="lexicon-list">
          {filtered.map((entry: LexiconEntry) => {
            const isOpen = open === entry.term;
            return (
              <li key={entry.term} className="lexicon-item">
                <button
                  type="button"
                  className={"lexicon-toggle" + (isOpen ? " lexicon-toggle-open" : "")}
                  aria-expanded={isOpen}
                  aria-controls={"lexicon-" + entry.term.replace(/[^a-zA-Z0-9_]/g, "-")}
                  onClick={() => setOpen(isOpen ? null : entry.term)}
                >
                  <span className="lexicon-term">{entry.term}</span>
                  <span className="lexicon-gloss">{entry.gloss[locale]}</span>
                  <span className="lexicon-chevron" aria-hidden="true">{isOpen ? "▴" : "▾"}</span>
                </button>
                {isOpen ? (
                  <div
                    className="lexicon-detail"
                    id={"lexicon-" + entry.term.replace(/[^a-zA-Z0-9_]/g, "-")}
                  >
                    <p>{entry.iron[locale]}</p>
                    <code className="lexicon-anchor">{entry.anchor}</code>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}

      <p className="muted lexicon-colophon">{t("lexicon.colophon")}</p>
    </div>
  );
}
