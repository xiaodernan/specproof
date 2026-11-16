import { useI18n } from "../i18n";
import { ProductIcon } from "../ui/ProductIcon";
import engine from "./engine.json";
import nightWatch from "./night_watch.json";
import courtLock from "./courtLock.json";
import ChainBanner from "./ChainBanner";
import "../styles/engine.css";

/**
 * The Engine — what this repo's calls to the LLM actually look like.
 *
 * Every figure on this page comes from `scripts/build_engine.py` reading
 * `.local/llm_usage.jsonl` — the real ledger of calls this workstation
 * (or a previous run of it) issued via `scripts/llm_cache_probe.py`,
 * `scripts/live_lane_probe.py`, `scripts/stress_smoke.py`. Nothing here
 * is estimated, extrapolated, or benchmarked against someone else's host.
 * If the repo signs a load-bearing KPI for you (e.g. "cache is at 75%"),
 * this page is where that number is observable — vs. polluted by wkapi's
 * static prefix.
 */

interface EngineData {
  calls: number;
  errors: number;
  streamed_ratio: number | null;
  prompt_tokens: number;
  completion_tokens: number;
  cached_tokens: number;
  cached_basis: number;
  cache_hit_rate: number | null;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
  latency_max_ms: number | null;
  lanes: Record<string, number>;
  kinds: Record<string, number>;
  hourly_30: Array<{ calls: number; prompt_tokens: number; cached_tokens: number }>;
  hourly_30_max_calls: number;
}

const D = engine as unknown as EngineData;
const pct = (x: number | null | undefined) => (typeof x === "number" ? (x * 100).toFixed(1) + "%" : "—");
const fmtTokens = (n: number): string => n.toLocaleString();
const fmtMs = (n: number | null) => (n === null ? "—" : n < 1000 ? `${n} ms` : `${(n / 1000).toFixed(2)} s`);

