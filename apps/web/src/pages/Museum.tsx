import { useMemo, useState } from "react";
import { useI18n } from "../i18n";
import { EXHIBITS, type MuseumExhibit } from "./museum.copy";
import "../styles/verification.css";

/**
 * 铁证博物馆 · The Evidence Museum — twelve permanent exhibits, one truth per
 * plaque. Every anchor points at a real ledger id, a real file, or a real
 * measurement. Nothing here is lore; nothing is decorative.
 *
 * Layout: a filterable wall of plaques; tap to unfold the full story.
 * The exhibits are ordered roughly chronologically by what an auditor would
 * want to walk past first.
 */
export default function Museum() {
  const { t, locale } = useI18n();
  const [open, setOpen] = useState<string | null>(EXHIBITS[0].id);
  const [tag, setTag] = useState<string>("all");

  const tags = useMemo(() => {
    const seen = new Set<string>();
    for (const e of EXHIBITS) seen.add(e.tag.zh);
    return Array.from(seen);
  }, []);

  const filtered = useMemo(
    () => (tag === "all" ? EXHIBITS : EXHIBITS.filter((e) => e.tag.zh === tag)),
    [tag],
  );

  return (
    <div className="museum-page">
      <div className="page-head">
        <h1>{t("museum.title")} <span className="museum-en">{t("museum.subtitle")}</span></h1>
        <div className="page-sub" title="THE EVIDENCE MUSEUM">{t("museum.lead")}</div>
      </div>

      <div className="museum-tags" role="group" aria-label={t("museum.filter")}>
        <button type="button" className={"museum-tag" + (tag === "all" ? " museum-tag-active" : "")} onClick={() => setTag("all")} aria-pressed={tag === "all"}>{t("museum.all")}</button>
        {tags.map((zhTag) => {
          const enTag = EXHIBITS.find((e) => e.tag.zh === zhTag)?.tag.en ?? zhTag;
          return (
            <button key={zhTag} type="button" className={"museum-tag" + (tag === zhTag ? " museum-tag-active" : "")} onClick={() => setTag(zhTag)} aria-pressed={tag === zhTag}>
              {locale === "zh" ? zhTag : enTag}
            </button>
          );
        })}
      </div>

      <ul className="museum-wall">
        {filtered.map((exhibit: MuseumExhibit) => {
          const isOpen = open === exhibit.id;
          return (
            <li key={exhibit.id} className={"museum-plaque" + (isOpen ? " museum-plaque-open" : "")}>
              <button
                type="button"
                className="museum-plaque-head"
                aria-expanded={isOpen}
                aria-controls={"museum-" + exhibit.id}
                onClick={() => setOpen(isOpen ? null : exhibit.id)}
              >
                <span className="museum-numeral" aria-hidden="true">{exhibit.numeral}</span>
                <span className="museum-title">{exhibit.title[locale]}</span>
                <span className="museum-tag-chip">{exhibit.tag[locale]}</span>
                <span className="museum-chevron" aria-hidden="true">{isOpen ? "▴" : "▾"}</span>
              </button>
              {isOpen ? (
                <div className="museum-plaque-body" id={"museum-" + exhibit.id}>
                  <p>{exhibit.story[locale]}</p>
                  <code className="museum-anchor">{exhibit.anchor}</code>
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>

      <p className="muted museum-colophon">{t("museum.colophon")}</p>
    </div>
  );
}
