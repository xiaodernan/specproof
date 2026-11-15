import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../i18n";
import worldbook from "./worldbook.json";
import { ProductIcon } from "../ui/ProductIcon";
import "../styles/gallery.css";

/**
 * The Gallery — a wall of everything this world has written so far.
 * Every tile on this page is a REAL volume of the SpecProof world book,
 * read build-time from worldbook.json (excerpted live, never truncated at
 * the source). Click any tile to open the World Book to read it in full.
 * No content here is invented at runtime.
 */

type WBVolume = { id: string; num: string; title: string; markdown: string };
const ZH_VOLUMES = (worldbook as { locales: { zh: { volumes: WBVolume[] } } }).locales.zh.volumes;
const EN_VOLUMES = (worldbook as { locales: { en: { volumes: WBVolume[] } } }).locales.en.volumes;

function firstProseExcerpt(markdown: string, budget: number): string {
  const clean = markdown
    .replace(/^>\s?/gm, "")
    .replace(/^#+\s*/gm, "")
    .replace(/```[\s\S]*?```/g, "")
    .replace(/`{1,3}/g, "")
    .split(/\n+/)
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("|") && !l.startsWith("---"))
    .slice(0, 30)
    .join(" ");
  return clean.length > budget ? clean.slice(0, budget - 1).trimEnd() + "…" : clean;
}

export default function Gallery(): JSX.Element {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const L = (a: string, b: string): string => (zh ? a : b);
  const [query, setQuery] = useState("");
  const volumes = zh ? ZH_VOLUMES : EN_VOLUMES;

  useEffect(() => {
    document.title = L("卷墙 · SpecProof", "The Gallery · SpecProof");
  }, [zh]);

  const cards = useMemo(() => {
    const q = query.trim().toLowerCase();
    return volumes.map((v) => ({ v, excerpt: firstProseExcerpt(v.markdown, zh ? 96 : 150) }))
      .filter(({ v }) => !q || v.title.toLowerCase().includes(q) || v.num.toLowerCase().includes(q) || v.id.toLowerCase().includes(q));
  }, [volumes, query, zh]);

  const maxExcerpt = Math.max(...volumes.map((v) => v.markdown.length), 1);

  return (
    <div className="gallery-page">
      <header className="gallery-mast">
        <p className="gallery-kicker">{L("卷 墙", "GALLERY OF ALL WRITTEN THINGS")}</p>
        <h1>{L("卷墙", "The Gallery")} <span className="gallery-en">{L("THE GALLERY · 全部卷目", "卷 墙 · EVERY VOLUME EVER WRITTEN")}</span></h1>
        <p className="gallery-lead">
          {L(
            "这面墙不漏掉一本——世界书每一卷、每一章、每一页敲门纸，全部按写成它的原文实陈上墙。搜索标题，或者点开任何一块板去书店翻它。",
            "Nothing is left off this wall — every volume of the world book, standing exactly as written. Search a title, or step into any tile and read the full chapter.",
          )}
        </p>
        <div className="gallery-stats">
          <div className="gallery-stat"><p className="gallery-stat-v">{volumes.length}</p><p className="gallery-stat-l">{L("卷", "volumes")}</p></div>
          <div className="gallery-stat"><p className="gallery-stat-v">{volumes.reduce((n, v) => n + v.markdown.length, 0).toLocaleString()}</p><p className="gallery-stat-l">{L("字符（全卷总字数）", "characters, all volumes")}</p></div>
          <div className="gallery-stat"><p className="gallery-stat-v">{cards.length}</p><p className="gallery-stat-l">{L("在你眼前", "in front of you")}</p></div>
        </div>
        <input
          className="gallery-search"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={L("搜索卷号、卷目、id…", "Search volume number, title, id…")}
          aria-label={L("搜索这面墙", "search the wall")}
        />
      </header>

      <div className="gallery-grid">
        {cards.map(({ v, excerpt }) => (
          <a key={v.id} className="gallery-tile" href="#/worldbook" aria-label={`${L("翻开", "Open")} ${v.title}`}>
            <div className="gallery-tile-seal" aria-hidden="true">{v.num || "—"}</div>
            <h2 className="gallery-tile-title">{v.title}</h2>
            <p className="gallery-tile-excerpt">{excerpt}</p>
            <div className="gallery-tile-foot">
              <span className="gallery-tile-id">{v.id}</span>
              <span className="gallery-tile-meter" aria-hidden="true"><span style={{ width: `${Math.min(100, (v.markdown.length / maxExcerpt) * 100)}%` }} /></span>
              <span className="gallery-tile-goto">{L("去翻 →", "Open →")}</span>
            </div>
          </a>
        ))}
        {cards.length === 0 && (
          <div className="gallery-empty">
            <ProductIcon name="scroll" size={28} />
            <p>{L("这面墙上没有这个卷目——试着换一个词。", "No tile matches that — try another word.")}</p>
            <button className="gallery-reset" onClick={() => setQuery("")}>{L("清空搜索", "clear search")}</button>
          </div>
        )}
      </div>

      <footer className="gallery-footer">
        <ProductIcon name="shield" size={13} />
        <p>
          {zh
            ? "这面墙不是展览海报——每一块板都是世界书原文的一次搬运（worldbook.json，build 时间快照）。点开任何板，你会被带去 #/worldbook 读最长最完整的原版。每一片叶子都能被 git show（卷 X = 世界的一大节）。"
            : "This wall is not a poster — every tile is a live carry of the world book's original prose (worldbook.json, snapshotted at build time). Open any tile and you'll land on #/worldbook with the longest, most complete rendition. Every leaf can be git shown (each volume = one whole class of the world's history)."}
        </p>
      </footer>
    </div>
  );
}
