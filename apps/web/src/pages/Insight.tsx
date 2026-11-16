import { useMemo, useState } from "react";
import { useI18n, type Locale } from "../i18n";
import { useIdentityAccess } from "../identity/useIdentityAccess";
import { PermissionDenied } from "../identity/PermissionDenied";
import { buildInsight } from "./insight.copy";
import { loadOnboardingProgress } from "../ui/onboarding";
import { clearHeat, deriveHeat, loadHeat } from "../telemetry/behavior";
import { ProductIcon } from "../ui/ProductIcon";
import "../styles/insight.css";

/**
 * The Insight Deck — admin-only analytics over a clearly-labelled SYNTHETIC
 * cohort, plus this browser's own real onboarding telemetry.
 *
 * What this page is:
 *   - an admin/operator-gated read panel: aggregate, anonymised, no PII;
 *   - a deterministic calibration population (seeded) with honest labels
 *     everywhere a number is quoted, so the demo never masquerades as real;
 *   - a miniature trend room: least-squares over the last 14 days with an
 *     honest r² and a 7-day forecast.
 *
 * What this page is NOT:
 *   - a surveillance of any real person;
 *   - a gate passed by typing "123";
 *   - a place where demo data becomes "evidence".
 */

const pick = (rec: Record<Locale, string>, locale: Locale) => rec[locale];
const pct = (n: number) => Math.round(n * 100) + "%";

