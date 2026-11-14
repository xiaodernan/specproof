import { useEffect, useMemo, useRef, useState } from "react";
import { marked } from "marked";
import { useI18n, type Locale } from "../i18n";
import worldbook from "./worldbook.json";
import "../styles/worldbook.css";

/**
 * The Reading Room — the Book of Iron Evidence, bound and shelved inside the app.
 *
 * The world book (docs/world/SPECROOF_WORLD.md + EN mirror) is the project's
 * 正史. Until now readers had to open the raw Markdown in a terminal. This
 * page is its reading room: 22 volumes + appendices, both languages
 * pixel-parallel, searchable, with reading progress persisted locally.
 *
 * Nothing here is invented: every paragraph rendered below comes from the
 * repository's own world bible, rebuilt by scripts/build_worldbook.py.
 */

type Volume = { id: string; num: string; title: string; markdown: string };
type Book = { title: string; volumes: Volume[] };
type FontSize = "s" | "m" | "l";

const BOOK = worldbook.locales as unknown as Record<Locale, Book>;

const READ_KEY = "specproof_worldbook_read";
const FONT_KEY = "specproof_worldbook_font";

function loadReadSet(): Set<string> {
  try {
    const raw = window.localStorage.getItem(READ_KEY);
    const ids = raw ? (JSON.parse(raw) as string[]) : [];
    return new Set(Array.isArray(ids) ? ids : []);
  } catch {
    return new Set();
  }
}

function saveReadSet(set: Set<string>) {
  try {
    window.localStorage.setItem(READ_KEY, JSON.stringify([...set]));
  } catch {
    /* storage unavailable — progress lives for the session */
  }
}

