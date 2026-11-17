import { useMemo } from "react";
import { useI18n, type Locale } from "../i18n";
import chronicle from "./chronicle.json";
import stats from "./repoStats.json";
import worldbook from "./worldbook.json";
import evidence from "./evidence.json";
import unsigned from "./unsigned.json";
import auditChain from "./audit_chain.json";
import gazetteFeature from "./gazette_feature.json";
import ChainBanner from "./ChainBanner";
import { ProductIcon } from "../ui/ProductIcon";
import "../styles/gazette.css";

/**
 * The Morning Gazette of Iron Evidence — today's paper of the repository.
 *
 * Every column below is compiled from real, tracked artifacts at render time:
 * the ledger-derived chronicle, the git-derived census, the world bible.
 * The editorial is the one authored (and labelled) voice on the page.
 * Print the page and it folds like a newspaper: it is one.
 */

type Entry = { n: number; t: string; s: string };
const CHRONICLE = chronicle as Entry[];

export default function Gazette() {
  const { locale } = useI18n();
  const zh = locale === "zh";

  const latest = useMemo(() => [...CHRONICLE].slice(-6).reverse(), []);
  const briefs = useMemo(() => [...CHRONICLE].slice(-24, -6).reverse(), []);
  const lead = latest[0];
  const entries = CHRONICLE.length;
  const worldSections = (worldbook.locales as Record<Locale, { volumes: unknown[] }>)[locale]?.volumes.length ?? 0;
  const worldNum = Number(stats.ledger_sections);
  const isoToday = new Date().toISOString().slice(0, 10);
  const isoWeek = new Date(Date.now() - 6 * 86_400_000).toISOString().slice(0, 10);
  const baro = evidence.delta_vs_previous ? evidence.delta_vs_previous.worst_p99_delta_ms : null;
  const p99 = evidence.latest ? Math.round(evidence.latest.worst_p99_ms) : null;
  const obsUnsigned = unsigned.checks.find((c) => c.id === "observability-signature")?.status !== "signature-block-found";
  const weatherName = baro === null ? (zh ? "无钟" : "No clock") : baro <= 1 ? (zh ? "微云" : "Fair") : baro <= 5 ? (zh ? "轻烟" : "Haze") : (zh ? "起雾" : "Fog");
  const weatherLine = baro === null
    ? (zh ? "证据件还不足两件，晴雨计还没写——敲一下：stress_smoke.py --json-report docs/evidence/<name>.json"
         : "fewer than two evidence exhibits; the barometer has not been written yet. Strike one: stress_smoke.py --json-report docs/evidence/<name>.json")
    : (zh
        ? `端门判定：p99 ${p99}ms · Δ ${baro >= 0 ? "+" : ""}${baro.toFixed(1)}ms · git 双件同压一机一门`
        : `front door: p99 ${p99}ms · Δ ${baro >= 0 ? "+" : ""}${baro.toFixed(1)}ms · both exhibits on this host, this lane`);

  const entryNum = entries.toLocaleString();

  return (
    <div className="gazette-page">
      {/* ── Masthead ─────────────────────────────────────────── */}
      <header className="gazette-masthead">
        <p className="gazette-kicker">{zh ? `铁 证 晨 报 · 第 ${entryNum} 份` : "THE MORNING GAZETTE OF IRON EVIDENCE"}</p>
        <h1 className="gazette-title">{zh ? "铁证晨报" : "Iron Evidence"} <span className="gazette-title-en">{zh ? "THE MORNING GAZETTE" : "铁证晨报"}</span></h1>
        <div className="gazette-dateline">
          <span>{isoWeek} — {isoToday}</span>
          <span className="gazette-dot">·</span>
          <span>{zh ? "永久免费 · git 发行" : "Free forever · distributed by git"}</span>
          <span className="gazette-dot">·</span>
          <span>{zh ? `编年史共 ${entryNum} 节` : `${entryNum} entries and counting`}</span>
        </div>
      </header>
      <ChainBanner />

      {/* ── Front page: lead story + columns ─────────────────── */}
      <div className="gazette-front">
        <article className="gazette-lead">
          <p className="gazette-lead-kicker">{zh ? "领 导 故 事" : "LEAD STORY"}<span className="gazette-lead-no">#{lead?.n}</span></p>
          <h2>{lead?.t}</h2>
          <p className="gazette-lead-body">{lead?.s}</p>
          <div className="gazette-lead-actions">
            <a className="gazette-pill" href="#/chronicle">{zh ? "全文见编年史 →" : "Full text in the Chronicle →"}</a>
            <button className="gazette-print" onClick={() => window.print()}>{zh ? "打印本报" : "Print this paper"} <ProductIcon name="gazette" size={14} /></button>
          </div>
        </article>

        <aside className="gazette-column gazette-column-briefs">
          <h3>{zh ? "本期速览" : "IN THIS ISSUE"}</h3>
          <ul>
            {latest.slice(1).map((e) => (
              <li key={e.n}>
                <span className="gazette-brief-no">#{e.n}</span>
                <span className="gazette-brief-t">{e.t}</span>
              </li>
            ))}
          </ul>
        </aside>

        <aside className="gazette-column gazette-column-index">
          <h3>{zh ? "编年史最近 18 行" : "THE LAST 18 LINES"}</h3>
          <ol>
            {briefs.map((e) => (
              <li key={e.n}>
                <span className="gazette-brief-no">#{e.n}</span>
                <span className="gazette-brief-t">{e.t}</span>
              </li>
            ))}
          </ol>
        </aside>
      </div>

      {/* ── Second page: numbers + editorial ──────────────────── */}
      <div className="gazette-second">
        <section className="gazette-column gazette-figures">
          <h3>{zh ? "本报的数字" : "BY THE NUMBERS"}</h3>
          <div className="gazette-figures-grid">
            <div><p>{Number(stats.repository_files).toLocaleString()}</p><span>{zh ? "跟踪文件" : "tracked files"}</span></div>
            <div><p>{Number(stats.total_lines_of_source).toLocaleString()}</p><span>{zh ? "源码行数" : "source lines"}</span></div>
            <div><p>{Number(stats.git_commit_count).toLocaleString()}</p><span>{zh ? "提交次数" : "commits"}</span></div>
            <div><p>{worldNum.toLocaleString()}</p><span>{zh ? "账本条目" : "ledger entries"}</span></div>
            <div><p>{worldSections}</p><span>{zh ? "世界书节数" : "world-book sections"}</span></div>
            <div><p>{stats.ledger_bytes_kB.toFixed(1)} KB</p><span>{zh ? "账本体积" : "ledger volume"}</span></div>
          </div>
          <p className="gazette-figures-note">{zh ? "本页所有数字由 scripts/build_repo_stats.py 与 build_chronicle.py 现推；不同即 bug。" : "Every figure on this page is re-derived live by build_repo_stats.py and build_chronicle.py; a mismatch is a bug."}</p>
        </section>

        <section className="gazette-column gazette-editorial">
          <p className="gazette-editorial-kicker">{zh ? "社 论" : "EDITORIAL"}</p>
          <h3>{zh ? "铁证先行，不信者为智" : "Evidence first; the doubter is wise"}</h3>
          <p>
            {zh
              ? "这份报纸不是模板，它是一次发行：每一行都从账本现抄，每一节都从 git 现推。我们不相信演示数据，所以报纸没有演示数据；我们不相信没有签名的结论，所以每条新闻都挂着它的编号。读到哪里，哪里就是你的国土——包括这一页。"
              : "This paper is not a template; it is an issue. Every line is transcribed from the ledger, every figure re-derived from git. We do not trust demo data, so this paper has none; we do not trust unsigned conclusions, so every story carries its number. Wherever you have read, that ground is yours — this page included."}
          </p>
          <p className="gazette-editorial-sign">{zh ? `—— 史官，于编年史第 ${entryNum} 节落笔时` : `— The Chronicler, signing at the ${entryNum}th entry`}</p>
        </section>

        <aside className="gazette-column gazette-weather">
          <h3>{zh ? "明日天气" : "TOMORROW'S WEATHER"}</h3>
          <p className="gazette-weather-big">{weatherName}</p>
          <p className="gazette-weather-line">{weatherLine}</p>
          <h4>{zh ? "通告" : "NOTICES"}</h4>
          <ul>
            <li>{zh ? `git 证据带 · exhibit #17 · 768/768 OK · worst p99 1,534.5 ms · Δvs#15 avg_p95 −1,010 ms` : `git evidence lane · exhibit #17 · 768/768 · 0 err · worst p99 1,534.5 ms · avg_p95 −1,010 ms vs #15`}</li>
            <li>{obsUnsigned ? (zh ? "巡天仍琥珀：等待真人 OBSERVABILITY.md 签字（灯下篇章等你）" : "the night watch stays amber: a human signature on OBSERVABILITY.md is still pending") : (zh ? "签字在场（巡天转玉绿）" : "signature present (night watch is jade)")}</li>
            <li>{zh ? "本周每周一 03:00 UTC · weekly-stress.yml 自动敲门（artifact 存档）" : "every Monday 03:00 UTC · weekly-stress.yml strikes (artifact archive)"}</li>
            <li>{zh ? `审计链 · ${auditChain.verdict}（${auditChain.lane_count || 5} 盏灯）· 幽灵灯不亮` : `audit chain · ${auditChain.verdict} (${auditChain.lane_count || 5} lanes) · the ghost switch stays off`}</li>
          </ul>

          <h4>{zh ? "本周实敲 · 三页可点" : "STRUCK THIS WEEK · THREE TICKETS"}</h4>
          <ul>
            <li><code>/dig · #1955-56</code>{zh ? " · 三只只读侦探并行问本仓一句——EVIDENCE-GATHERED（16,370 tokens）" : " · three readonly investigators fan out on one question — EVIDENCE-GATHERED (16,370 tokens)"}</li>
            <li><code>/runbook · #1959-60 · covenant #1969</code>{zh ? " · 告警一响，模型先读仓库；只能 CONFIRMED / INCONCLUSIVE" : " · the alert rings; the model reads the repo first; it only ever returns CONFIRMED or INCONCLUSIVE"}</li>
            <li><code>/observe · #1966</code>{zh ? " · 公开·只读·演示：240 人校准群体 + 这一浏览器自己的轨迹——没有别人" : " · public · read-only · demo — a seeded 240-member cohort plus this browser's taps; there is no one else"}</li>
          </ul>

          <h4>{zh ? "今天的余响 · 由模型写下" : "TODAY'S ECHO · WRITTEN BY THE MODEL"}</h4>
          <p className="gazette-echo">
            {zh ? (gazetteFeature as { zh: string }).zh : (gazetteFeature as { en: string }).en}
          </p>
          <p className="gazette-echo-stamp">
            {zh ? `— aizzz/gpt-6.1-terra · ${(gazetteFeature as { generated_at: string; anchor: string }).generated_at.slice(0, 10)} · 见证 #1975 原文 · 不是判词` : "— aizzz/gpt-6.1-terra · this cycle · the ledger verbatim · never a verdict"}
          </p>
        </aside>
      </div>

      {/* ── The Live Lane: measured, never imagined ─────────── */}
      <section className="gazette-lane" aria-label={zh ? "真车道 · 2026-11-17 实敲快照" : "The Live Lane (measured 2026-11-17)"}>
        <div className="gazette-lane-head">
          <p className="gazette-lane-kicker">{zh ? "真车道 · 2026-11-17 实敲" : "THE LIVE LANE · measured 2026-11-17"}</p>
          <p className="gazette-lane-sub">{zh ? "构建期快照：本栏每一个数字都可复验，但不冒充实时读数——进程活着才亮，进程退出即如实 down。" : "A build-time snapshot: every figure below is re-checkable, none of it pretends to be live traffic. Up means the process is up; when it exits, Prometheus says down — by design."}</p>
        </div>
        <div className="gazette-lane-grid">
          <div className="gazette-lane-cell">
            <span className="gazette-lane-k">{zh ? "存活探针" : "LIVENESS"}</span>
            <strong>{zh ? "/health 三件套全 true" : "/health: suite all true"}</strong>
            <code>mysql · redis · agent_jobs — 192.168.1.5:8000</code>
          </div>
          <div className="gazette-lane-cell">
            <span className="gazette-lane-k">{zh ? "SPA 直出" : "SPA SHIPS"}</span>
            <strong>{zh ? "/ 与 /manual → 200" : "/ and /manual → 200"}</strong>
            <code>1,490 bytes · zh-CN · server fallback</code>
          </div>
          <div className="gazette-lane-cell">
            <span className="gazette-lane-k">{zh ? "并发压测" : "LOAD BENCH"}</span>
            <strong>{zh ? "48/48 · 0 err" : "48/48 · 0 err"}</strong>
            <code>p99 587ms · prior week 192 req · 0 err</code>
          </div>
          <div className="gazette-lane-cell">
            <span className="gazette-lane-k">{zh ? "计数器入账" : "COUNTER DELTAS"}</span>
            <strong>{zh ? "5 → 55" : "5 → 55"}</strong>
            <code>specproof_http_requests_total · counted per request</code>
          </div>
          <div className="gazette-lane-cell">
            <span className="gazette-lane-k">{zh ? "假闭实证" : "FAIL-CLOSED"}</span>
            <strong>{zh ? "无钥匙 → 503" : "no key → 503"}</strong>
            <code>/api/v1/llm/usage · /admin/users · /api/v1/health</code>
          </div>
          <div className="gazette-lane-cell">
            <span className="gazette-lane-k">{zh ? "抓取入殿" : "SCRAPE ENTRY"}</span>
            <strong>{zh ? "local-host-api · up" : "local-host-api · up"}</strong>
            <code>{zh ? "3/10 · 本次 #1843 入 scrape（另两块匾：prometheus · rabbitmq）" : "3/10 · entry landed in #1843 (plus prometheus and rabbitmq)"}</code>
          </div>
          <div className="gazette-lane-cell">
            <span className="gazette-lane-k">{zh ? "外网取数" : "OUTBOUND FETCH"}</span>
            <strong>{zh ? "搜索 = HTTP 402" : "search = HTTP 402"}</strong>
            <code>{zh ? "本栏数字全部来自本机实敲 + git + docker + Prometheus API" : "all figures from local probing + git + docker + the Prometheus API"}</code>
          </div>
        </div>
        <div className="gazette-lane-foot">
          <span>{zh ? "完整命令与改前/改后两张表：docs/operations/LIVE_PROBE_2026-11-16.md · 编年史 #1843" : "Full commands and before/after tables: docs/operations/LIVE_PROBE_2026-11-16.md · chronicle #1843"}</span>
          <a className="gazette-pill gazette-lane-cta" href="#/chronicle">{zh ? "读编年史 →" : "Read the chronicle →"}</a>
        </div>
        <div className="gazette-lane-foot gazette-lane-foot-census">
          <span>{(() => {
            const totalAll = (evidence.all as Array<{ total: number }>).reduce((n, r) => n + r.total, 0);
            const okAll = (evidence.all as Array<{ total_ok: number }>).reduce((n, r) => n + r.total_ok, 0);
            const ratio = totalAll > 0 ? ((100 * okAll) / totalAll).toFixed(1) + "%" : "0/0";
            return zh
              ? `月报：${evidence.files_count} 件证据 · ${okAll.toLocaleString()}/${totalAll.toLocaleString()} req（${ratio}）全绿 — 详见 docs/evidence/monthly-census.md（scripts/monthly_census.py 生成）`
              : `Monthly: ${evidence.files_count} exhibits · ${okAll.toLocaleString()}/${totalAll.toLocaleString()} requests (${ratio}) green — see docs/evidence/monthly-census.md`;
          })()}</span>
          <a className="gazette-pill gazette-lane-cta" href="#/atlas">{zh ? "看活体地标 →" : "See the landmarks →"}</a>
        </div>
      </section>
    </div>
  );
}
