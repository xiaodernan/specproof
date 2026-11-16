import { useMemo, useState } from "react";
import { useI18n } from "../i18n";
import chronicle from "./chronicle.json";
import corrections from "./corrections.json";
import ChainBanner from "./ChainBanner";
import "../styles/recall.css";

/**
 * 问铁证 · Ask the Iron — the "retrieval half" of RAG, struck honestly.
 *
 * No model is called, no network is touched, no embeddings are faked: every
 * ranking on this page is BM25 over files that are already git-tracked —
 * the 1,683-line chronicle (`chronicle.json`) and the append-only errata
 * scroll (`corrections.json`). Same query + same JSON ⇒ same scores, always.
 *
 * Why it lives here: the LLM lane is closed for this channel (see /engine;
 * the gateway answers 「本站不对您所在的国家及地区进行商业服务」), so the
 * only lawful way to ask the iron something right now is to let iron answer.
 */

type ChronicleEntry = { n: number; t: string; s: string };
type Doc = { id: string; kind: "ledger" | "erratum"; n: number | string; title: string; body: string };

const CHRONICLE: Array<ChronicleEntry> = chronicle as unknown as ChronicleEntry[];
const ERRATA: Doc[] = ((corrections as { ids?: string[]; items?: string[] }).items ?? []).map((item, i) => ({
  id: `erratum-${(corrections as { ids?: string[] }).ids?.[i] ?? i}`,
  kind: "erratum",
  n: (corrections as { ids?: string[] }).ids?.[i] ?? `E${i}`,
  title: (corrections as { ids?: string[] }).ids?.[i] ?? `R${i}`,
  body: item,
}));

const DOCS: Doc[] = [
  ...CHRONICLE.map((e) => ({ id: `ledger-${e.n}`, kind: "ledger" as const, n: e.n, title: e.t, body: e.s })),
  ...ERRATA,
];

const K1 = 1.5;
const B = 0.75;

/** CJK unigrams+bigrams, latin/digit word runs — both scripts on one field. */
function tokenize(text: string): string[] {
  const lower = text.toLowerCase();
  const tokens: string[] = [];
  for (const m of lower.matchAll(/[a-z0-9_]{2,}/g)) tokens.push(m[0]);
  const cjk = (lower.match(/[\u3400-\u9fff\uf900-\ufaff]/g) ?? []).join("");
  for (let i = 0; i < cjk.length; i += 1) tokens.push(cjk[i]);
  for (let i = 0; i + 1 < cjk.length; i += 1) tokens.push(cjk.slice(i, i + 2));
  return tokens;
}

interface FieldIndex {
  tf: Map<string, number>;
  len: number;
}

interface Index {
  fields: Array<{ title: FieldIndex; body: FieldIndex }>;
  df: Map<string, number>;
  avgTitle: number;
  avgBody: number;
}

function buildIndex(): Index {
  const fields = DOCS.map((doc) => {
    const titleTokens = tokenize(doc.title);
    const bodyTokens = tokenize(doc.body);
    const toField = (toks: string[]): FieldIndex => {
      const tf = new Map<string, number>();
      for (const t of toks) tf.set(t, (tf.get(t) ?? 0) + 1);
      return { tf, len: toks.length };
    };
    return { title: toField(titleTokens), body: toField(bodyTokens) };
  });
  const df = new Map<string, number>();
  for (const f of fields) {
    const seen = new Set<string>([...f.title.tf.keys(), ...f.body.tf.keys()]);
    for (const term of seen) df.set(term, (df.get(term) ?? 0) + 1);
  }
  const avgTitle = fields.reduce((n, f) => n + f.title.len, 0) / fields.length;
  const avgBody = fields.reduce((n, f) => n + f.body.len, 0) / fields.length;
  return { fields, df, avgTitle, avgBody };
}

const INDEX = buildIndex();
const N = INDEX.fields.length;
const idf = (term: string): number => {
  const df = INDEX.df.get(term) ?? 0;
  return Math.log(1 + (N - df + 0.5) / (df + 0.5));
};
const fieldScore = (field: FieldIndex, avg: number, term: string): number => {
  const tf = field.tf.get(term);
  if (!tf) return 0;
  const norm = 1 - B + (B * field.len) / (avg || 1);
  return (tf * (K1 + 1)) / (tf + K1 * norm);
};

interface Hit {
  doc: Doc;
  score: number;
}

