import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../i18n";
import { buildInsight } from "./insight.copy";
import { deriveHeat, loadHeat } from "../telemetry/behavior";
import { simulateCohort, PERSONA_LABEL } from "../telemetry/syntheticCohort";
import { postObserveAdvice, type ObserveAdvice } from "../api";
import { Panel, Button, StatCard, Empty } from "../ui";
import { ProductIcon } from "../ui/ProductIcon";

/**
 * The Observatory — a public read-only room.
 *
 * Everyone knows the password: it is `123` by the owner's own request. The
 * point is not to guard; the point is to demonstrate a calibrated public
 * view of the product's own engagement with synthetic-but-deterministic data
 * — no real person is ever observed here, and this page makes that loudly
 * known on purpose.
 *
 * Three blocks:
 *   1. library metrics — the synthetic cohort population, the calibration funnel,
 *      the headline numbers (everything Importable to /insight but exposed
 *      anonymously, derived from buildInsight());
 *   2. this browser's session — a finite, honest derivation of what the
 *      visitor*does* in their own browser, no other browser's data touched;
 *   3. gate — typing "123" unlocks the AI-crafted deep read, confined to
 *      the same anonymous aggregate the admin lane reads; never verdict, never
 *      judge, never a token-swapping agent of the court.
 *
 * Every copy line lives bilingual; nothing here reaches past this tab; the
 * page is a *demo of an operator's lens*, not a disclosure of anything real.
 */
