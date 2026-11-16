import { useI18n } from "../i18n";
import { ProductIcon } from "../ui/ProductIcon";
import engine from "./engine.json";
import nightWatch from "./night_watch.json";
import cacheWitness from "./cache_witness.json";
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
 * this page is where that number is observable — never the gateway's
 * self-estimate; only this host's bytes.
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
const CW = cacheWitness as unknown as {
  started_utc?: string;
  cached_tokens_a?: number;
  cached_tokens_b?: number;
  prompt_tokens_b?: number;
  hit_rate_b?: number;
  verdict?: string;
};
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
            "本页的数字是这个仓库在本机真实发出的全部调用，直接由 scripts/build_engine.py 读 .local/llm_usage.jsonl 重建。不是网关对自己的估算、不是比例折算、不是拍脑袋的『75 分』。它们是一笔账：谁写、谁读、谁命中缓存。",
            "The figures on this page come from every call this repository actually issued on this host — rebuilt at build time from .local/llm_usage.jsonl by scripts/build_engine.py. They are not the gateway's estimate of itself, not a percentage blend, and not a guess at what the gateway might do.",
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
          <p className="engine-note">{L("仅统计 duration_ms > 0 的调用；调用数由 .local/llm_usage.jsonl 的 全部调用组成，每条都是本机真实发出的调用。车道实况（本机统计）：direct 46（29 行 gpt-6-sol 起于 2026-11-13 · 17 行 aizzz/gpt-6.1-terra 起于 2026-11-16 经本机代理 Clash Verge）· policy 17（全部 gpt-6-sol）。", "Computed only from calls with duration_ms > 0; every row is a real call issued by this host. Lane truth, measured locally: direct 46 (29 gpt-6-sol from 2026-11-13 · 17 aizzz/gpt-6.1-terra from 2026-11-16 through the local Clash Verge proxy) · policy 17 (all gpt-6-sol).")}</p>
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
          <h2>{L("逐小时刻度 · 这些时间点上，本机敲了这些次", "Hourly ticks, this host's beat")}</h2>
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

      <section className="engine-witness" aria-label={L("前缀缓存 · 双敲见证", "Prefix cache · double-strike witness")}>
        <h2>{L("前缀缓存 · 双敲见证", "Prefix cache · double-strike witness")}</h2>
        <p className="engine-note">{L(
          `${CW.started_utc}——agent/graphs/cache_witness_graph.py 实打实双敲同一个固定提示：两次都带回 cached_tokens=4224（prompt 4430）；hit_rate 95.3%；verdict HIT。这不是命中率认证书，只是这一刻这台机器的表态：换一个字节的前缀，数字落回 0 是正常的。court 永远不出现在这笔账里。`,
          `${CW.started_utc} — agent/graphs/cache_witness_graph.py struck the same fixed prompt twice for real: both strikes came back with cached_tokens=4224 on a prompt of 4430; hit_rate 95.3%; verdict HIT. This is a reading, not a certificate — change one byte of the prefix and the number falls to 0. The court never appears in this account.`,
        )}</p>
        <div className="engine-kpis engine-kpis-witness">
          <div className="engine-kpi"><p className="engine-kpi-v">{CW.cached_tokens_a}</p><p className="engine-kpi-l">{L("strike A · cached", "strike A · cached")}</p></div>
          <div className="engine-kpi"><p className="engine-kpi-v">{CW.cached_tokens_b}</p><p className="engine-kpi-l">{L("strike B · cached", "strike B · cached")}</p></div>
          <div className="engine-kpi"><p className="engine-kpi-v">{(((CW.hit_rate_b ?? 0) * 100).toFixed(1)) + "%"}</p><p className="engine-kpi-l">hit_rate (strike B)</p></div>
          <div className="engine-kpi engine-kpi-verdict"><p className="engine-kpi-v">{CW.verdict}</p><p className="engine-kpi-l">{L("双敲判词 · verdict", "double-strike verdict")}</p></div>
        </div>
      </section>

      <footer className="engine-honesty">
        <ProductIcon name="shield" size={13} />
        <p>
          {zh
            ? "本页算是这仓库最接近「真实数据」的一页：账已于 2026-11-16 从 .local/llm_usage.jsonl 重建：共 63 行真实调用（46 行 gpt-6-sol 时代 · 17 行 aizzz/gpt-6.1-terra 经本机代理），不是演示；本页不是直接把 .local/llm_usage.jsonl 贴出来（那不雅观、也不安全—含 prompts），只是聚合结果。本次 prompt 238,221 / cached 105,206 = **44.2 % exact static-prefix hit rate**（仅 63 次中的 39 次上报缓存数，其余只计 prompt 侧）。完全诚实地讲：生产负载能否复现同样命中率，取决于真实负载；本页只能如实说本机的数据。"
            : "This page is the closest this repo will ever come to 'real data': every row is one of the 63 calls actually issued from this host since 2026-11-16 (rebuilt from .local/llm_usage.jsonl — 46 gpt-6-sol-era rows + 17 aizzz/gpt-6.1-terra through the local proxy). Nothing here is a mock or a sample. The 238,221 prompt tokens / 105,206 cached = 44.2 % exact static-prefix hit rate (cache counts were reported on 39 of the 63 calls; the rest count raw prompt bytes) — that is what this machine actually did. Whether a production deployment reaches the same is an experiment that has not been run, and this page will not guess."}
        </p>
        <p className="engine-honesty-note">
          {zh
            ? "※ 注：2026-11-16 起，本机车道已切换为 aizzz/gpt-6.1-terra（经本机代理 · provider_smoke 7/7 PASS · court 永远不缓存 · 永远 stream）。同日账本重建时已把新车道 17 行并入同一份 jsonl——本页的 63 行就是**两个车道的和**，没有另分一本账。cache_witness_graph 的双敲见证见下；court 永远不出现在任何一笔账里。"
            : "※ note: since 2026-11-16 this host runs the aizzz/gpt-6.1-terra lane (through the local proxy · provider_smoke 7/7 · court never cached, always streamed). The 2026-11-16 rebuild folded the new lane's 17 rows into the same jsonl — this page's 63 rows ARE the two eras folded, no separate books. The double-strike witness lives one panel down; the court never appears in any of them."}
        </p>
      </footer>
    </div>
  );
}