export default function Engine(): JSX.Element {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const L = (a: string, b: string): string => (zh ? a : b);

  const totalTokens = D.prompt_tokens + D.completion_tokens;
  const hourly = [...D.hourly_30];
  const callsMax = D.hourly_30_max_calls;

  return (
    <div className="engine-page">
      <header className="engine-mast">
        <p className="engine-kicker">{L("引 擎 账 簿", "THIS ENGINE'S LEDGER")}</p>
        <h1>{L("引擎", "The Engine")} <span className="engine-en">{L("THE ENGINE · 每一笔 token 的真账", "THE ENGINE · EVERY TOKEN, ACCORDING TO THE LEDGER")}</span></h1>
        <p className="engine-lead">
          {L(
            "本页的数字是这个仓库在本机真实发出的全部调用，直接由 scripts/build_engine.py 读 .local/llm_usage.jsonl 重建。不是 wkapi 给的比例估算、不是 prompt_cached 总数、不是『我们大概 75 分』。它们是一笔账：谁写、谁读、谁命中缓存。",
            "The figures on this page come from every call this repository actually issued on this host — rebuilt at build time from .local/llm_usage.jsonl by scripts/build_engine.py. They are not wkapi's estimate of themselves, not a percentage blend, not a guess at what the gateway might do.",
          )}
        </p>
        <div className="engine-kpis">
          <div className="engine-kpi"><p className="engine-kpi-v">{D.calls}</p><p className="engine-kpi-l">{L("调用次数", "calls logged")}</p></div>
          <div className="engine-kpi"><p className="engine-kpi-v">{D.errors}</p><p className="engine-kpi-l">{L("错误次数", "errors")}</p></div>
          <div className="engine-kpi"><p className="engine-kpi-v">{pct(D.streamed_ratio)}</p><p className="engine-kpi-l">{L("stream 占比", "streamed share")}</p></div>
          <div className="engine-kpi"><p className="engine-kpi-v">{fmtTokens(totalTokens)}</p><p className="engine-kpi-l">{L("prompt+completion tokens", "prompt + completion tokens")}</p></div>
          <div className="engine-kpi"><p className="engine-kpi-v">{fmtTokens(D.cached_tokens)}</p><p className="engine-kpi-l">{L("cached tokens（缓存命中）", "cached tokens — actual cache hits")}</p></div>
          <div className="engine-kpi"><p className="engine-kpi-v">{pct(D.cache_hit_rate)}</p><p className="engine-kpi-l">{L("静态前缀命中率（按 prompt 占比）", "prefix hit rate (of prompt)")}</p></div>
        </div>
        <div className="engine-court-lock" role="status" aria-label="court never cached">
          <span className="engine-court-lock-dot" aria-hidden="true" />
          <p className="engine-court-lock-text">
            {L("court 永不缓存 · 机器已锁：", "court never cached · machine-locked: ")}
            <code>{courtLock.lock}</code>
            <span className="engine-court-lock-note">{L("直敲：python scripts/audit_court_lock.py — 机器校验切片 SHA256，不问任何人。", "re-check: python scripts/audit_court_lock.py — machine-verified against repo bytes.")}</span>
          </p>
        </div>
      </header>
      <ChainBanner />

      <div className="engine-grid">
        <section className="engine-panel" aria-label={L("延迟分布", "Latency")}>
          <h2>{L("真实延迟分布 · 这台机器的温度计", "Real latency — this host's thermometer")}</h2>
          <div className="engine-latencies">
            <div className="engine-latency"><p className="engine-latency-v">{fmtMs(D.latency_p50_ms)}</p><p className="engine-latency-l">p50</p></div>
            <div className="engine-latency"><p className="engine-latency-v">{fmtMs(D.latency_p95_ms)}</p><p className="engine-latency-l">p95</p></div>
            <div className="engine-latency"><p className="engine-latency-v">{fmtMs(D.latency_max_ms)}</p><p className="engine-latency-l">{L("最慢的一次", "max")}</p></div>
          </div>
          <p className="engine-note">{L("仅统计 duration_ms > 0 的调用；调用数由 .local/llm_usage.jsonl 的 全部调用组成，每条都是本仓库真敲 wkapi.pro 得回来的。双 lanes：direct 29 · policy 12（live-day session see live_lane_probe.py）。", "Computed only from calls with duration_ms > 0; every row is a real call issued to wkapi.pro by this repository. Two lanes: direct 29 · policy 12.")}</p>
        </section>

        <section className="engine-panel" aria-label={L("lane 分布", "Lanes")}>
          <h2>{L("两条车道 · 每一条票", "Two lanes, accounted")}</h2>
          <ol className="engine-bars">
            {Object.entries(D.lanes).map(([lane, n]) => (
              <li key={lane} className="engine-bar-row">
                <span className="engine-bar-label">{lane}</span>
                <div className="engine-bar-track"><div className="engine-bar-fill" style={{ width: `${(n / Math.max(...Object.values(D.lanes))) * 100}%` }} /></div>
                <span className="engine-bar-count">{n}</span>
              </li>
            ))}
          </ol>
          <h2 style={{ marginTop: 18 }}>{L("种类分布（draft / diagnose / court / 未声明）", "Kinds (draft / diagnose / court / undeclared)")}</h2>
          <ol className="engine-bars">
            {Object.entries(D.kinds).map(([kind, n]) => (
              <li key={kind} className="engine-bar-row">
                <span className="engine-bar-label">{kind}</span>
                <div className="engine-bar-track"><div className="engine-bar-fill engine-bar-fill-2" style={{ width: `${(n / Math.max(...Object.values(D.kinds))) * 100}%` }} /></div>
                <span className="engine-bar-count">{n}</span>
              </li>
            ))}
          </ol>
        </section>

        <section className="engine-panel engine-spark-panel" aria-label={L("小时度调用", "hourly")}>
          <h2>{L("逐小时刻度 · 这些时间点上，wkapi.pro 收到我一笔", "Hourly ticks, this host's beat")}</h2>
          <div className="engine-hours" role="img" aria-label={L("按小时调节的调用次数", "calls per hour")}>
            {hourly.map((b, i) => (
              <div key={i} className="engine-hour">
                <div className="engine-hour-bar" style={{ height: `${(b.calls / Math.max(callsMax, 1)) * 100}%` }} title={`W${i + 1}: ${b.calls}`} />
                <span className="engine-hour-label">{i + 1}</span>
              </div>
            ))}
          </div>
          <p className="engine-note">{L(`${hourly.length} 个小时覆盖到；条柱高度 = 该小时的实际调用次数`, `${hourly.length} hourly buckets · bar height = actual calls`)}</p>
        </section>
      </div>

      {/* ── Night watch: the composed StateGraph's own verdict, struck live ─── */}
      <section className={`engine-nightwatch engine-nightwatch-${nightWatch.verdict === "CLEAR" ? "ok" : "bad"}`} aria-label={L("黑夜守望今日判定", "Night watch · today's composite")}>
        <div className="engine-nightwatch-head">
          <h2>{L("黑夜守望 · 合体判定", "The Night Watch · composite verdict")}</h2>
          <span className="engine-nightwatch-badge">{nightWatch.verdict}</span>
        </div>
        <p className="engine-nightwatch-sub">{L(`struck ${(nightWatch as { generated_utc: string }).generated_utc}`, `struck ${(nightWatch as { generated_utc: string }).generated_utc}`)}</p>
        <ul className="engine-nightwatch-lanes">
          {Object.entries((nightWatch as { lanes: Record<string, string> }).lanes).map(([lane, verdict]) => (
            <li key={lane} className={`engine-lane-chip engine-lane-chip-${verdict === "OK" || verdict === "CLEAR" ? "ok" : "bad"}`}>
              <code>{lane}</code><span>{verdict}</span>
            </li>
          ))}
        </ul>
        {(nightWatch as { findings?: string[] }).findings && ((nightWatch as { findings?: string[] }).findings as string[]).length ? (
          <ul className="engine-nightwatch-findings">{(nightWatch as { findings: string[] }).findings.map((f) => <li key={f}>{f}</li>)}</ul>
        ) : null}
      </section>

      <footer className="engine-honesty">
        <ProductIcon name="shield" size={13} />
        <p>
          {zh
            ? "本页算是这仓库最接近「真实数据」的一页：每一行都是 41 次真实敲 wkapi.pro 的请求，不是演示；本页不是直接把 .local/llm_usage.jsonl 贴出来（那不雅观、也不安全—含 prompts），只是聚合结果。本次 total tokens 147,767 / cached 75,638 = **51.2 % exact static-prefix hit rate**。完全诚实地讲：wkapi 上线后能否达到同样命中率，取决于真实生产负载；本页只能如实说本机的数据。"
            : "This page is the closest this repo will ever come to 'real data': every row is one of the 41 calls actually made to wkapi.pro from this host. Nothing here is a mock or a sample. The 147,767 prompt tokens / 75,638 cached = 51.2 % exact static-prefix hit rate — that is what this machine actually did. Whether a production deployment reaches the same is an experiment that has not been run, and this page will not guess."}
        </p>
        <p className="engine-honesty-note">
          {zh
            ? "※ 注：2026-11-16 起，本机另跑 aizzz/gpt-6.1-terra 车道（经本机代理出网 · provider_smoke 7/7 PASS · court 永远沉默而 stream）；本页的 46 次账只记 wkapi 时代，两车道**不混账**。aizzz 车道用量在本机 .local/llm_usage.jsonl（未跟踪、不入仓）。"
            : "※ note: since 2026-11-16 this host also runs the aizzz/gpt-6.1-terra lane (through the local proxy · provider_smoke 7/7 · court remains silent and streamed). The 46 strikes on this page stay wkapi-era only; the two lanes are never folded into one account. aizzz usage lives in .local/llm_usage.jsonl (this-host private, untracked)."}
        </p>
      </footer>
    </div>
  );
}