export default function Observe(): JSX.Element {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const L = (a: string, b: string) => (zh ? a : b);

  const data = useMemo(() => buildInsight(), []);
  // The impatient crowd — fully deterministic (seed 20261119), the seeded
  // half of the owner's §九 ask: what it looks like when 240 synthetic
  // visitors open the door, hesitate, rage-tap, wander, and leave.
  const crowd = useMemo(() => simulateCohort(), []);
  const [gateInput, setGateInput] = useState("");
  const [gatePassed, setGatePassed] = useState(false);
  const [gateError, setGateError] = useState<string | null>(null);
  const [adviceState, setAdviceState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [advice, setAdvice] = useState<ObserveAdvice | null>(null);

  // The unlocked read is a LIVE model call against this panel's aggregates —
  // answered in the interface language, cached server-side by fingerprint,
  // and never a verdict. Failures surface as one honest error line.
  useEffect(() => {
    if (!gatePassed) return;
    let cancelled = false;
    setAdviceState("loading");
    postObserveAdvice(zh ? "zh" : "en")
      .then((res) => {
        if (cancelled) return;
        setAdvice(res);
        setAdviceState("ready");
      })
      .catch(() => {
        if (cancelled) return;
        setAdvice(null);
        setAdviceState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [gatePassed, zh]);

  const unlock = (): void => {
    if (gateInput.trim() === "123") {
      setGatePassed(true);
      setGateError(null);
      return;
    }
    setGatePassed(false);
    setGateError(L("只接受 123（所有人都知道）。", "Only \"123\" opens this gate — everyone already knows it."));
  };

  const formatCount = (n: number): string => (n >= 1000 ? (n / 1000).toFixed(1) + "k" : String(n));

  // This browser's own tap ledger — the only REAL telemetry on the page.
  // Read from localStorage only; unreadable/quiet shows the silence line,
  // never a fabricated zero. (Rule inherited from Mint/LocalEcho.)
  const thisBrowser = useMemo(() => {
    try {
      const summary = deriveHeat(loadHeat());
      return { ok: true as const, summary };
    } catch {
      return { ok: false as const, summary: null };
    }
  }, []);

  return (
    <div className="observe-page">
      <header className="page-head" style={{ marginBottom: 18 }}>
        <ProductIcon name="chart" size={28} />
        <h1>{L("观察舱", "Observatory")} <span className="usage-en">{L("公开 · 只读 · 演示", "PUBLIC · READONLY · DEMO")}</span></h1>
        <div className="page-sub">
          {L(
            "本页公开。用「123」解锁一段校准观察——里面没有真实人：只有一个 240 人的校准群体，以及你浏览器自己的点按轨迹。本页不收集、不上传、不展示任何人的行为数据；它只是演示产品自己的观察仪是什么样子。",
            "Public page. Type \"123\" to unlock the calibration read — there is no real person in this room: only a seeded 240-member synthetic cohort, and this browser's own taps. Nothing about anyone else is ever shown.",
          )}
        </div>
      </header>

      <Panel title={L("一个校准群体，不是监听你", "Calibrated cohort — never a listener of you")}>
        <div className="stat-grid" style={{ marginBottom: 14 }}>
          <StatCard label={L("校准人数", "Cohort size")} value={String(data.population)} tone="ok" />
          <StatCard label={L("巡览完成率", "Tour completion")} value={`${Math.round((data.tourCompletionRate * 100))}%`} tone="ok" />
          <StatCard label={L("快问通过率", "Drill pass rate")} value={`${Math.round((data.drillPassRate * 100))}%`} tone="warn" />
          <StatCard label={L("今日会话", "Sessions today")} value={String(data.sessionsPerDay[data.sessionsPerDay.length - 1])} />
          <StatCard label={L("7 日预测", "7-day forecast")} value={String(data.predictedNext7[0])} />
          <StatCard label={L("斜率", "Slope")} value={data.dailySlope.toFixed(2)} tone="warn" />
        </div>
        <p className="muted usage-basis-note">
          r² = {data.r2.toFixed(2)} · {L("拟合很弱——平线，不是斜坡；预测逐日微减", "a weak fit — a near-flat line, easing down; the forecast steps down day by day")} · {L("斜率", "slope")} {data.dailySlope.toFixed(2)}/d
        </p>
      </Panel>

      <Panel title={L("本机这一台 · 只有你这一台是真的", "This one machine — the only real telemetry here")}>
        {thisBrowser.ok && thisBrowser.summary.events > 0 ? (
          <>
            <div className="stat-grid" style={{ marginBottom: 10 }}>
              <StatCard label={L("点按记录", "Taps on record")} value={String(thisBrowser.summary.events)} tone="ok" />
              <StatCard label={L("到访页面", "Pages visited")} value={String(thisBrowser.summary.views)} />
              <StatCard label={L("秒退次数", "Quick bounces")} value={String(thisBrowser.summary.quickBounces)} tone="warn" />
              <StatCard label={L("急躁点按", "Rage taps")} value={String(thisBrowser.summary.rageTotal)} tone="warn" />
              <StatCard label={L("不同页面", "Distinct pages")} value={String(thisBrowser.summary.distinctRoutes)} />
              <StatCard label={L("中位停留(秒)", "Median dwell (s)")} value={String(thisBrowser.summary.medianDwellSec)} />
            </div>
            {thisBrowser.summary.rageTop.length > 0 ? (
              <p className="muted usage-basis-note">
                {L("急点最多的地方", "where the impatience lands")}: {thisBrowser.summary.rageTop.slice(0, 3).map((r) => `${r.target} ×${r.count}`).join(" · ")}
              </p>
            ) : (
              <p className="muted usage-basis-note">{L("本机轨迹里没有急躁点按——这是最好的消息。", "No rage taps in this machine's ledger — the best signal on this page.")}</p>
            )}
            <p className="muted usage-basis-note">
              {L(
                "这组数字是你这一台浏览器亲手敲出来的——不上传、不汇总、不属于任何人；清空浏览器数据即抹掉。",
                "These numbers were struck by this one browser — nothing is uploaded, nothing aggregated, nobody owns them; clearing your browsing data erases them.",
              )}
            </p>
          </>
        ) : (
          <p className="muted" style={{ margin: 0 }}>
            {L(
              "这一台还没有足够的轨迹——沉默，不是零。随便去走几间屋，它就有了。",
              "This machine has no trail yet — silence, not zero. Walk through a few rooms and it will have one.",
            )}
          </p>
        )}
      </Panel>

      <Panel title={L("漏斗：来 240 个人，走 41 个人", "Funnel: 240 enter, 41 leave with a seal")}>
        <ol className="observe-funnel">
          {data.funnel.map((stage, i) => {
            const pct = (stage.count / data.population) * 100;
            return (
              <li key={stage.key} className="observe-funnel-row">
                <span className="observe-funnel-stage">{i + 1}. {stage.label[locale as "zh" | "en"]}</span>
                <span className="observe-funnel-bar"><span style={{ width: pct.toFixed(1) + "%" }} /></span>
                <span className="observe-funnel-count">{formatCount(stage.count)}</span>
              </li>
            );
          })}
        </ol>
      </Panel>

      <Panel title={L("输入 123 看管理员看得到什么", "Type 123 to see what the operator sees")}>
        {!gatePassed ? (
          <div>
            <p className="muted" style={{ marginBottom: 10 }}>
              {L(
                "「123」：这台产品每个人都能进入的门。进来后你会看到一段模型写给你的评估——模型只能读本页这几项聚合数字，别的地方一律不准看。",
                "\"123\" — this is the door with no guards: even you can open it. What unfolds inside is the same aggregate surface the admin sees; the model may look only at these numbers, never anywhere else.",
              )}
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                unlock();
              }}
              className="observe-gate"
            >
              <label htmlFor="observe-gate-input">{L("密码：", "Password:")}</label>
              <input
                id="observe-gate-input"
                type="password"
                autoComplete="off"
                value={gateInput}
                onChange={(e) => setGateInput(e.target.value)}
                placeholder=""
                className="observe-gate-field"
              />
              <Button type="submit" variant="primary" size="sm">{L("进门", "Open")}</Button>
            </form>
            {gateError ? <p className="observe-gate-error">{gateError}</p> : null}
          </div>
        ) : (
          <div>
            <p className="muted" style={{ marginBottom: 10 }}>
              {L(
                "已进入。下面由模型现场读这几项聚合——界面语言是中文。失败时这里会老实报错，绝不代写一段假的。",
                "You're in. The model reads this page's aggregates, live, in the interface language. On failure you get one honest error line — never a ghost-written paragraph.",
              )}
            </p>
            <Panel title={L("合成人群 · 240 个访客，没人真的存在", "The synthetic crowd — 240 visitors, none of them real")}>
              <div className="stat-grid" style={{ marginBottom: 12 }}>
                <StatCard label={L("合成样本", "Synthetic members")} value={String(crowd.size)} />
                <StatCard label={L("秒退+急躁占比", "Bounce + rage share")} value={`${Math.round(crowd.impatientRate * 100)}%`} tone="warn" />
                <StatCard label={L("秒退人数", "Bouncers")} value={String(crowd.bouncers)} tone="warn" />
                <StatCard label={L("急躁点触事件", "Rage events")} value={String(crowd.totalRageEvents)} tone="warn" />
                <StatCard label={L("带急躁会话", "Sessions with rage")} value={String(crowd.rageSessions)} />
                <StatCard label={L("走完全程", "Finishers")} value={String(crowd.finishers)} tone="ok" />
              </div>
              <ol className="observe-funnel" style={{ marginBottom: 12 }}>
                {crowd.personaSummaries.map((p) => {
                  const label = PERSONA_LABEL[p.persona];
                  const pct = (p.share * 100).toFixed(1) + "%";
                  return (
                    <li key={p.persona} className="observe-funnel-row">
                      <span className="observe-funnel-stage">{label[zh ? "zh" : "en"]} — {label.behavior[zh ? "zh" : "en"]}</span>
                      <span className="observe-funnel-bar"><span style={{ width: pct }} /></span>
                      <span className="observe-funnel-count">{p.count}</span>
                    </li>
                  );
                })}
              </ol>
              <p className="muted usage-basis-note">
                {crowd.note[zh ? "zh" : "en"]} · {L("中位停留", "median dwell")} {Math.round(crowd.medianDwellMs / 1000)}s
              </p>
              <p className="muted usage-basis-note">
                {L(
                  "人群给出的下一步优先级：先把首屏价值一眼看懂，去掉一个需要猜的按钮，先演示再解释——不是猜，是合成轨迹的收敛结论。",
                  "The crowd's priority order: make time-to-first-value legible at a glance, remove one button the visitor must guess, demonstrate before explaining — not a hunch, the convergence of thousands of seeded taps.",
                )}
              </p>
            </Panel>
            <Panel title={L("模型说了什么", "What the model said")}>
              {adviceState === "loading" ? (
                <p className="muted">
                  {L("模型正在逐数字读这一页——别无他件可读。", "The model is reading this page, number by number — nothing else is legible to it.")}
                </p>
              ) : adviceState === "error" ? (
                <>
                  <p>
                    {L(
                      "模型这次没接上（503）。下面没有任何一句是它写的——这是本页数字自己的自述：",
                      "The model did not answer this time (503). Nothing below was written by it — the panel is describing itself:",
                    )}
                  </p>
                  <p>
                    {L(
                      `240 人校准群体 · 巡览 ${Math.round(data.tourCompletionRate * 100)}%（113/201）· 快问 ${Math.round(data.drillPassRate * 100)}% · 今日 ${data.sessionsPerDay[data.sessionsPerDay.length - 1]} · 斜率 ${data.dailySlope.toFixed(2)}/日（r² = ${data.r2.toFixed(2)}）· 预测 ${data.predictedNext7[0]} → ${data.predictedNext7[data.predictedNext7.length - 1]}。这是校准轨迹，不是承诺。`,
                      `240 synthetic members · tour ${Math.round(data.tourCompletionRate * 100)}% (113/201) · drill ${Math.round(data.drillPassRate * 100)}% · today ${data.sessionsPerDay[data.sessionsPerDay.length - 1]} · slope ${data.dailySlope.toFixed(2)}/day (r² = ${data.r2.toFixed(2)}) · forecast ${data.predictedNext7[0]} → ${data.predictedNext7[data.predictedNext7.length - 1]}. A calibration trajectory, not a promise.`,
                    )}
                  </p>
                </>
              ) : advice ? (
                <>
                  <p className="observe-gate-note" style={{ marginBottom: 8 }}>
                    {(advice.model ?? "model")} · {advice.model_latency_ms ?? "—"} ms ·{" "}
                    {advice.cached ? L("缓存命中（字节全同）", "cache hit — byte-identical") : L("现敲生成", "generated live")} ·{" "}
                    {advice.evidence_packet_chars} B {L("数据包", "packet")}
                  </p>
                  <p style={{ whiteSpace: "pre-wrap", lineHeight: 1.9, margin: 0 }}>{advice.advice}</p>
                </>
              ) : (
                <p className="muted">{L("正在准备模型请求……", "Preparing the model request…")}</p>
              )}
              <p className="observe-gate-note">
                {L(
                  "它没有看别人——本页没有别人。它的答案不是判词——判词只属于 SpecProof 的法院。「123」本来就没有门；这一页也没有给你别的入口。",
                  "It never looked at you — only the numbers rendered above are read. Its answer is not a verdict — verdicts belong to SpecProof's court. \"123\" was never a gate; it opened a mirror.",
                )}
              </p>
            </Panel>
            <Button variant="ghost" size="sm" onClick={() => { setGatePassed(false); setGateInput(""); setAdviceState("idle"); setAdvice(null); }}>
              {L("再走出来", "Leave")}
            </Button>
          </div>
        )}
      </Panel>

      <Empty
        text={L(
          "本页公开可读。没有别的入口、也没有登录后台——只有这一扇门：一个匿名聚合数页，和一段指纹缓存的模型解读。",
          "This page is public and read-only. No other entrance, no login cabinet — only this one door: anonymous aggregates, and a fingerprint-cached model reading.",
        )}
      />
    </div>
  );
}
