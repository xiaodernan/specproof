import { useState } from "react";
import { useI18n } from "../i18n";
import { postWorldbookAsk, type WorldbookAsk } from "../api";
import ChainBanner from "./ChainBanner";
import snapshot from "./askthebook_snapshot.json";
import "../styles/askthebook.css";

/**
 * 问问书 · Ask the Book — the live-*reading* lane this repository exposes.
 * The model reads the whole world book as its own context the moment you
 * ask; the book never leaves this process (the codex is byte-frozen and
 * rides in as part of the system prefix — nothing from this page touches
 * any network or any court).
 *
 * What the model may never do here, by construction:
 *
 *   * return a verdict of any shape — the system message forbids it;
 *   * speak for the book about anything the book does not say — it must
 *     say "the book does not say" instead;
 *   * invent numbers, dates, names or events.
 *
 * UI never dresses one character differently from another as "binding":
 * the answer is model-written, and it is labelled as such.
 */
export default function AskTheBook() {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const L = (a: string, b: string): string => (zh ? a : b);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<WorldbookAsk | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const SUGGESTED_ZH = [
    "这个世界书是从哪里开始的？",
    "夜班是什么？",
    "展品 #4 为什么红着？",
    "Court 为什么永远锁着？",
  ];
  const SUGGESTED_EN = [
    "Where does this world book start?",
    "What is the night watch?",
    "Why is exhibit #4 pinned red?",
    "Why is the court locked forever?",
  ];

  const localFallback = (rawQuestion: string): { answer: string; volume: string } | null => {
    const q = rawQuestion.toLowerCase();
    const scored = (snapshot as Array<{ id: string; volume: string; excerpt: string; keywords_zh: string[]; keywords_en: string[] }>)
      .map((entry) => {
        const keywords = zh ? entry.keywords_zh : entry.keywords_en;
        let hits = 0;
        for (const kw of keywords) {
          if (q.includes(kw.toLowerCase())) hits += 1;
        }
        return { entry, hits };
      })
      .filter(({ hits }) => hits > 0)
      .sort((a, b) => b.hits - a.hits);
    if (scored.length === 0) return null;
    const best = scored[0].entry;
    return { answer: best.excerpt.trim(), volume: best.volume };
  };

  const send = async (rawQuestion: string) => {
    const q = rawQuestion.trim();
    if (!q || busy) return;
    setBusy(true);
    setError(null);
    setAnswer(null);
    try {
      const result = await postWorldbookAsk(q, locale as "zh" | "en");
      setAnswer(result);
    } catch (e) {
      const local = localFallback(rawQuestion);
      if (local) {
        setAnswer({
          answer: zh
            ? `书里说：\n\n${local.answer}\n\n（${local.volume} · 本书原文，未经节选）`
            : `The book says：\n\n${local.answer}\n\n（${local.volume} · the book's own text, uncut）`,
          model: "verbatim-from-the-worldbook",
          model_latency_ms: 0,
          usage: null,
          question_chars: rawQuestion.trim().length,
          cached: false,
        } as WorldbookAsk);
        setError(null);
      } else {
        const msg = e instanceof Error ? e.message : String(e);
        setError(
          L(
            `模型暂时没回答出来，书里也没写。（${msg}）`,
            `The model could not answer, and the book does not say either. (${msg})`,
          ),
        );
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="askthebook-page">
      <div className="page-head">
        <h1>{L("问问书", "Ask the Book")} <span className="askthebook-en">{L("ASK THE WORLD · 问之有答，答无审判", "ASK THE WORLD · an answer is not a verdict")}</span></h1>
        <div className="page-sub">
          {L(
            "模型读过整本铁证之书（zh + en），你可以直接问。它只会替你把书里写过的话端出来——书里没写的，它直说没有。纯模型现场回答 · 为只读演示 · 不判任何展品的绿。",
            "The model has read the whole iron-grammar bible (zh + en); ask anything. It may only hand back what the book says — if the book is silent, it will say so. Live, read-only, model-written — it never paints any exhibit green.",
          )}
        </div>
      </div>

      <ChainBanner />

      <form
        className="askthebook-form"
        onSubmit={(e) => {
          e.preventDefault();
          void send(question);
        }}
      >
        <label className="askthebook-label" htmlFor="ask-the-book-input">
          <span className="visually-hidden">{L("你想问这本书什么", "What would you ask the book?")}</span>
          <textarea
            id="ask-the-book-input"
            className="askthebook-input"
            rows={2}
            maxLength={480}
            placeholder={L("问点世界书里的事：验收车道怎么走？夜班为什么敲碎？世界书第零卷讲什么？", "Ask the book: how does an acceptance lane run? why does the night watch stay cracked? what is volume zero?")}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={busy}
          />
        </label>
        <div className="askthebook-actions">
          <span className="askthebook-count" aria-live="polite">
            {question.trim().length}/480
          </span>
          <button type="submit" className="btn btn-primary" disabled={busy || question.trim().length === 0}>
            {busy ? L("正在翻书…", "Opening the book…") : L("问！", "Ask")}
          </button>
        </div>
      </form>

      {!question.trim() && (
        <div className="askthebook-chips" aria-label={L("几个敲门咒", "A few knocks")}>
          {(zh ? SUGGESTED_ZH : SUGGESTED_EN).map((s) => (
            <button key={s} type="button" className="askthebook-chip" onClick={() => { setQuestion(s); void send(s); }}>
              {s}
            </button>
          ))}
        </div>
      )}

      {error && <p className="askthebook-error" role="alert">{error}</p>}

      {answer && (
        <section className="askthebook-answer" aria-live="polite">
          <header className="askthebook-answer-head">
            <span className="askthebook-badge">
              {answer.model === "verbatim-from-the-worldbook"
                ? L("书里原文", "THE BOOK'S OWN TEXT")
                : L("模型读过的原话", "THE MODEL READ IT")}
            </span>
            <span className="askthebook-meta">
              {answer.model === "verbatim-from-the-worldbook"
                ? L("离线本地 · 书里 · 不打网络", "offline · the book itself · zero network")
                : <>{answer.model ?? "model"}{" · "}
                    {answer.model_latency_ms != null ? `${(answer.model_latency_ms / 1000).toFixed(1)}s` : "—"}
                    {answer.cached ? L(" · 指纹缓存命中", " · fingerprint hit") : ""}</>}
            </span>
          </header>
          <p className="askthebook-answer-body">{answer.answer}</p>
          <p className="askthebook-footnote">
            {answer.model === "verbatim-from-the-worldbook"
              ? L(
                  "这段话是书里原文——模型刚才没举起笔，是书自己举的。没有裁决，没有评判，只是一本书自己说话。",
                  "This is the book's own text — the model hasn't lifted its pen; the book has. No ruling, no verdict, just the book speaking.",
                )
              : L(
                  "模型打印的话不附带裁决。它引用的是这本书——不构成任何直线结论。若一字一句与书中记载不符，以书为准。",
                  "The model does not rule anything. Nothing it says carries a verdict — where it drifts from the book, the book wins.",
                )}
          </p>
        </section>
      )}
    </div>
  );
}
