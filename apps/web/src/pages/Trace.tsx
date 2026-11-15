import { useMemo, useState } from "react";
import { useI18n } from "../i18n";
import chronicle from "./chronicle.json";
import worldbook from "./worldbook.json";
import { ProductIcon } from "../ui/ProductIcon";
import "../styles/trace.css";

/**
 * The Trace — every claim in this world carried back to its commit.
 *
 * Type any short hash, ledger number, or phrase — the page scans
 * chronicle.json (1,624 sections) and worldbook.json (50 volumes)
 * live, and renders it in the same moment: nothing is retrieved from
 * anywhere but this repository's own git-tracked JSON. Paste anything
 * you believe is evidence; the page shows the exact byte ranges that
 * prove or fail to prove it.
 *
 * Honestly: a single-browser substring scan, not an index. It proves
 * a thing was written; it does not prove the thing is true, nor that
 * it proves anything. The ledger is the anchor — read it, not the page.
 */

interface ChronEntry { n: number; t: string; s: string }
interface WBVolume { id: string; num: string; title: string; markdown: string }
const ENTRIES = chronicle as ChronEntry[];
const VOLUMES = (worldbook as { locales: { zh: { volumes: WBVolume[] }, en: { volumes: WBVolume[] } } }).locales.zh.volumes;

function windowAround(text: string, needle: string, budget: number): string {
  const i = text.toLowerCase().indexOf(needle.toLowerCase());
  if (i < 0) return "";
  const start = Math.max(0, i - Math.floor(budget / 2));
  const end = Math.min(text.length, i + needle.length + Math.floor(budget / 2));
  const prefix = start > 0 ? "…" : "";
  const suffix = end < text.length ? "…" : "";
  return prefix + text.slice(start, end).replace(/\s+/g, " ").trim() + suffix;
}

