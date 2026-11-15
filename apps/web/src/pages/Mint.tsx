import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../i18n";
import { loadTourProgress, isTourSealed, TOUR_STATIONS } from "../ui/tour";
import { loadOnboardingProgress } from "../ui/onboarding";
import { readDrillRecord, tierIndexFor, TIERS } from "./drill.copy";
import { DRILL_TOTAL } from "./drillQuestions";
import { GESTURES } from "./gestures.copy";
import { loadHeat, deriveHeat } from "../telemetry/behavior";
import { ProductIcon } from "../ui/ProductIcon";
import "../styles/mint.css";

/**
 * The Mint — the visitor's own vault. Every number here is read fresh from
 * THIS browser's localStorage (specproof_tour_v1 / specproof_drill_v1 /
 * specproof_gestures_v1 / specproof_onboarding_v1 / specproof_heat_v1). Nothing is uploaded,
 * nothing is averaged across users, nothing is inferred. If storage cannot
 * be read, the page says "unknown", never "0".
 */

function readGestureCollected(): { status: "ok" | "unknown" | "absent"; collected: Set<string> } {
  try {
    const raw = window.localStorage.getItem("specproof_gestures_v1");
    if (raw === null || raw === "") return { status: "absent", collected: new Set() };
    const parsed = JSON.parse(raw) as Array<string>;
    if (!Array.isArray(parsed)) return { status: "unknown", collected: new Set() };
    return { status: "ok", collected: new Set(parsed) };
  } catch {
    return { status: "unknown", collected: new Set() };
  }
}

