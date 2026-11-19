import { useMemo, useState } from "react";
import { useI18n } from "../i18n";
import library from "./library.json";
import "../styles/library.css";

/**
 * The Library — every volume of the world bible, in the same order as the
 * file, without reordering or omission. 203 scrolls zh≡en. Built from the
 * world bible, machine-struck by `scripts/build_library.py`.
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
  const [open, setOpen] = useState<number | null>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return volumes;
    return volumes.filter((volume) => `${volume.num} ${volume.title} ${volume.excerpt}`.toLowerCase().includes(q));
  }, [query, volumes]);

  return (
    <div className="library-page">
      <div className="page-head">
        <h1>{zh ? "图 书 馆" : "THE LIBRARY"} <span className="library-en">SPECROOF BIBLE · 203 SCROLLS</span></h1>
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
      </label>

      <ol className="library-list">
        {filtered.map((volume, index) => (
          <li key={`${volume.num}-${index}`} className="library-item">
            <div className="library-row">
              <span className="library-num">{volume.num}</span>
              <div className="library-body">
                <div className="library-title">{volume.title}</div>
                <button
                  type="button"
                  className="library-toggle"
                  aria-expanded={open === index}
                  onClick={() => setOpen(open === index ? null : index)}
                >
                  {open === index ? (zh ? "收起 ▾" : "collapse ▾") : (zh ? "展开 ▸" : "expand ▸")}
                </button>
                {open === index ? <p className="library-excerpt">{volume.excerpt}</p> : null}
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