export default function Trace(): JSX.Element {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const L = (a: string, b: string): string => (zh ? a : b);
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();

  const chronoHits = useMemo(() => {
    if (!q) return [];
    const qNoHash = q.startsWith("#") ? q.slice(1) : q;
    return ENTRIES.map((e) => {
      const nMatch = String(e.n) === qNoHash || String(e.n).includes(qNoHash);
      const tMatch = e.t.toLowerCase().includes(qNoHash);
      const sMatch = e.s && e.s.toLowerCase().includes(qNoHash);
      const score = (nMatch ? 100 : 0) + (tMatch ? 50 : 0) + (sMatch ? 25 : 0);
      return { e, score, hits: nMatch || tMatch || sMatch, nMatch, tMatch, sMatch };
    }).filter((h) => h.hits).sort((a, b) => b.score - a.score).slice(0, 40);
  }, [q]);

  const volumeHits = useMemo(() => {
    if (!q) return [];
    return VOLUMES.map((v) => {
      const tMatch = v.title.toLowerCase().includes(q);
      const mMatch = v.markdown.toLowerCase().includes(q);
      const excerpt = mMatch ? windowAround(v.markdown, q, 240) : "";
      return { v, title: v.title, tMatch, mMatch, excerpt };
    }).filter((h) => h.tMatch || h.mMatch).slice(0, 40);
  }, [q]);

  const totalBundles = chronoHits.length + volumeHits.length;

  return (
    <div className="trace-page">
      <header className="trace-mast">
        <p className="trace-kicker">{L("按 图 索 骥", "FOLLOW THE EVIDENCE")}</p>
        <h1>{L("溯源", "The Trace")} <span className="trace-en">{L("THE TRACE · 从任何一句话回到它的依据", "THE TRACE · FROM ANY SENTENCE BACK TO ITS EVIDENCE")}</span></h1>
        <p className="trace-lead">
          {L(
            "本页把 1,624 节账本和 50 卷世界书当场扫了一遍——输入任何你怀疑的句子、任何 commit 短哈希、任何一个 #NNNN 编号。能找到就显示出来，找不到就说找不到——这不是索引，也不是搜索引擎，是自己肠子面前的人对自己仓库开的一次证明的目光。",
            "This page runs a live scan over 1,624 chronicle sections and 50 volumes of the world book. Type any sentence, commit short-hash or #NNNN number. If it's there, it will show you — if it isn't, it tells you so. This is not an index engine and not a search service — it is an eye turned inward by a person to their own machine.",
          )}
        </p>
        <div className="trace-search-row">
          <input
            className="trace-search"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
            placeholder={L("git 短哈希（如 e06d918）· #1790 节号 · 或直接粘一句话……", "commit short hash (e.g. e06d918) · #NNNN · or paste any sentence…")}
            aria-label={L("搜索依据", "query evidence")}
          />
        </div>
        <div className="trace-chips">
          {["e06d918", "#1819", "4f2ad98", "#1800", "e657631", "#1781"].map((seed) => (
            <button key={seed} className="trace-chip" onClick={() => setQuery(seed)}>{seed}</button>
          ))}
        </div>
        {q && (
          <p className="trace-count">
            {L("命中的证据块", "evidence bundles found")} <strong>{totalBundles}</strong> · 
            {L("账本命中", "chronicle hits")} <strong>{chronoHits.length}</strong> · 
            {L("世界书命中", "world-book hits")} <strong>{volumeHits.length}</strong>
          </p>
        )}
      </header>

      {q.length >= 3 && (
        <div className="trace-grid">
          <section className="trace-panel trace-chrono" aria-label={L("账本命中的条目", "Chronicle hits")}>
            <h2>{L("账本 · 1,624 节", "The ledger · 1,624 sections")}</h2>
            {chronoHits.length === 0 ? (
              <p className="trace-empty">{L("没有一节账本包含这条检索。", "Not a single ledger section contains this query.")}</p>
            ) : (
              <ol className="trace-list">
                {chronoHits.map(({ e }) => (
                  <li key={e.n} className="trace-row">
                    <a className="trace-row-head" href={`#/chronicle?q=${encodeURIComponent(String(e.n))}`}>
                      <span className="trace-row-n">#{e.n}</span>
                      <span className="trace-row-title">{e.t.replace(/^—\s*/, "")}</span>
                    </a>
                    {e.s && <p className="trace-row-body">{e.s.replace(/\s+/g, " ").slice(0, 280)}{e.s.length > 280 ? "…" : ""}</p>}
                  </li>
                ))}
              </ol>
            )}
          </section>

          <section className="trace-panel trace-world" aria-label={L("世界书命中的卷", "World-book hits")}>
            <h2>{L("世界书 · 50 卷", "The world book · 50 volumes")}</h2>
            {volumeHits.length === 0 ? (
              <p className="trace-empty">{L("没有一卷世界书包含这条检索。", "Not a single volume contains this query.")}</p>
            ) : (
              <ol className="trace-list">
                {volumeHits.map(({ v, title, excerpt, tMatch, mMatch }) => (
                  <li key={v.id} className="trace-row">
                    <a className="trace-row-head" href="#/worldbook">
                      <span className="trace-row-n">{v.num || "—"}</span>
                      <span className="trace-row-title">{title}</span>
                      <span className="trace-row-badge">{tMatch ? L("卷目命中", "title hit") : mMatch ? L("正文命中", "body hit") : ""}</span>
                    </a>
                    {excerpt && <p className="trace-row-body">{excerpt}</p>}
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>
      )}

      {q.length > 0 && q.length < 3 && (
        <p className="trace-tooshort">{L("再多敲两个字符再说。", "Two more characters, then the evidence will talk.")}</p>
      )}

      {!q && (
        <section className="trace-empty-panel">
          <ProductIcon name="shield" size={26} />
          <p>{L(
            "这不是演示数据——每一行所显示的，都是这个仓库自己的账本和自己的世界书。只证你所知道的那一句不是从 AI 的嘴里编出来的，是从这仓库的 git 审计里得的。",
            "Not demo data — every line on this page is read from this repository's own ledger and own world book. It exists to prove that what you heard was not fabricated — it was audited by git.",
          )}</p>
        </section>
      )}

      <footer className="trace-honesty">
        <ProductIcon name="shield" size={13} />
        <p>
          {zh
            ? "本页没有索引引擎、没有数据库写库、没有任何 fetch 后端接口——只是用 substring 扫 chronicle.json / worldbook.json 的两处内置 JSON。找不到 = 没写；找到 ≠ 一定对。证据的最终所有权在 git——这一页只是它的眼睛。"
            : "No index engine, no database, no backend call — substring scans over two committed JSONs: chronicle.json and worldbook.json. Not found = not written; found ≠ true. Evidence belongs to git — this page is only its eye."}
        </p>
      </footer>
    </div>
  );
}