export default function Insight() {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const { checked, canManage } = useIdentityAccess();
  const data = useMemo(() => buildInsight(), []);
  const [heatVersion, setHeatVersion] = useState(0);
  const heat = useMemo(() => loadHeat(), [heatVersion]);
  const heatSummary = useMemo(() => deriveHeat(heat), [heat]);

  const local = useMemo(() => {
    const out = { visits: 0, routes: [] as { path: string; at: string }[] };
    try {
      const raw = loadOnboardingProgress();
      if (raw.status === "ok") {
        const entries = Object.entries(raw.progress.visited);
        out.visits = entries.length;
        out.routes = entries
          .sort((a, b) => (a[1] < b[1] ? 1 : -1))
          .slice(0, 5)
          .map(([path, at]) => ({ path, at }));
      }
    } catch {
      /* unreadable storage is an unknown — never rendered as zero */
    }
    return out;
  }, []);

  if (!checked) return <div className="insight-gate"><div className="insight-spinner" aria-label={zh ? "加载中" : "Loading"} /></div>;

  if (!canManage) {
    return (
      <div className="page-head">
        <h1>{zh ? "洞察舱" : "Insight Deck"} <span className="insight-en">{zh ? "INSIGHT DECK" : "洞察舱"}</span></h1>
        <div className="page-sub">{zh ? "本页仅对 admin / operator 角色开放。" : "This deck is visible to admin/operator roles only."}</div>
        <PermissionDenied action={zh ? "洞察舱仅对 admin / operator 开放（RBAC fail-closed）" : "Insight Deck is admin / operator only (RBAC fail-closed)"} />
      </div>
    );
  }

  const maxSessions = Math.max(...data.sessionsPerDay, ...data.predictedNext7, 1);
  const maxFeature = Math.max(...data.features.map((f) => f.users));
  const funnelMax = data.funnel[0]?.count ?? 1;

  const sparkW = 720;
  const sparkH = 150;
  const sparkPadX = 10;
  const sparkPadY = 12;
  const sparkPoints = data.sessionsPerDay.map((v, i) => {
    const x = sparkPadX + (i * (sparkW - 2 * sparkPadX)) / (data.sessionsPerDay.length - 1);
    const y = sparkH - sparkPadY - ((v / maxSessions) * (sparkH - 2 * sparkPadY));
    return { x, y, v };
  });
  const sparkPath = sparkPoints.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const predicted = data.predictedNext7.map((v, k) => {
    const idx = data.sessionsPerDay.length + k;
    const x = sparkPadX + (idx * (sparkW - 2 * sparkPadX)) / (data.sessionsPerDay.length - 1 + 7);
    const y = sparkH - sparkPadY - ((v / maxSessions) * (sparkH - 2 * sparkPadY));
    return `${k === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");

  const recommendations = [
    {
      key: "tour", priority: "P1",
      title: zh ? "巡览第 3–5 章中途流失：在第 2 章后强制挂一次「H 教学模式」横幅" : "Tour drop-off after chapter 2: force the H coach-marks banner after chapter 2",
      evidence: zh ? `巡览开始 ${data.funnel[1].count} · 通关 ${data.funnel[2].count}（${pct(data.tourCompletionRate)}）` : `tour started ${data.funnel[1].count} · finished ${data.funnel[2].count} (${pct(data.tourCompletionRate)})`,
      action: zh ? "提示文案带『按 H』；未命中的用户 48 小时后再次在 Dashboard 复现" : "CTA carries “press H”; un-hit cohort re-prompted on Dashboard within 48h",
      confidence: 0.84,
    },
    {
      key: "drill", priority: "P1",
      title: zh ? "快问准确率偏低：把 i18n / base_pass_head_fail 两题降级为「复习卡」而非阻断题" : "Drill pass-rate is soft: re-classify the i18n / base_pass_head_fail items as review cards, not gate questions",
      evidence: zh ? `快问通过率 ${pct(data.drillPassRate)}（${data.population} 样本内）` : `drill pass ${pct(data.drillPassRate)} (n=${data.population} synthetic)`,
      action: zh ? "把 2/12 题改为「正确示范」卡片；Failure 按钮 →「再看一遍」" : "2 of 12 items become worked examples; the failure button becomes “show me why”",
      confidence: 0.78,
    },
    {
      key: "manual", priority: "P2",
      title: zh ? "袖中手札使用率 14%：把打印版 /manual 放到首验入口侧边而非 footer 链接" : "Pocket Card usage 14%: move the printable /manual to the new-verification sidebar instead of the footer link",
      evidence: zh ? "manual 触达 33/240，且触达者中 run-together 首验率高 1.9×" : "manual reached 33/240; of those, first-verification conversion was 1.9×",
      action: zh ? "jobs/new 右栏加「袖中手札·16 字」折叠条 + 一键打印" : "Add a collapsed 16-word strip in jobs/new with one-click print",
      confidence: 0.71,
    },
    {
      key: "worldbook", priority: "P2",
      title: zh ? "世界书通读率 40%：每合入一卷即在史诗顶「新卷」徽章 + push toast" : "World Book read-through 40%: on every merged volume, pin a “New volume” badge at Epic’s top + push toast",
      evidence: zh ? `世界书触达 ${data.features[4].users}/240` : `world book opened by ${data.features[4].users}/240`,
      action: zh ? "composable output from scripts/build_worldbook.py + push to the sidebar-guide rail" : "composable output from scripts/build_worldbook.py + push on the sidebar guide rail",
      confidence: 0.68,
    },
    {
      key: "nightwatch", priority: "P2",
      title: zh ? "子时守夜通关仅 5%：在 /nightwatch 第 4 站插一句「你离验讫只差 3 站」锚点句" : "Night Watch clear-rate 5%: inject “three stations to the seal” anchor at station 4",
      evidence: zh ? "通关 12/240 · 中途放弃集中在 station 4（印章庭前）" : "12/240 cleared · abandonment clusters at station 4 (before the Cartouche Court)",
      action: zh ? "当油剩 1 滴时，station 4 出现一行「你离验讫只差 3 站」" : "When one oil-drop remains, station 4 surfaces “three stations to the seal”",
      confidence: 0.63,
    },
    {
      key: "calendar", priority: "P3",
      title: zh ? "铁证日历未被看见：在 dashboard 顶部加一行「本周活跃 N 天 · 连击 N 天」小语" : "The calendar is invisible: add “active days this week · streak” one-liner to dashboard header",
      evidence: zh ? `日历门店 ${data.features[8].users}/240 — 仅 21 人见过` : `calendar doorway ${data.features[8].users}/240 — 21 visitors ever`,
      action: zh ? "从 calendarData.json 现推；不知道就是 0 也写 0" : "Derived on-render from calendarData.json; zero stays zero",
      confidence: 0.55,
    },
  ];

  if (data.sessionsPerDay.length !== 28) return null;

  return (
    <div className="insight-page">
      {/* ── Admin masthead ─────────────────────────────────────── */}
      <div className="insight-mast">
        <div>
          <p className="insight-kicker">{zh ? "管 理 员 休 息 室" : "THE ADMIN LOUNGE"}</p>
          <h1>{zh ? "洞察舱" : "Insight Deck"} <span className="insight-en">{zh ? "INSIGHT DECK" : "洞察舱"}</span></h1>
          <p className="insight-lead">{zh ? "给 admin / operator 看的仪表盘：谁在用、用什么、卡在哪、下一步该修哪一扇门——所有数字都是合成校准数据，明确标注，永不扮演真话。" : "The board: who shows up, what they touch, where they stall, and which door to fix next — every figure is a labelled calibration cohort, never a real person."}</p>
        </div>
        <div className="insight-badges">
          <span className="insight-pill insight-pill-admin"><ProductIcon name="shield" size={13} /> {zh ? "admin / operator" : "admin / operator"}</span>
          <span className="insight-pill insight-pill-sim">{zh ? "合成校准数据 · synthetic cohort" : "SYNTHETIC COHORT"}</span>
        </div>
      </div>

      {/* ── KPI strip ──────────────────────────────────────────── */}
      <div className="insight-kpis">
        <div className="insight-kpi"><p className="insight-kpi-value">{data.population}</p><p className="insight-kpi-label">{zh ? "合成成员数" : "synthetic members"}</p></div>
        <div className="insight-kpi"><p className="insight-kpi-value">{pct(data.tourCompletionRate)}</p><p className="insight-kpi-label">{zh ? "巡览通关率" : "tour completion"}</p></div>
        <div className="insight-kpi"><p className="insight-kpi-value">{pct(data.drillPassRate)}</p><p className="insight-kpi-label">{zh ? "快问首次通过" : "drill first-pass"}</p></div>
        <div className="insight-kpi"><p className="insight-kpi-value">{data.medianDwellMin}m</p><p className="insight-kpi-label">{zh ? "中位停留时长" : "median dwell"}</p></div>
        <div className="insight-kpi"><p className="insight-kpi-value">{data.dailySlope >= 0 ? "+" : ""}{data.dailySlope.toFixed(2)}</p><p className="insight-kpi-label">{zh ? "14 日斜率 (会话/天)" : "14-day slope (sessions/day)"}</p></div>
        <div className="insight-kpi"><p className="insight-kpi-value">{data.r2.toFixed(2)}</p><p className="insight-kpi-label">{zh ? "回归 R²· 越近 1 越可信" : "regression R²"}</p></div>
      </div>

      <div className="insight-grid">
        {/* ── Funnel ─────────────────────────────────────────── */}
        <section className="insight-panel insight-funnel-panel">
          <h2>{zh ? "漏斗：从进来到印章" : "The funnel, door to seal"}</h2>
          <div className="insight-funnel">
            {data.funnel.map((stage, i) => (
              <div key={stage.key} className="insight-funnel-row">
                <span className="insight-funnel-label">{pick(stage.label, locale)}</span>
                <div className="insight-funnel-bar">
                  <div className="insight-funnel-fill" style={{ width: `${(stage.count / funnelMax) * 100}%` }} />
                  <span className="insight-funnel-count">{stage.count}<em>{Math.round((stage.count / funnelMax) * 100)}%</em></span>
                </div>
                {i > 0 && (
                  <span className="insight-funnel-drop">−{data.funnel[i - 1].count - stage.count}</span>
                )}
              </div>
            ))}
          </div>
        </section>

        {/* ── Trend + forecast ─────────────────────────────────── */}
        <section className="insight-panel insight-trend-panel">
          <div className="insight-trend-head">
            <h2>{zh ? "近 28 天会话数 · 7 天预测" : "28 days in, 7 days predicted"}</h2>
            <div className="insight-trend-stats">
              <span>{zh ? "斜率" : "slope"} <strong>{data.dailySlope >= 0 ? "+" : ""}{data.dailySlope.toFixed(2)}/{zh ? "日" : "d"}</strong></span>
              <span>R² <strong>{data.r2.toFixed(2)}</strong></span>
            </div>
          </div>
          <svg viewBox={`0 0 ${sparkW} ${sparkH}`} className="insight-spark" role="img" aria-label={zh ? "近 28 天每日会话数与 7 天预测" : "Sessions per day, past 28 days plus 7-day forecast"}>
            <line x1={sparkPadX} y1={sparkH - sparkPadY} x2={sparkW - sparkPadX} y2={sparkH - sparkPadY} className="insight-spark-axis" />
            <path d={sparkPath} fill="none" className="insight-spark-line" strokeWidth="2" />
            <path d={predicted} fill="none" className="insight-spark-forecast" strokeWidth="2" strokeDasharray="5 5" />
          </svg>
          <p className="insight-spark-note">{zh ? `预测：${data.predictedNext7.join(", ")} 会话 / 日 —— 只读 · 不自动执行。` : `Forecast: ${data.predictedNext7.join(", ")} sessions / day — read-only, nothing self-executes.`}</p>
        </section>

        {/* ── Feature adoption ────────────────────────────────── */}
        <section className="insight-panel insight-features-panel">
          <h2>{zh ? "特性采纳榜（合成）" : "Feature adoption (synthetic)"}</h2>
          <ol className="insight-bars">
            {data.features.map((f) => (
              <li key={f.key} className="insight-bar-row">
                <span className="insight-bar-label">{pick(f.label, locale)}</span>
                <div className="insight-bar-track"><div className="insight-bar-fill" style={{ width: `${(f.users / maxFeature) * 100}%` }} /></div>
                <span className="insight-bar-count">{f.users}</span>
              </li>
            ))}
          </ol>
        </section>

        {/* ── Local browser's own real telemetry ───────────────── */}
        <section className="insight-panel insight-local-panel">
          <h2>{zh ? "这个浏览器（你）¥ —— 真实轨迹" : "THIS BROWSER (you) — real trace"}</h2>
          {local.visits === 0 ? (
            <p className="insight-local-empty">{zh ? "本机 localStorage 没有记录到路由访问——这不等于没走过（例如无痕模式）。" : "No route visits recorded in this browser yet — silence here is unknown, not proof of zero."}</p>
          ) : (
            <>
              <p className="insight-local-count">{local.visits} <span>{zh ? "次路由访问（仅本机·真实）" : "route visits (this browser only, real)"}</span></p>
              <ol className="insight-local-list">
                {local.routes.map((r) => (
                  <li key={r.path}><code>{r.path}</code><span className="muted">{r.at.slice(0, 16).replace("T", " ")}</span></li>
                ))}
              </ol>
            </>
          )}
        </section>

        {/* ── This browser's raw tap/dwell climate ───────────── */}
        <section className="insight-panel insight-heat-panel">
          <div className="insight-heat-head">
            <div>
              <h2>{zh ? "本机真实点按 · 气候图（specproof_heat_v1）" : "THIS BROWSER'S RAW TAPS · the climate chart"}</h2>
              <p className="insight-heat-sub">{zh ? "这个浏览器亲手敲出的真实轨迹——路由视图、停留毫秒数、2 秒内连敲 3 次的暴怒点击。只读 localStorage，不联网、不上报、不代他人代写。" : "Trace struck by this very browser — route views, dwell in milliseconds, rage-taps (3 taps inside 2s). Read-only localStorage; never uploaded, never written on anyone's behalf."}</p>
            </div>
            <button
              type="button"
              className="insight-heat-clear"
              onClick={() => {
                clearHeat();
                setHeatVersion((v) => v + 1);
              }}
              disabled={heatSummary.events === 0}
            >
              {zh ? "清空本机轨迹" : "Clear this browser's trace"}
            </button>
          </div>
          {heatSummary.events === 0 ? (
            <p className="insight-local-empty">{zh ? "还没有任何敲击记录——这不是零，是沉默。去 #/tour 走一走，再回到本页。" : "No taps recorded yet — silence, not zero. Walk through #/tour once, then come back."}</p>
          ) : (
            <>
              <div className="insight-heat-stats">
                <div><p>{heatSummary.events}</p><span>{zh ? "事件数" : "events"}</span></div>
                <div><p>{heatSummary.distinctRoutes}</p><span>{zh ? "不同页面" : "distinct routes"}</span></div>
                <div><p>{heatSummary.views}</p><span>{zh ? "路由视图" : "views"}</span></div>
                <div><p>{heatSummary.medianDwellSec}s</p><span>{zh ? "中位停留" : "median dwell"}</span></div>
                <div><p>{heatSummary.quickBounces}</p><span>{zh ? "秒退次数 (<4s)" : "quick bounces (<4s)"}</span></div>
                <div><p>{heatSummary.spanMin}m</p><span>{zh ? "轨迹跨度" : "span"}</span></div>
              </div>
              <div className="insight-heat-cols">
                <div>
                  <h3>{zh ? "常驻页面（真实）" : "Resident routes (real)"}</h3>
                  <table className="insight-heat-table">
                    <thead><tr><th>{zh ? "页面" : "route"}</th><th>{zh ? "次数" : "views"}</th><th>{zh ? "停留" : "dwell"}</th></tr></thead>
                    <tbody>
                      {heatSummary.routes.map((r) => (
                        <tr key={r.path}><td><code>{r.path}</code></td><td>{r.views}</td><td>{Math.round(r.dwellMs / 1000)}s</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div>
                  <h3>{zh ? "暴怒点按（真实）" : "Rage taps (real)"}</h3>
                  {heatSummary.rageTotal === 0 ? (
                    <p className="insight-local-empty">{zh ? "零暴怒——要么顺利，要么耐心。" : "Zero rage — either lucky or patient."}</p>
                  ) : (
                    <ol className="insight-heat-rage">
                      {heatSummary.rageTop.map((r) => (
                        <li key={r.target}><code>{r.target}</code><span>×{r.count}</span></li>
                      ))}
                    </ol>
                  )}
                </div>
              </div>
            </>
          )}
          <p className="insight-heat-foot">{zh ? "事件仅存本机、随缓存清理消失；本块永不上传——即便 D1 于 2026-11-16 签落（身份未加密实证），本页依然只是这个浏览器的痕迹，不是船队遥测。。" : "Events live only on this device and vanish with your cache; this block never uploads — even with D1 signed 2026-11-16 (identity not crypto-verified), this page is still this browser's trace, not fleet telemetry."}</p>
        </section>

        {/* ── Personas ───────────────────────────────────────── */}
        <section className="insight-panel insight-personas-panel">
          <h2>{zh ? "合成用户型谱（匿名画像 · 6 型）" : "Synthetic personas (anonymous · 6 archetypes)"}</h2>
          <div className="insight-personas">
            {data.personas.map((p) => (
              <div key={p.key} className="insight-persona">
                <div className="insight-persona-head"><strong>{pick(p.label, locale)}</strong><span className="insight-persona-count">{p.count}</span></div>
                <p>{pick(p.demeanor, locale)}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ── Recommendations engine ─────────────────────────── */}
        <section className="insight-panel insight-reco-panel">
          <h2>{zh ? "下一步优化措施 · 由引擎根据上面的数字推出" : "Recommended next moves — derived from the numbers above"}</h2>
          <div className="insight-recos">
            {recommendations.map((r) => (
              <article key={r.key} className="insight-reco">
                <header>
                  <span className={`insight-reco-prio insight-reco-${r.priority.toLowerCase()}`}>{r.priority}</span>
                  <h3>{r.title}</h3>
                </header>
                <p className="insight-reco-evidence"><strong>{zh ? "证据" : "Evidence"} ·</strong> {r.evidence}</p>
                <p className="insight-reco-action"><strong>{zh ? "动作" : "Action"} ·</strong> {r.action}</p>
                <footer>
                  <span className="insight-reco-conf">{zh ? "置信" : "confidence"} <strong>{Math.round(r.confidence * 100)}%</strong></span>
                  <span className="insight-reco-tag">{zh ? "合成校准 · 仅作示范" : "synthetic calibration demo"}</span>
                </footer>
              </article>
            ))}
          </div>
          <p className="insight-reco-footnote">{zh ? "「证据」列全部可以在本页数字中直接复核；如某个数字被删改，对应推荐自动失效。" : "Every “Evidence” figure can be re-derived from this page; if a figure is removed or altered, its recommendation is void."}</p>
        </section>
      </div>

      <p className="insight-honesty">
        <ProductIcon name="shield" size={14} />{" "}
        {zh
          ? "本页的人群面板是确定性合成校准数据（mulberry32(20261115)），不含任何真实用户身份或行为字段；本机真实轨迹只读 localStorage，不联网、不上报。admin/operator 可见并受 RBAC fail-closed 约束——不设「123 密钥」这类全员通行证。真·船队级遥测的接入方式见 docs/operations/OBSERVABILITY.md；上线前必须由产品与隐私评审签字。"
          : "The cohort on this page is a deterministic synthetic calibration (mulberry32(20261115)) — no real user identity or behaviour fields anywhere. This browser's real trace reads localStorage only — never uploads. Visible to admin/operator under the same fail-closed RBAC; there is deliberately no “123 key” golden ticket. Real fleet telemetry wiring is documented in docs/operations/OBSERVABILITY.md and must pass product/privacy review before it ever ships."}
      </p>
    </div>
  );
}
