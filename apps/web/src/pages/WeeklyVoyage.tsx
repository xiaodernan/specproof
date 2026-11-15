import { useMemo } from "react";
import { useI18n } from "../i18n";
import { ProductIcon } from "../ui/ProductIcon";
import evidence from "./evidence.json";
import unsigned from "./unsigned.json";
import "../styles/voyage.css";

/**
 * The Weekly Voyage — a living cover page next to Last Call:
 *
 *   row 1 · the ship's stamp — the latest committed stress evidence
 *   row 2 · what is still unsigned — LIVE audit (scripts/audit_unsigned.py),
 *           rebuilt at build time; green/amber/red honesty, never fabricated
 *   row 3 · the next knock — next Monday 03:00 UTC, computed live
 *
 * Evidence facts and the audit details come from build-time JSON (verbatim).
 * The next-knock date is the only clock read on the page.
 */
function nextMondayKnock(from: Date): Date {
  const d = new Date(Date.UTC(from.getUTCFullYear(), from.getUTCMonth(), from.getUTCDate(), 3, 0, 0));
  while (d <= from || d.getUTCDay() !== 1) {
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return d;
}

const STATUS_META: Record<string, { icon: string; zh: string; en: string; tone: "ok" | "warn" | "idle" | "bad" }> = {
  "signature-block-found": { icon: "✓", zh: "签字在场（未核实身份）", en: "signature found (identity NOT verified)", tone: "ok" },
  "awaiting-signature": { icon: "○", zh: "等待真人签字", en: "awaiting a human signature", tone: "warn" },
  "merged": { icon: "✓", zh: "已合入（首班等下个周一）", en: "merged (first strike next Monday)", tone: "ok" },
  "missing": { icon: "✗", zh: "未合入", en: "missing", tone: "bad" },
  "specproof-answering": { icon: "✓", zh: "本仓库在答", en: "specproof answering", tone: "ok" },
  "other-project-answering": { icon: "✗", zh: "别的项目在答", en: "another project answering", tone: "bad" },
  "port-free": { icon: "~", zh: "空门（无人答）", en: "port free (nothing answers)", tone: "idle" },
};

const CHECK_LABEL: Record<string, { zh: string; en: string }> = {
  "observability-signature": { zh: "真·fleet 遥测 · OBSERVABILITY.md 签字", en: "real fleet telemetry · OBSERVABILITY.md signature" },
  "weekly-stress-merged": { zh: "每周一敲门 · weekly-stress.yml 合入状态", en: "Monday knock · weekly-stress.yml merged" },
  "port-8000-answers": { zh: "端口 8000 · 此刻谁在答", en: "port 8000 · who answers right now" },
  "branch-cleanliness": { zh: "提交到过 origin 了吗 · 分支洁净度", en: "did your commits reach origin? · branch cleanliness" },
};

export default function WeeklyVoyage(): JSX.Element {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const L = (a: string, b: string): string => (zh ? a : b);

  const knock = useMemo(() => nextMondayKnock(new Date()), []);
  const latest = evidence.latest ?? null;
  const audit = unsigned.checks ?? [];
  const fmt = (d: Date) =>
    d.toISOString().slice(0, 16).replace("T", " ") + "Z (" + d.toLocaleString(locale === "zh" ? "zh-CN" : "en-GB", { weekday: "short", month: "short", day: "numeric" }) + ")";

  return (
    <section className="voyage-log" aria-label={L("本周航行日志", "The Weekly Voyage")}>
      <header className="voyage-head">
        <ProductIcon name="scroll" size={13} />
        <p className="voyage-kicker">{L("本周航行日志 · 船签 · 欠签 · 下一次敲门", "THE WEEKLY VOYAGE · stamp · unsigned · next knock")}</p>
      </header>
      <div className="voyage-grid">
        {/* row 1 — the ship's stamp */}
        <div className="voyage-cell">
          <span className="voyage-lane">{L("此刻船签 · 最近一次被敲", "SHIP'S STAMP · last struck")}</span>
          {latest ? (
            <>
              <p className="voyage-ship-name"><code>{latest.file}</code></p>
              <p className="voyage-ship-line">
                {L("敲击于", "struck")} <strong>{latest.started_utc.slice(0, 16).replace("T", " ")}Z</strong>
                {" · "}worst p99 <strong>{Math.round(latest.worst_p99_ms)}ms</strong>
                {" · "}total <strong>{latest.total_ok}/{latest.total}</strong>
              </p>
              <p className={latest.verdict === "OK" ? "voyage-verdict voyage-verdict-ok" : "voyage-verdict voyage-verdict-bad"}>
                {L("判定", "verdict")}: <strong>{latest.verdict}</strong>
              </p>
            </>
          ) : (
            <p className="voyage-empty">{L("尚未敲门——第一件证据还没有落库；敲完它会出现在这里。", "No knock yet — the first evidence has not landed; strike it and it lights up here.")}</p>
          )}
          <p className="voyage-source">{L("出厂源：docs/evidence/（git-tracked，原样摘抄）", "source: docs/evidence/ (git-tracked, verbatim)")}</p>
        </div>

        {/* row 2 — live unsigned audit */}
        <div className="voyage-cell">
          <span className="voyage-lane">{L("欠签 · 审计于本机", "UNSIGNED · audited on this host")}</span>
          <ul className="voyage-audit">
            {audit.map((c) => {
              const meta = STATUS_META[c.status] ?? { icon: "?", zh: c.status, en: c.status, tone: "idle" as const };
              const label = CHECK_LABEL[c.id]?.[locale === "zh" ? "zh" : "en"] ?? c.id;
              return (
                <li key={c.id} title={c.detail}>
                  <span className={`voyage-chip voyage-chip-${meta.tone}`}>{meta.icon}</span>
                  <span className="voyage-audit-label">
                    <strong>{label}</strong>
                    <em>{zh ? meta.zh : meta.en}</em>
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="voyage-source">{L(`审计时间：${unsigned.generated_utc.replace("T", " ").slice(0, 19)}Z · scripts/audit_unsigned.py 现场实测`, `audited at ${unsigned.generated_utc.replace("T", " ").slice(0, 19)}Z · live, by scripts/audit_unsigned.py`)}</p>
        </div>

        {/* row 3 — the next knock */}
        <div className="voyage-cell">
          <span className="voyage-lane">{L("下一次敲门的时间 · 下一班船", "NEXT KNOCK · next departure")}</span>
          <p className="voyage-next-day">{fmt(knock)}</p>
          <p className="voyage-next-note">{L("weekly-stress.yml 的 cron：每周一 03:00 UTC。什么都不推、不红旗、只存档。", "cron of weekly-stress.yml: every Monday 03:00 UTC. Pushes nothing, red-flags nothing, archives only.")}</p>
          <code className="voyage-next-cmd">python scripts/stress_smoke.py --warmup 2 --concurrency 48 --rounds 2 --json-report docs/evidence/&lt;name&gt;.json</code>
        </div>
      </div>
    </section>
  );
}
