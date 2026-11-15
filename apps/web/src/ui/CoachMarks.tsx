import { useCallback, useEffect, useState } from "react";
import { useI18n } from "../i18n";
import { COACH_MARKS, coachToggleEvent, readCoachEnabled, writeCoachEnabled } from "./coachData";
import "../styles/coach.css";

/**
 * The teaching layer: small gold badges over the main interface, each
 * self-explaining the actionable element underneath it. Toggle with `H`
 * anywhere outside an editable target, or with the topbar "?" button;
 * persists per browser; dismissed once, never nags again.
 *
 * Badges are positioned from live getBoundingClientRect measurements (a
 * 500ms collector plus scroll/resize listeners), because the shell mutates
 * often — hash route swaps, lazy chunks, sidebar toggles — and a stale
 * badge is worse than no badge.
 */

const isEditableTarget = (target: EventTarget | null): boolean =>
  target instanceof Element && !!target.closest('input, textarea, select, [contenteditable="true"]');

type Badge = (typeof COACH_MARKS)[number] & {
  x: number;
  y: number;
};

export function CoachMarks(): JSX.Element | null {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const [enabled, setEnabled] = useState<boolean>(() => readCoachEnabled());
  const [badges, setBadges] = useState<Badge[]>([]);

  const toggle = useCallback(() => {
    setEnabled((prev) => {
      writeCoachEnabled(!prev);
      return !prev;
    });
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) return;
      if (isEditableTarget(event.target)) return;
      if (event.key.toLowerCase() === "h") {
        event.preventDefault();
        toggle();
      }
    };
    const onToggleEvent = (): void => setEnabled(readCoachEnabled());
    window.addEventListener("keydown", onKey);
    window.addEventListener(coachToggleEvent(), onToggleEvent);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(coachToggleEvent(), onToggleEvent);
    };
  }, [toggle]);

  useEffect(() => {
    if (!enabled) {
      setBadges([]);
      return;
    }
    const byKey = new Map(COACH_MARKS.map((m) => [m.key, m]));
    const collect = (): void => {
      const out: Badge[] = [];
      document.querySelectorAll<HTMLElement>("[data-coach]").forEach((el) => {
        const mark = byKey.get(el.getAttribute("data-coach") ?? "");
        if (!mark) return;
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) return;
        out.push({ ...mark, x: Math.max(2, rect.left + 4), y: Math.max(2, rect.top - 9) });
      });
      setBadges(out);
    };
    collect();
    const interval = window.setInterval(collect, 500);
    window.addEventListener("resize", collect, { passive: true });
    window.addEventListener("scroll", collect, { capture: true, passive: true });
    return () => {
      window.clearInterval(interval);
      window.removeEventListener("resize", collect);
      window.removeEventListener("scroll", collect, true);
    };
  }, [enabled]);

  if (!enabled) return null;

  const ordered = [...badges].sort(
    (a, b) => COACH_MARKS.findIndex((m) => m.key === a.key) - COACH_MARKS.findIndex((m) => m.key === b.key),
  );

  return (
    <>
      {ordered.map((badge) => {
        const n = COACH_MARKS.findIndex((m) => m.key === badge.key) + 1;
        return (
          <div
            key={badge.key}
            className="coach-badge"
            style={{ left: badge.x, top: badge.y }}
            tabIndex={0}
            role="note"
            aria-label={`${zh ? "说明" : "About"}: ${badge.title[locale]} — ${badge.body[locale]}`}
          >
            <span className="coach-badge-num">{n}</span>
            <span className="coach-tip" role="tooltip">
              <strong>{badge.title[locale]}</strong>
              <span>{badge.body[locale]}</span>
            </span>
          </div>
        );
      })}

      <aside className="coach-legend" aria-label={zh ? "教学模式图例" : "Coach marks legend"}>
        <p className="coach-legend-kicker">{zh ? "教 学 模 式" : "COACH MARKS"}</p>
        <p className="coach-legend-title">{zh ? `${badges.length} 处按键与操作，皆已标出` : `${badges.length} controls annotated`}</p>
        <p className="coach-legend-body">{zh ? "金色徽章 = 可点可按；悬停/聚焦即可读懂它。按 H 或右侧按钮随时关闭。" : "Gold badges mark what you can touch; hover/focus to read each one. Press H or the button to hide."}</p>
        <button className="coach-legend-done" onClick={toggle}>
          {zh ? "全部看懂了 · 关闭教学" : "Got it — hide the marks"}
        </button>
      </aside>
    </>
  );
}
