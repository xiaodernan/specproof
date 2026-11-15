import { useMemo } from "react";
import { useI18n } from "../i18n";
import { ProductIcon } from "../ui/ProductIcon";
import evidence from "./evidence.json";
import "../styles/voyage.css";

/**
 * The Weekly Voyage — a living cover page next to Last Call:
 *
 *   row 1 · the ship's stamp — the latest committed stress evidence
 *   row 2 · what is still unsigned — honest absences, no invented fixes
 *   row 3 · the next knock — next Monday 03:00 UTC, computed live
 *
 * Evidence facts come from the build-time distilled evidence.json (verbatim).
 * The two dates are the only live clock reads on the page.
 */
function nextMondayKnock(from: Date): Date {
  const d = new Date(Date.UTC(from.getUTCFullYear(), from.getUTCMonth(), from.getUTCDate(), 3, 0, 0));
  while (d <= from || d.getUTCDay() !== 1) {
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return d;
}

export default function WeeklyVoyage(): JSX.Element {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const L = (a: string, b: string): string => (zh ? a : b);

  const knock = useMemo(() => nextMondayKnock(new Date()), []);
  const latest = evidence.latest ?? null;
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
        {/* row 2 — what is still unsigned */}
        <div className="voyage-cell">
          <span className="voyage-lane">{L("欠签 · 仍然没有真人签字的欠条", "STILL UNSIGNED")}</span>
          <ul className="voyage-unsigned">
            <li>{L("真·fleet 遥测——需要 OBSERVABILITY.md 的真人签字，永远不够随手一按", "Real fleet telemetry — needs a human signature on OBSERVABILITY.md; never one click away")}</li>
            <li>{L("weekly-stress.yml 的船还没启航——合入 master 后，下一个周一 03:00 UTC 才敲第一班", "weekly-stress.yml has not sailed — its first strike is the Monday 03:00 UTC after merge into master")}</li>
            <li>{L("127.0.0.1:8000 不是本仓库的门——那一扇属于 career-os-ai-service（com.docker.backend）", "127.0.0.1:8000 is not this repo's door — it belongs to career-os-ai-service (com.docker.backend)")}</li>
          </ul>
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