function search(query: string, limit: number): { hits: Hit[]; totalMatching: number } {
  const terms = [...new Set(tokenize(query))];
  if (terms.length === 0) return { hits: [], totalMatching: 0 };
  const scores = new Float64Array(DOCS.length);
  for (let i = 0; i < DOCS.length; i += 1) {
    const f = INDEX.fields[i];
    let s = 0;
    for (const term of terms) {
      const w = idf(term);
      s += w * (2.4 * fieldScore(f.title, INDEX.avgTitle, term) + fieldScore(f.body, INDEX.avgBody, term));
    }
    scores[i] = s;
  }
  const hits: Hit[] = [];
  for (let i = 0; i < DOCS.length; i += 1) {
    if (scores[i] > 0) hits.push({ doc: DOCS[i], score: scores[i] });
  }
  hits.sort((a, b) => b.score - a.score || String(a.doc.n).localeCompare(String(b.doc.n)));
  return { hits: hits.slice(0, limit), totalMatching: hits.length };
}

function snippet(body: string, query: string, radius = 110): string {
  const lower = body.toLowerCase();
  let idx = -1;
  for (const token of tokenize(query)) {
    const at = lower.indexOf(token);
    if (at !== -1 && (idx === -1 || at < idx)) idx = at;
  }
  if (idx === -1) idx = 0;
  const start = Math.max(0, idx - radius);
  const end = Math.min(body.length, idx + radius);
  return (start > 0 ? "…" : "") + body.slice(start, end).replace(/\s+/g, " ").trim() + (end < body.length ? "…" : "");
}

const SUGGESTED = ["court 永不缓存", "滚轮", "cache", "LLM", "密钥", "密码 123", "stream"];

export default function Recall() {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const L = (a: string, b: string): string => (zh ? a : b);
  const [query, setQuery] = useState("");

  const trimmed = query.trim();
  const { hits, totalMatching } = useMemo(() => search(trimmed, 10), [trimmed]);

  return (
    <div className="recall-page">
      <div className="page-head">
        <h1>{L("问铁证", "Ask the Iron")} <span className="recall-en">{L("ASK THE IRON · 答案不来自模型", "ASK THE IRON · the answer is not the model")}</span></h1>
        <div className="page-sub">
          {L(
            `检索 1,683 节编年史 + 13 条更正卷轴（BM25，纯本地，输入输出可复现）。本页不调用大模型——模型车道今天关着，见引擎页；这里每一条排序都是现敲出来的。`,
            `Search 1,683 chronicle lines + 13 errata (BM25, fully local, reproducible). This page never calls the model — the lane is closed today (see /engine); every ranking here is struck on the spot.`,
          )}
        </div>
      </div>

      <ChainBanner />

      <label className="recall-search" htmlFor="recall-filter">
        <span className="visually-hidden">{L("输入要问的话", "Type your question")}</span>
        <input
          id="recall-filter"
          type="search"
          className="recall-filter"
          placeholder={L("问点真的事情：court 永不缓存？滚轮改了没有？密钥从哪进仓？", "Ask a real thing: is the court cached? the wheel? where did keys leak in?")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoComplete="off"
          spellCheck={false}
        />
        <span className="recall-count" aria-live="polite">{trimmed ? `${Math.min(totalMatching, 10)} / ${totalMatching}` : `${DOCS.length.toLocaleString()}`}</span>
      </label>

      {!trimmed && (
        <div className="recall-empty">
          <p className="recall-empty-lead">{L("从这些敲门声开始：", "Begin with one of these knocks:")}</p>
          <div className="recall-chips">
            {SUGGESTED.map((s) => (
              <button key={s} type="button" className="recall-chip" onClick={() => setQuery(s)}>{s}</button>
            ))}
          </div>
        </div>
      )}

      {trimmed && hits.length === 0 && (
        <p className="recall-noresult">{L("没有一行账本咬住这个词。换个说法再敲一次（关键词越具体越准）。", "Not one ledger line bit this word. Rephrase (more specific keywords land better).")}</p>
      )}

      <ol className="recall-results">
        {hits.map((hit) => (
          <li key={hit.doc.id} className="recall-hit">
            <div className="recall-hit-head">
              <span className={`recall-badge recall-badge-${hit.doc.kind}`}>{hit.doc.kind === "ledger" ? L(`账本 #${hit.doc.n}`, `LEDGER #${hit.doc.n}`) : L(`更正 ${hit.doc.n}`, `ERRATUM ${hit.doc.n}`)}</span>
              <span className="recall-score" title={L("原始 BM25 分数（不做归一化、不做百分比）", "Raw BM25 score (never normalized, never a percentage)")}>{hit.score.toFixed(2)}</span>
            </div>
            <h3 className="recall-hit-title">{hit.doc.title}</h3>
            <p className="recall-hit-body">{snippet(hit.doc.body, trimmed)}</p>
            <a className="recall-hit-cta" href="#/chronicle">{L("去编年史里找它 →", "Find it in the Chronicle →")}</a>
          </li>
        ))}
      </ol>

      <p className="muted recall-colophon">{L("同一查询 · 同一份 git-tracked JSON · 同一分数。没有模型、没有联网、没有美化——问铁证，铁证答。", "Same query · same git-tracked JSON · same scores. No model, no network, no varnish — ask the iron, the iron answers.")}</p>
    </div>
  );
}
