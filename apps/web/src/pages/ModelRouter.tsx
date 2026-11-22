import { useState } from "react";
import { useI18n } from "../i18n";
import { postModelRouterAsk, type ModelRouterAsk } from "../api";
import ChainBanner from "./ChainBanner";
import "../styles/askthebook.css";

/**
 * 模型选路 · Model Router — the live product face of the model_router
 * StateGraph (#1638). Unlike a witness graph, the MODEL picks the lane: its
 * structured JSON label drives the graph's conditional edge, and the chosen
 * lane writes the content. This page shows exactly which lane won, why, and
 * how warm the cache was.
 *
 * Never a verdict: the model may route and explain, but it never grades an
 * exhibit. A hallucinated route (ROUTE-DRIFT) or a verdict in the content
 * (VERDICT-LEAK) is refused and shown honestly, never dressed as an answer.
 */
const LANE_LABELS: Record<string, { zh: string; en: string; hintZh: string; hintEn: string }> = {
  evidence: {
    zh: "证据车道", en: "Evidence lane",
    hintZh: "一次验收的结论与证据是怎么来的", hintEn: "how a verification conclusion and its evidence were reached",
  },
  worldbook: {
    zh: "世界书车道", en: "World-book lane",
    hintZh: "本仓正史与账本里记过的事实", hintEn: "facts recorded in this repo's chronicle and ledger",
  },
  nextstep: {
    zh: "下一步车道", en: "Next-step lane",
    hintZh: "在产品里接下来该做什么", hintEn: "what to do next inside the product",
  },
};

export default function ModelRouter() {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const L = (a: string, b: string): string => (zh ? a : b);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<ModelRouterAsk | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const SUGGESTED = zh
    ? [
        "SpecProof 的验收结论是怎么定出来的？",
        "世界书里记过哪些真实的数据？",
        "我接下来在这个产品里该做什么？",
      ]
    : [
        "How is a SpecProof acceptance conclusion reached?",
        "What real data is recorded in the world book?",
        "What should I do next in this product?",
      ];

  const send = async (raw: string) => {
    const q = raw.trim();
    if (!q || busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await postModelRouterAsk(q, locale as "zh" | "en"));
    } catch (e) {
      setError(L("模型暂时不可用——没有编造任何选路。（", "The model is unavailable — no route was fabricated. (") +
        (e instanceof Error ? e.message : String(e)) + ")");
    } finally {
      setBusy(false);
    }
  };

  const usage = (result?.usage ?? {}) as Record<string, number | undefined>;
  const hit = typeof usage.cached_tokens_seen === "number" ? usage.cached_tokens_seen : null;
  const ratio = typeof usage.cache_hit_ratio === "number" ? usage.cache_hit_ratio : null;
  const lane = result && LANE_LABELS[result.route];

  return (
    <div className="askthebook-page">
      <div className="page-head">
        <h1>{L("模型选路", "Model Router")} <span className="askthebook-en">{L("STATEGRAPH · 模型选路，车道作答", "STATEGRAPH · the model routes, the lane answers")}</span></h1>
        <div className="page-sub">
          {L(
            "这是状态流转图的现场版：模型先读你的问题、吐出一条车道标签（图的条件边），再由被选中的车道写答案。它绝不判任何展品的绿——幻觉选路或裁决措辞都会被拦下并如实展示。",
            "This is the live face of the state-flow graph: the model reads your question and emits a lane label (the graph's conditional edge), then the chosen lane writes the answer. It never grades an exhibit — a hallucinated route or verdict wording is refused and shown honestly.",
          )}
        </div>
      </div>

      <ChainBanner />

      <form className="askthebook-form" onSubmit={(e) => { e.preventDefault(); void send(question); }}>
        <label className="askthebook-label" htmlFor="model-router-input">
          <span className="visually-hidden">{L("你想让模型路由什么问题", "What should the model route?")}</span>
          <textarea
            id="model-router-input"
            className="askthebook-input"
            rows={2}
            maxLength={480}
            placeholder={L("问一个关于验收、世界书或下一步的问题，看模型把它分到哪条车道……", "Ask about an acceptance, the world book, or a next step — watch which lane the model picks...")}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={busy}
          />
        </label>
        <div className="askthebook-actions">
          <span className="askthebook-count" aria-live="polite">{question.trim().length}/480</span>
          <button type="submit" className="btn btn-primary" disabled={busy || question.trim().length === 0}>
            {busy ? L("正在选路…", "Routing…") : L("选路并作答", "Route & answer")}
          </button>
        </div>
      </form>

      {!question.trim() && (
        <div className="askthebook-chips" aria-label={L("试几个问题", "Try a few")}>
          {SUGGESTED.map((s) => (
            <button key={s} type="button" className="askthebook-chip" onClick={() => { setQuestion(s); void send(s); }}>{s}</button>
          ))}
        </div>
      )}

      {error && <p className="askthebook-error" role="alert">{error}</p>}

      {result && (
        <section className="askthebook-answer" aria-live="polite">
          <header className="askthebook-answer-head">
            <span className="askthebook-badge">
              {result.route_drift
                ? L("选路漂移 · 已拒绝", "ROUTE-DRIFT · refused")
                : result.verdict === "VERDICT-LEAK"
                  ? L("裁决措辞 · 已拒绝", "VERDICT-LEAK · refused")
                  : lane
                    ? `${zh ? lane.zh : lane.en}${result.route_source === "model" ? (zh ? " · 模型所选" : " · model-picked") : ""}`
                    : result.route}
            </span>
            <span className="askthebook-meta">
              {result.model ?? "model"}{" · "}
              {result.model_latency_ms != null ? `${(result.model_latency_ms / 1000).toFixed(1)}s` : "—"}
              {result.cached ? L(" · 指纹缓存命中", " · fingerprint hit") : ""}
              {hit != null ? ` · ${L("命中", "cached")} ${hit}${ratio != null ? ` (${(ratio * 100).toFixed(1)}%)` : ""}` : ""}
            </span>
          </header>
          {lane && result.verdict !== "VERDICT-LEAK" && (
            <p className="askthebook-meta">{zh ? lane.hintZh : lane.hintEn}</p>
          )}
          <p className="askthebook-answer-body">
            {result.verdict === "VERDICT-LEAK"
              ? L("模型试图给出裁决措辞，已被拦下——这张图只解释路线，不评判展品。", "The model tried to issue a verdict; it was refused — this graph explains routes, it does not grade exhibits.")
              : result.route_drift
                ? L("模型给出了允许清单之外的路线，已被拦下——没有编造任何答案。", "The model chose a route outside the allowlist; it was refused — no answer was fabricated.")
                : result.content}
          </p>
          <p className="askthebook-footnote">
            {L(
              "模型打印的话不附带裁决。它选的是解释路线，不是给你盖章——要判定一个展品，仍然只能靠真正的验收流程。",
              "Nothing the model prints carries a verdict. It picks an explanation lane, not a stamp — grading an exhibit still requires the real acceptance flow.",
            )}
          </p>
        </section>
      )}
    </div>
  );
}
