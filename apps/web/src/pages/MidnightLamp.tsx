import { useI18n } from "../i18n";
import { ProductIcon } from "../ui/ProductIcon";
import unsigned from "./unsigned.json";
import "../styles/auditLights.css";

/**
 * The Midnight Lamp — the audit's three lamps hanging beside the Atlas.
 * The same live statuses #/last-call shows (unsigned.json, struck at
 * build time by scripts/audit_unsigned.py) rather than a new measurement:
 * one host, three lamps, one truth.
 */
const LABEL: Record<string, { zh: string; en: string }> = {
  "observability-signature": { zh: "真·fleet 遥测 · OBSERVABILITY.md 签字（amber until human-signed）", en: "real fleet telemetry · OBSERVABILITY.md sign-off" },
  "weekly-stress-merged": { zh: "每周一敲门 · weekly-stress.yml 合入", en: "the Monday knock · weekly-stress.yml" },
  "port-8000-answers": { zh: "端口 8000 · 此刻谁在答", en: "port 8000 · who answers right now" },
};

const TONE: Record<string, "ok" | "warn" | "idle" | "bad"> = {
  "signature-block-found": "ok",
  "awaiting-signature": "warn",
  merged: "ok",
  missing: "bad",
  "specproof-answering": "ok",
  "other-project-answering": "bad",
  "port-free": "idle",
};

export default function MidnightLamp(): JSX.Element {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const L = (a: string, b: string): string => (zh ? a : b);
  const checks = unsigned.checks ?? [];

  return (
    <section className="midnight-lamp" aria-label={L("长夜灯 · 三盏审计灯", "The Midnight Lamps")}>
      <header className="midnight-lamp-head">
        <ProductIcon name="shield" size={13} />
        <p className="midnight-lamp-kicker">{L("长夜灯 · 三盏 · 审计于本机", "THE MIDNIGHT LAMPS · three of them · audited on this host")}</p>
      </header>
      <div className="midnight-lamp-grid">
        {checks.map((c) => {
          const tone = TONE[c.status] ?? "idle";
          const label = LABEL[c.id]?.[locale] ?? c.id;
          return (
            <div key={c.id} className="midnight-lamp-cell" title={c.detail}>
              <span className={`midnight-lamp-dot midnight-lamp-dot-${tone}`} aria-hidden="true" />
              <div className="midnight-lamp-text">
                <p className="midnight-lamp-label">{label}</p>
                <p className="midnight-lamp-status"><code>{c.status}</code></p>
              </div>
            </div>
          );
        })}
      </div>
      <p className="midnight-lamp-foot">
        {L(
          `灯色逐态由 scripts/audit_unsigned.py 在本机现敲：${unsigned.generated_utc.replace("T", " ").slice(0, 19)}Z — 不验证身份、不伪造签字。`,
          `lamp tones struck live by scripts/audit_unsigned.py on this host at ${unsigned.generated_utc.replace("T", " ").slice(0, 19)}Z — identity never verified, signatures never fabricated.`,
        )}
      </p>
    </section>
  );
}
