import { useI18n } from "../i18n";
import chain from "./audit_chain.json";
import { ProductIcon } from "../ui/ProductIcon";
import "../styles/chainBanner.css";

/**
 * A one-line roll-call, read straight from audit_chain.json:
 * exactly the numbers of the five audit lamps, struck live and counted.
 * The page never interprets — it just shows the lamps as they were struck.
 */
export default function ChainBanner(): JSX.Element {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const verdict = (chain as { verdict?: string }).verdict ?? "UNKNOWN";
  const lanes = (chain as { lane_count?: number }).lane_count ?? 0;
  const ok = verdict === "CLEAR";
  return (
    <aside className={`chain-banner chain-banner--${ok ? "ok" : "bad"}`} role="note" aria-label={zh ? "审计链今天" : "The audit chain today"}>
      <ProductIcon name="shield" size={14} />
      <p className="chain-banner-text">
        {zh
          ? `审计链 · ${verdict} · ${lanes} 盏灯（敲一次只数一遍；不造势，不瞒）`
          : `audit chain · ${verdict} · ${lanes} lamps (struck and counted once — never decorated, never doctored)`}
      </p>
      <a className="chain-banner-link" href="#/archive">{zh ? "对照铁证 →" : "Cross the iron →"}</a>
    </aside>
  );
}
