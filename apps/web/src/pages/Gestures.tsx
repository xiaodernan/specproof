import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "../hooks/navigate";
import { useI18n } from "../i18n";
import { GESTURES, type GestureFace } from "./gestures.copy";
import "../styles/verification.css";

/**
 * 验收官十四式 · The Fourteen Faces of Verification —
 * an interactive gallery of the officer's fourteen ways of standing
 * before evidence. Assemble your set by tapping each face; each tap is
 * remembered in this browser only (localStorage), because a collector's
 * cabinet belongs to the collector alone.
 */

const STORAGE_KEY = "specproof_gestures_v1";

function loadCollected(): Set<string> {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((item): item is string => typeof item === "string"));
  } catch {
    return new Set();
  }
}

export default function Gestures() {
  const { t, locale } = useI18n();
  const navigate = useNavigate();
  const [collected, setCollected] = useState<Set<string>>(() => loadCollected());
  const [selected, setSelected] = useState<string>(GESTURES[0].id);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(collected)));
    } catch {
      // storage disabled — the cabinet lives for the session only
    }
  }, [collected]);

  const count = collected.size;
  const allCollected = count === GESTURES.length;

  const toggle = useCallback((id: string) => {
    setCollected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  const active: GestureFace = GESTURES.find((g) => g.id === selected) ?? GESTURES[0];

  return (
    <div className="gestures-page">
      <div className="page-head">
        <h1>{t("gestures.title")} <span className="gestures-en">{t("gestures.subtitle")}</span></h1>
        <div className="page-sub" title="THE FOURTEEN GESTURES">{t("gestures.lead")}</div>
      </div>

      <div className="gestures-progress" role="status" aria-live="polite">
        <strong>{count} / {GESTURES.length}</strong>
        <span>{allCollected ? t("gestures.complete") : t("gestures.collecting")}</span>
      </div>

      <div className="gestures-layout">
        <ul className="gestures-grid" aria-label={t("gestures.gridAria")}>
          {GESTURES.map((gesture) => {
            const owned = collected.has(gesture.id);
            const isSelected = selected === gesture.id;
            return (
              <li key={gesture.id}>
                <button
                  type="button"
                  className={
                    "gesture-card" +
                    (owned ? " gesture-card-owned" : "") +
                    (isSelected ? " gesture-card-selected" : "")
                  }
                  aria-pressed={owned}
                  aria-label={gesture.zhName + " · " + gesture.token}
                  onClick={() => { toggle(gesture.id); setSelected(gesture.id); }}
                >
                  <span className="gesture-numeral" aria-hidden="true">{gesture.numeral}</span>
                  <span className="gesture-zh">{gesture.zhName}</span>
                  <span className="gesture-en">{gesture.enName}</span>
                  <span className="gesture-token">{gesture.token}</span>
                  {owned ? <span className="gesture-check" aria-hidden="true">✓</span> : null}
                </button>
              </li>
            );
          })}
        </ul>

        <article className="gesture-detail" aria-labelledby={"gesture-title-" + active.id}>
          <div className="gesture-detail-head">
            <span className="gesture-detail-numeral" aria-hidden="true">{active.numeral}</span>
            <div>
              <h2 id={"gesture-title-" + active.id}>{active.zhName} <span className="gesture-en">{active.enName}</span></h2>
              <div className="gesture-token-chip">{active.token}</div>
            </div>
          </div>
          <p className="gesture-face">{active.face[locale]}</p>
          <p className="gesture-act">{active.act[locale]}</p>
          <button type="button" className="btn btn-primary" onClick={() => navigate(active.route)}>
            {active.routeLabel[locale]} <span aria-hidden="true">→</span>
          </button>
          <p className="muted gesture-token-note">{t("gestures.tokenNote")}</p>
        </article>
      </div>

      <p className="muted gestures-colophon">{t("gestures.colophon")}</p>
    </div>
  );
}
