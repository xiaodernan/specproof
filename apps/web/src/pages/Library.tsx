import { useMemo, useRef, useState } from "react";
import { useI18n } from "../i18n";
import library from "./library.json";
import "../styles/library.css";

/**
 * The Library — every volume of the world bible, in the same order as the
 * file, without reordering or omission. Counts are derived from library.json
 * at render time (never hard-coded), so a rebuilt bible cannot leave a stale
 * number on the page. Built from the world bible, machine-struck by
 * `scripts/build_library.py`.
 */

interface Volume {
  num: string;
  title: string;
  excerpt: string;
}

const ZH: Volume[] = library.zh as Volume[];
const EN: Volume[] = library.en as Volume[];

export default function Library() {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const volumes = zh ? ZH : EN;
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const itemRefs = useRef<Record<string, HTMLLIElement | null>>({});

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return volumes;
    return volumes.filter((volume) => `${volume.num} ${volume.title} ${volume.excerpt}`.toLowerCase().includes(q));
  }, [query, volumes]);

  // "Wander": jump to an arbitrary scroll in the whole bible. This is the
  // open-world door — a reader who does not know where to start lands on a
  // real volume every time, no ranking, no recommendation, no fabricated
  // content. Deterministic per click from Math.random; the set is the full
  // unfiltered library so every scroll is reachable.
  const wander = () => {
    if (!volumes.length) return;
    const target = volumes[Math.floor(Math.random() * volumes.length)];
    setQuery(""); // clear any filter so the target is guaranteed visible
    setOpen(target.num);
    window.setTimeout(() => {
      itemRefs.current[target.num]?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 0);
  };

  return (
    <div className="library-page">
      <div className="page-head">
        <h1>{zh ? "图 书 馆" : "THE LIBRARY"} <span className="library-en">SPECROOF BIBLE · {volumes.length} SCROLLS</span></h1>
        <div className="page-sub">
          {zh
            ? "每一卷都对着真实发生过的事；没有重排、没有删节；任何一条你想"  + "反驳，都能打开对应的 .md 找到同一页。"
            : "Every volume bears real events; nothing reordered, nothing pruned; any page you doubt is one .md away."}
        </div>
      </div>
      <label className="library-search" htmlFor="library-filter">
        <span className="visually-hidden">{zh ? "搜索卷宗" : "search the library"}</span>
        <input
          id="library-filter"
          type="search"
          className="library-filter"
          placeholder={zh ? "搜索卷号、卷名…" : "search scroll number or title…"}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          autoComplete="off"
          spellCheck={false}
        />
        <span className="library-count" aria-live="polite">{filtered.length} / {volumes.length}</span>
        <button type="button" className="library-toggle" onClick={wander} aria-label={zh ? "随机漫游一卷" : "wander to a random scroll"}>
          {zh ? "✦ 随机漫游" : "✦ Wander"}
        </button>
      </label>

      <ol className="library-list">
        {filtered.map((volume, index) => (
          <li
            key={`${volume.num}-${index}`}
            className="library-item"
            ref={(node) => { itemRefs.current[volume.num] = node; }}
          >
            <div className="library-row">
              <span className="library-num">{volume.num}</span>
              <div className="library-body">
                <div className="library-title">{volume.title}</div>
                <button
                  type="button"
                  className="library-toggle"
                  aria-expanded={open === volume.num}
                  onClick={() => setOpen(open === volume.num ? null : volume.num)}
                >
                  {open === volume.num ? (zh ? "收起 ▾" : "collapse ▾") : (zh ? "展开 ▸" : "expand ▸")}
                </button>
                {open === volume.num ? <p className="library-excerpt">{volume.excerpt}</p> : null}
              </div>
            </div>
          </li>
        ))}
      </ol>

      <div className="library-colophon">
        <p>
          {zh
            ? "此页由 scripts/build_library.py 落册，页面读 library.json — 不是 editor 编辑的，没有加工、没有翻译；完全对齐 SPECROOF_WORLD.md 与 SPECROOF_WORLD_EN.md 的实际字位。"
            : "This page is built by scripts/build_library.py; it reads library.json verbatim — no editor pass, no translation; byte-for-byte aligned with SPECROOF_WORLD.md and SPECROOF_WORLD_EN.md."}
        </p>
      </div>
    </div>
  );
}
