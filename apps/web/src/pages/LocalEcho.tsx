import { useMemo } from "react";
import { useI18n } from "../i18n";
import { deriveHeat, loadHeat } from "../telemetry/behavior";
import { ProductIcon } from "../ui/ProductIcon";
import "../styles/localEcho.css";

/**
 * The Local Echo — a strip embedded in the Manual that answers one honest
 * question: "which door did this browser keep bolting out of?"
 *
 * Data source: specproof_heat_v1 (this device only, never uploaded).
 * A bounce is a route view whose dwell fell below 4 seconds. Silence is
 * not zero: with no data the strip says so instead of inventing numbers.
 */
export default function LocalEcho(): JSX.Element | null {
  const { locale } = useI18n();
  const zh = locale === "zh";

  const bounce = useMemo(() => {
    try {
      const summary = deriveHeat(loadHeat());
      const events = loadHeat();
      const byRoute = new Map<string, number>();
      for (const e of events) {
        if (e.t === "dwell" && e.ms < 4000) byRoute.set(e.path, (byRoute.get(e.path) ?? 0) + 1);
      }
      const ranked = [...byRoute.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4);
      return { summary, ranked };
    } catch {
      return null;
    }
  }, []);

  if (!bounce) return null;
  const { summary, ranked } = bounce;

  return (
    <aside className="local-echo" aria-label={zh ? "本机回音壁" : "The Local Echo"}>
      <div className="local-echo-head">
        <ProductIcon name="scroll" size={13} />
        <p className="local-echo-kicker">{zh ? "本机回音壁 · 只读本机" : "THE LOCAL ECHO · this device only"}</p>
      </div>
      {summary.views === 0 || ranked.length === 0 ? (
        <p className="local-echo-empty">
          {zh
            ? "还没有秒退记录——沉默，不是 0。随便去走几间屋，再回来看它怎么变。"
            : "No quick-bounces recorded yet — silence, not zero. Walk through a few rooms and watch this change."}
        </p>
      ) : (
        <>
          <p className="local-echo-lead">
            {zh
              ? `这个浏览器曾快速离开：（<4 秒停留）`
              : `This browser bolted out of:`}
          </p>
          <ol className="local-echo-list">
            {ranked.map(([route, count]) => (
              <li key={route}>
                <code>{route}</code>
                <span className="local-echo-count">×{count}</span>
                <a className="local-echo-go" href={`#${route}`}>
                  {zh ? "再走一次 →" : "Walk it →"}
                </a>
              </li>
            ))}
          </ol>
          <p className="local-echo-hint">
            {zh
              ? "如果某扇门每次都让你急躁——按 H 给界面挂金色徽章，或者先从 #/tour 走一圈。"
              : "If a door keeps making you impatient — press H for the gold marks, or walk #/tour first."}
          </p>
        </>
      )}
    </aside>
  );
}
