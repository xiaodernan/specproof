import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../i18n";
import { coachToggleEvent } from "./coachData";
import { deriveHeat, loadHeat } from "../telemetry/behavior";
import { hintsForRage } from "./rage";
import { ProductIcon } from "./ProductIcon";
import "../styles/rage.css";

/**
 * The rage-response coach: when THIS browser has hammered the same control
 * before (specproof_heat_v1), surface — once, dismissible — one honest
 * paragraph explaining what actually unblocks that spot. Local-only, never
 * uploaded, never tied to any person. Acknowledging stores only a count
 * (the number of rage-taps seen so far on this device).
 */

const ACK_KEY = "specproof_heat_ack_v1";

function readAck(): number {
  try {
    return Number(globalThis.localStorage?.getItem(ACK_KEY) ?? 0) || 0;
  } catch {
    return 0;
  }
}

function writeAck(count: number): void {
  try {
    globalThis.localStorage?.setItem(ACK_KEY, String(count));
  } catch {
    /* silent — acknowledgement is best-effort */
  }
}

export function RageCoach(): JSX.Element | null {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const [open, setOpen] = useState(false);
  const [hints, setHints] = useState<ReturnType<typeof hintsForRage>>([]);
  const [rageTotal, setRageTotal] = useState(0);

  useEffect(() => {
    try {
      const summary = deriveHeat(loadHeat());
      const ack = readAck();
      if (summary.rageTotal > ack && summary.rageTotal >= 3) {
        setHints(hintsForRage(summary.rageTop, 2));
        setRageTotal(summary.rageTotal);
        setOpen(true);
      }
    } catch {
      /* storage unreadable — stay silent rather than nag */
    }
  }, []);

  const count = useMemo(() => hints.reduce((n, h) => n + h.count, 0), [hints]);

  if (!open || hints.length === 0) return null;

  return (
    <aside className="rage-coach" role="complementary" aria-label={zh ? "来自本机气候图的回报" : "Returned by this browser's climate log"}>
      <div className="rage-coach-head">
        <ProductIcon name="scroll" size={13} />
        <p className="rage-coach-kicker">{zh ? "气候图回报 · 本机" : "CLIMATE REPORT · this device"}</p>
        <button type="button" className="rage-coach-close" aria-label={zh ? "关闭" : "Dismiss"} onClick={() => setOpen(false)}>×</button>
      </div>
      <p className="rage-coach-lead">
        {zh
          ? `这个浏览器在同一位置连续重敲了 ${count} 次。多半它下面藏着一句说明——`
          : `This browser hammered the same spot ${count} time${count > 1 ? "s" : ""}. Often a hint hides right under it —`}
      </p>
      <ul className="rage-coach-hints">
        {hints.map((hint) => (
          <li key={hint.key}>
            <strong>{hint.title[locale]}</strong>
            <span>{hint.body[locale]}</span>
          </li>
        ))}
      </ul>
      <div className="rage-coach-actions">
        <button type="button" className="rage-coach-arm" onClick={() => { globalThis.dispatchEvent(new Event(coachToggleEvent())); setOpen(false); }}>
          {zh ? "按 H · 打开金色教学徽章" : "Press H · arm the gold marks"}
        </button>
        <button type="button" className="rage-coach-ack" onClick={() => { writeAck(rageTotal); setOpen(false); }}>
          {zh ? "本机记住，不再提醒" : "Remember on this device"}
        </button>
      </div>
    </aside>
  );
}