export default function Mint(): JSX.Element {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const L = (a: string, b: string): string => (zh ? a : b);

  const [printAttempted, setPrintAttempted] = useState(false);

  const tour = useMemo(() => loadTourProgress(), []);
  const onboarding = useMemo(() => loadOnboardingProgress(), []);
  const drill = useMemo(() => readDrillRecord(), []);
  const gestures = useMemo(() => readGestureCollected(), []);
  const heat = useMemo(() => deriveHeat(loadHeat()), []);

  const visited = onboarding.status === "ok" ? Object.entries(onboarding.progress.visited) : [];
  const lastFive = [...visited].sort((a, b) => (a[1] < b[1] ? 1 : -1)).slice(0, 5);
  const stampsDone = TOUR_STATIONS.filter((s) => tour.progress.completed.includes(s.id)).length;
  const tierIdx = tierIndexFor(drill.best);

  useEffect(() => {
    document.title = L("印记阁 · SpecProof", "The Mint · SpecProof");
  }, [zh]);

  return (
    <div className="mint-page">
      <header className="mint-mast">
        <p className="mint-kicker">{L("自 证 之 匣", "EVIDENCE BY YOUR OWN HAND")}</p>
        <h1>{L("印记阁", "The Mint")} <span className="mint-en">{L("THE MINT OF YOUR MARKS", "印 记 阁")}</span></h1>
        <p className="mint-lead">
          {L(
            "这里只陈列你在本浏览器里亲手盖过的印、走过的步子和找回的手势——不上传、不汇总、不代表任何人。若存储读不出，本页会写「未知」，而不是假装是零。",
            "This page shows only what this browser itself saw you do — seals, steps, retrieved gestures. Nothing is uploaded or aggregated, and if your storage cannot be read, the page says “unknown”, never a faked zero.",
          )}
        </p>
        <div className="mint-kpis">
          <div className="mint-kpi"><p className="mint-kpi-v">{tour.corrupted ? "—" : stampsDone}/{TOUR_STATIONS.length}</p><p className="mint-kpi-l">{L("已盖的印", "seals affixed")}</p></div>
          <div className="mint-kpi"><p className="mint-kpi-v">{drill.best}/{DRILL_TOTAL}</p><p className="mint-kpi-l">{L("快问最好成绩", "drill best")}</p></div>
          <div className="mint-kpi"><p className="mint-kpi-v">{gestures.status === "ok" ? gestures.collected.size : gestures.status === "absent" ? 0 : "—"}/{GESTURES.length}</p><p className="mint-kpi-l">{L("十四式已收", "gestures collected")}</p></div>
          <div className="mint-kpi"><p className="mint-kpi-v">{onboarding.status === "ok" ? visited.length : "?"}</p><p className="mint-kpi-l">{L("脚迹次数", "visits recorded")}</p></div>
          <div className="mint-kpi"><p className="mint-kpi-v">{heat.events}</p><p className="mint-kpi-l">{L("点按事件", "tap events")}</p></div>
        </div>
      </header>

      <div className="mint-grid">
        {/* ── the seals ─────────────────────────────────────────── */}
        <section className="mint-panel mint-seals-panel" aria-label={L("巡览六印", "Six seals of the tour")}>
          <h2>{L("六印之册", "The Six Seals")} <span className="mint-panel-note">{tour.corrupted ? L("（存储损坏，我不替你猜）", "(storage corrupted — I will not guess)") : isTourSealed(tour.progress) ? L("已封印", "SEALED") : L("未封印", "not yet sealed")}</span></h2>
          <div className="mint-stamps">
            {TOUR_STATIONS.map((s) => {
              const done = !tour.corrupted && tour.progress.completed.includes(s.id);
              return (
                <div key={s.id} className={"mint-stamp" + (done ? " mint-stamp-done" : "")}>
                  <span className="mint-stamp-numeral">{s.numeral}</span>
                  <span className="mint-stamp-name">{s.title}</span>
                  <span className="mint-stamp-en">{s.en}</span>
                  <span className="mint-stamp-state">{done ? L("验讫", "AFFIXED") : L("虚位", "VOID")}</span>
                </div>
              );
            })}
          </div>
          {tour.progress.sealed_at && <p className="mint-footnote">{L("封印于", "Sealed at")} {tour.progress.sealed_at.slice(0, 16).replace("T", " ")}</p>}
        </section>

        {/* ── the drill ladder ──────────────────────────────────── */}
        <section className="mint-panel mint-drill-panel">
          <h2>{L("快问之阶", "The Drill Ladder")}</h2>
          <p className="mint-drill-score">{drill.best}<span>/{DRILL_TOTAL}</span><em>{L("最好成绩", "best")} · {drill.runs} {L("次尝试", "runs")}</em></p>
          <ol className="mint-ladder">
            {TIERS.map((t, i) => (
              <li key={t.at} className={"mint-ladder-rung" + (tierIdx >= i ? " mint-rung-reached" : "")}>
                <span className="mint-rung-at">{t.at}</span>
                <span className="mint-rung-name">{zh ? t.zh : t.en}</span>
                <span className="mint-rung-note">{zh ? t.note.zh : t.note.en}</span>
              </li>
            ))}
          </ol>
        </section>

        {/* ── the fourteen gestures ─────────────────────────────── */}
        <section className="mint-panel mint-gestures-panel">
          <h2>{L("十四式手印", "The Fourteen Gestures")}</h2>
          <div className="mint-gestures">
            {GESTURES.map((g) => {
              const owned = gestures.collected.has(g.id);
              return (
                <div key={g.id} className={"mint-gesture" + (owned ? " mint-gesture-owned" : "")} title={g.enName}>
                  <span className="mint-gesture-numeral">{g.numeral}</span>
                  <span className="mint-gesture-name">{zh ? g.zhName : g.enName}</span>
                </div>
              );
            })}
          </div>
          <p className="mint-footnote">
            {gestures.status === "unknown"
              ? L("存储读不出来——未知，不写零。", "storage unreadable — unknown, not zero.")
              : gestures.status === "absent"
                ? L("还没有收集到任何手印——从十四式开始。", "no gestures yet — start at the Fourteen.")
                : `${gestures.collected.size} / ${GESTURES.length}`}
          </p>
        </section>

        {/* ── the footsteps ─────────────────────────────────────── */}
        <section className="mint-panel mint-trace-panel">
          <h2>{L("最近脚迹", "Recent Footsteps")}</h2>
          {onboarding.status !== "ok" ? (
            <p className="mint-trace-empty">{L("本浏览器没有可读的路由记录（无痕模式或未开始）——这不代表你走过零次。", "no readable route record in this browser (private window, or fresh) — this does not mean you visited nothing.")}</p>
          ) : lastFive.length === 0 ? (
            <p className="mint-trace-empty">{L("走出去第一步之后，这一页才会有内容。", "Step once into the product and this page starts to remember.")}</p>
          ) : (
            <ol className="mint-trace">
              {lastFive.map(([route, at]) => (
                <li key={route}><code>{route}</code><span className="mint-trace-at">{at.slice(0, 16).replace("T", " ")}</span></li>
              ))}
            </ol>
          )}
        </section>

        {/* ── the tap climate (specproof_heat_v1) ───────────────── */}
        <section className="mint-panel mint-heat-panel">
          <h2>{L("点按气候（specproof_heat_v1）", "The Tap Climate (specproof_heat_v1)")} <span className="mint-panel-note">{L("这个浏览器亲手敲出的真实轨迹", "the raw trail this browser typed out itself")}</span></h2>
          <div className="mint-heat-stats">
            <div><p>{heat.views}</p><span>{L("路由视图", "views")}</span></div>
            <div><p>{heat.distinctRoutes}</p><span>{L("不同页面", "routes")}</span></div>
            <div><p>{heat.quickBounces}</p><span>{L("秒退(<4s)", "bounces(<4s)")}</span></div>
            <div><p>{heat.rageTotal}</p><span>{L("暴怒点按", "rage taps")}</span></div>
          </div>
          {heat.rageTop.length > 0 ? (
            <p className="mint-footnote">{L("最暴怒点按", "most-raged target")}: <code>{heat.rageTop[0].target}</code> ×{heat.rageTop[0].count} — {L("完整气候图见洞察舱 #/insight", "full climate chart at #/insight")}</p>
          ) : (
            <p className="mint-footnote">{L("还没有暴怒点按；要清空本机轨迹，同样在洞察舱 #/insight", "no rage taps yet; to clear this trace, head to #/insight")}</p>
          )}
        </section>
      </div>

      {/* ── the personal certificate ─────────────────────────────── */}
      <section className="mint-certificate" aria-label={L("自印凭证", "A certificate pressed by your own hand")}>
        <p className="mint-certificate-kicker">{L("自 印 凭 证", "A CERTIFICATE PRESSED BY YOUR OWN HAND")}</p>
        <p className="mint-certificate-body">
          {zh
            ? `此浏览器于本地记下：${tour.corrupted ? "?" : stampsDone}/6 枚巡览之印 · 快问最好 ${drill.best}/${DRILL_TOTAL}（${drill.runs} 次尝试） · ${gestures.status === "ok" ? gestures.collected.size : "?"}/14 式手印 · ${onboarding.status === "ok" ? visited.length : "?"} 次足迹。此凭证只读本机存储，不含任何服务端事实；它不是验收报告，也不是给任何人看的——它只是你的铁证物证的回声。`
            : `This browser remembers locally: ${tour.corrupted ? "?" : stampsDone}/6 tour seals · drill best ${drill.best}/${DRILL_TOTAL} (${drill.runs} runs) · ${gestures.status === "ok" ? gestures.collected.size : "?"}/14 gestures · ${onboarding.status === "ok" ? visited.length : "?"} recorded visits. It reads local storage only; it is not a verification report and it is not for any audience but you — it is the echo of your own iron.`}
        </p>
        <button type="button" className="mint-print" onClick={() => { setPrintAttempted(true); window.print(); }}>
          {printAttempted ? L("再打印一次", "Print again") : L("打印此证", "Print this certificate")}
        </button>
      </section>

      <footer className="mint-footer">
        <ProductIcon name="shield" size={13} />
        <p>
          {zh
            ? "本页只读取本地存储（specproof_tour_v1 / specproof_drill_v1 / specproof_gestures_v1 / specproof_onboarding_v1 / specproof_heat_v1）——不上报、不汇总、不与服务端对账。这一枚印不是验收报告；真实验收仍以矩阵与人签为准。船队级真实遥测见 docs/operations/OBSERVABILITY.md。"
            : "This page reads only local storage (specproof_tour_v1 / specproof_drill_v1 / specproof_gestures_v1 / specproof_onboarding_v1 / specproof_heat_v1) — nothing is uploaded or reconciled with the server. These marks are not a verification report; real acceptance still hangs on the matrix and a human signature. For real fleet telemetry see docs/operations/OBSERVABILITY.md."}
        </p>
      </footer>
    </div>
  );
}