function escapeRe(literal: string): string {
  return literal.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Highlight `query` inside rendered HTML, skipping tags themselves. */
function highlightHtml(html: string, query: string): string {
  const q = query.trim();
  if (!q) return html;
  const re = new RegExp(escapeRe(q), "gi");
  return html
    .split(/(<[^>]+>)/g)
    .map((part) => (part.startsWith("<") ? part : part.replace(re, (m) => `<mark class="wb-hit">${m}</mark>`)))
    .join("");
}

export default function WorldBook() {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const book = BOOK[locale] ?? BOOK.zh;

  const [activeId, setActiveId] = useState<string>(book.volumes[0]?.id ?? "front");
  const [query, setQuery] = useState("");
  const [readIds, setReadIds] = useState<Set<string>>(() => loadReadSet());
  const [fontSize, setFontSize] = useState<FontSize>(() => {
    try {
      const raw = window.localStorage.getItem(FONT_KEY);
      return raw === "s" || raw === "l" ? raw : "m";
    } catch {
      return "m";
    }
  });
  const articleTopRef = useRef<HTMLDivElement>(null);

  const activeIndex = Math.max(0, book.volumes.findIndex((v) => v.id === activeId));
  const active = book.volumes[activeIndex] ?? book.volumes[0];

  // When the locale (book) changes, keep the same volume index selected.
  useEffect(() => {
    setActiveId((prev) => {
      if (book.volumes.some((v) => v.id === prev)) return prev;
      return book.volumes[Math.min(activeIndex, book.volumes.length - 1)]?.id ?? "front";
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locale]);

  const html = useMemo(() => {
    const rendered = marked.parse(active?.markdown ?? "", { async: false }) as string;
    return highlightHtml(rendered, query);
  }, [active?.markdown, query]);

  const visibleVolumes = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return book.volumes;
    return book.volumes.filter((v) =>
      `${v.num} ${v.title} ${v.markdown}`.toLowerCase().includes(q),
    );
  }, [book.volumes, query]);

  const matchCount = useMemo(() => {
    const q = query.trim();
    if (!q) return 0;
    const re = new RegExp(escapeRe(q), "gi");
    return (active?.markdown.match(re) ?? []).length;
  }, [active?.markdown, query]);

  const total = book.volumes.length;
  const readCount = book.volumes.filter((v) => readIds.has(v.id)).length;
  const pct = total ? Math.round((readCount / total) * 100) : 0;

  function toggleRead(id: string) {
    setReadIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      saveReadSet(next);
      return next;
    });
  }

  function goTo(id: string) {
    setActiveId(id);
    articleTopRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function surprise() {
    const pool = book.volumes.filter((v) => v.id !== active?.id);
    const pickV = pool[Math.floor(Math.random() * pool.length)];
    if (pickV) goTo(pickV.id);
  }

  function changeFont(next: FontSize) {
    setFontSize(next);
    try {
      window.localStorage.setItem(FONT_KEY, next);
    } catch {
      /* ignore */
    }
  }

  const isRead = active ? readIds.has(active.id) : false;

  return (
    <div className="worldbook-page">
      {/* ── Masthead ─────────────────────────────────────────── */}
      <div className="wb-masthead">
        <div className="wb-masthead-row">
          <div>
            <p className="wb-kicker">{zh ? "铁 证 之 书 · 正 史" : "THE BOOK OF IRON EVIDENCE · THE OFFICIAL HISTORY"}</p>
            <h1 className="wb-title">{zh ? "世界书 · 铁证书房" : "The Reading Room"}<span className="wb-title-en">{zh ? "THE READING ROOM" : "铁证书房"}</span></h1>
          </div>
          <div className="wb-controls">
            <button className="wb-icon-btn" onClick={surprise} title={zh ? "随机开一卷" : "Open a random volume"} aria-label={zh ? "随机开一卷" : "Open a random volume"}>
              <span aria-hidden="true">⚄</span>
            </button>
            <div className="wb-font" role="group" aria-label={zh ? "字号" : "Font size"}>
              <button className={fontSize === "s" ? "is-active" : ""} onClick={() => changeFont("s")} aria-label="A−">A<small>−</small></button>
              <button className={fontSize === "m" ? "is-active" : ""} onClick={() => changeFont("m")} aria-label="A">A</button>
              <button className={fontSize === "l" ? "is-active" : ""} onClick={() => changeFont("l")} aria-label="A+">A<small>+</small></button>
            </div>
          </div>
        </div>
        <p className="wb-lead">
          {zh
            ? "二十二卷正史 + 附录，中英对照，一字不虚——每卷所言皆可拿去和仓库逐字对照。读到哪里，哪里就是你的。"
            : "Twenty-two volumes of the official history plus appendices, bilingual and pixel-parallel. Nothing herein that cannot be checked against the repository. Wherever you have read is yours."}
        </p>
      </div>

      <div className="wb-grid">
        {/* ── Volume rail ─────────────────────────────────────── */}
        <aside className="wb-sidebar" aria-label={zh ? "目录" : "Table of contents"}>
          <div className="wb-bookplate">
            <div className="wb-bookplate-emblem" aria-hidden="true">铁</div>
            <div>
              <p className="wb-bookplate-title">{book.title}</p>
              <p className="wb-bookplate-sub">{zh ? "SpecProof 创世记 · 永不结卷" : "SpecProof's genesis · never sealed"}</p>
            </div>
          </div>

          <label className="wb-search">
            <span className="wb-search-icon" aria-hidden="true">⌕</span>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={zh ? "搜索全书（例：base_pass_head_fail）…" : "Search the book (e.g. base_pass_head_fail)…"}
              aria-label={zh ? "搜索全书" : "Search the whole book"}
            />
            {query && <button className="wb-search-clear" onClick={() => setQuery("")} aria-label={zh ? "清空" : "Clear"}>×</button>}
          </label>

          {query && (
            <p className="wb-search-meta" role="status">
              {zh
                ? `找到 ${visibleVolumes.length} 卷含「${query.trim()}」；当前卷命中 ${matchCount} 处`
                : `${visibleVolumes.length} volume(s) match “${query.trim()}”; ${matchCount} hit(s) in this volume`}
            </p>
          )}

          <div className="wb-progress" aria-label={zh ? "阅读进度" : "Reading progress"}>
            <div className="wb-progress-track">
              <div className="wb-progress-fill" style={{ width: `${pct}%` }} />
            </div>
            <p className="wb-progress-text">{zh ? `已读 ${readCount} / ${total} 卷 · ${pct}%` : `${readCount} / ${total} volumes read · ${pct}%`}</p>
          </div>

          <nav className="wb-volumes">
            {visibleVolumes.length === 0 && (
              <p className="wb-empty">{zh ? "全书里没有这个词条。" : "No such word in the whole book."}</p>
            )}
            {visibleVolumes.map((v) => {
              const isActive = v.id === active?.id;
              const read = readIds.has(v.id);
              return (
                <button
                  key={v.id}
                  className={isActive ? "wb-volume is-active" : "wb-volume"}
                  onClick={() => goTo(v.id)}
                  aria-current={isActive ? "true" : undefined}
                >
                  <span className="wb-volume-num">{v.num || "序"}</span>
                  <span className="wb-volume-title">{v.title}</span>
                  <span className={read ? "wb-volume-read is-read" : "wb-volume-read"} aria-hidden="true">{read ? "✓" : ""}</span>
                </button>
              );
            })}
          </nav>
        </aside>

        {/* ── The reading desk ────────────────────────────────── */}
        <article className={`wb-article wb-font-${fontSize}`}>
          <div className="wb-breadcrumb" ref={articleTopRef}>
            <span>{zh ? `第 ${activeIndex + 1} / ${total} 卷` : `Volume ${activeIndex + 1} of ${total}`}</span>
            <span className="wb-breadcrumb-dot" aria-hidden="true">·</span>
            <span className="wb-breadcrumb-title">{active?.num} {active?.title}</span>
            <button className={isRead ? "wb-mark is-read" : "wb-mark"} onClick={() => active && toggleRead(active.id)}>
              {isRead ? (zh ? "✓ 已读完本卷" : "✓ Read") : (zh ? "标记本卷为已读" : "Mark as read")}
            </button>
          </div>

          <div className="wb-prose" dangerouslySetInnerHTML={{ __html: html }} />

          <div className="wb-pager">
            <button className="wb-pager-btn" disabled={activeIndex <= 0} onClick={() => goTo(book.volumes[activeIndex - 1]?.id)}>
              ← {zh ? "上一卷" : "Previous"}
            </button>
            <button className="wb-pager-btn wb-pager-btn-next" disabled={activeIndex >= total - 1} onClick={() => goTo(book.volumes[activeIndex + 1]?.id)}>
              {zh ? "下一卷" : "Next"} →
            </button>
          </div>
        </article>
      </div>
    </div>
  );
}
