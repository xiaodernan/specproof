import { useState } from "react";
import { useI18n, type Locale } from "../i18n";
import { ATLAS_REGIONS, EXPEDITIONS, type AtlasRegionId } from "./atlas.copy";
import stats from "./repoStats.json";
import evidence from "./evidence.json";
import MidnightLamp from "./MidnightLamp";
import { ProductIcon } from "../ui/ProductIcon";
import "../styles/atlas.css";

/**
 * The Atlas — the Evidence Archipelago, drawn.
 *
 * The product's failure mode is not "too little to see", it is "too much and
 * no way to hold the whole"; this page exists so a newcomer can see the whole
 * continent in one glance, pick an island, and know exactly which halls are
 * inside it. Every room named here is a real route; every figure in the
 * landmarks strip is derived from repoStats.json (git ls-files) or the
 * ledger — nothing is art-directed.
 */

const pick = (rec: Record<Locale, string>, locale: Locale) => rec[locale];

/** Ledger sections — counted by build_repo_stats.py from the same `^## #\\d+` headings the chronicle parses. */
const LEDGER_SECTIONS = (stats as { ledger_sections?: number }).ledger_sections ?? 0;

export default function Atlas() {
  const { t, locale } = useI18n();
  const zh = locale === "zh";
  const [regionId, setRegionId] = useState<AtlasRegionId>("plain");
  const [roomPath, setRoomPath] = useState<string | null>(null);
  const region = ATLAS_REGIONS.find((r) => r.id === regionId) ?? ATLAS_REGIONS[1];

  const evidenceGreen = (evidence as unknown as { all: Array<{ total_ok: number }> }).all.reduce((n, r) => n + r.total_ok, 0);
  const evidenceRequests = (evidence as unknown as { all: Array<{ total: number }> }).all.reduce((n, r) => n + r.total, 0);
  const stressGreenShare = evidenceRequests > 0 ? `${Math.round((evidenceGreen / evidenceRequests) * 100)}%` : "—";
  const tiles = [
    { value: stressGreenShare, label: zh ? "本月压测 · 全绿份额" : "stress green share" },
    { value: `${evidenceRequests.toLocaleString()}`, label: zh ? "本月证据·请求数" : "exhibit requests" },
    { value: stats.repository_files.toLocaleString(), label: zh ? "跟踪文件" : "tracked files" },
    { value: stats.total_lines_of_source.toLocaleString(), label: zh ? "源码行数" : "source lines" },
    { value: stats.git_commit_count.toLocaleString(), label: zh ? "提交次数" : "commits" },
    { value: LEDGER_SECTIONS.toLocaleString(), label: zh ? "账本条目" : "ledger entries" },
    { value: stats.ledger_bytes_kB.toFixed(1) + " KB", label: zh ? "账本体积" : "ledger volume" },
    { value: (stats.world_bytes_zh / 1024).toFixed(1) + " KB", label: zh ? "中文铁证之书" : "Book of Iron · zh" },
    { value: (stats.world_bytes_en / 1024).toFixed(1) + " KB", label: zh ? "英文铁证之书" : "Book of Iron · en" },
  ];

  return (
    <div className="atlas-page">
      <div className="page-head">
        <h1>
          {zh ? "SpecProof 世界舆图" : "The SpecProof Atlas"}{" "}
          <span className="atlas-en">{zh ? "THE EVIDENCE ARCHIPELAGO" : "证据群岛"}</span>
        </h1>
        <div className="page-sub">
          {zh
            ? "三座岛、二十四个大厅、三条探险路线——这个世界大到永远走不完，但不该大到让你迷路。点击任意岛屿或厅点，右侧即展开该岛的全部细节。"
            : "Three islands, twenty-four halls, three expedition routes — big enough to never finish, never so big you get lost. Click an island, click a room-dot; the panel on the right unfolds everything inside."}
        </div>
      </div>

      {/* ── Island tabs (keyboard & screen-reader friendly) ── */}
      <div className="atlas-tabs" role="tablist" aria-orientation="horizontal">
        {ATLAS_REGIONS.map((r) => (
          <button
            key={r.id}
            role="tab"
            aria-selected={regionId === r.id}
            className={regionId === r.id ? "atlas-tab is-active" : "atlas-tab"}
            style={{ ["--accent" as string]: r.accent }}
            onClick={() => { setRegionId(r.id); setRoomPath(null); }}
          >
            <span className="atlas-tab-dot" aria-hidden="true" />
            {pick(r.name, locale)}
          </button>
        ))}
      </div>

      <div className="atlas-grid">
        {/* ── The map itself ── */}
        <div className="atlas-map-frame">
          <svg viewBox="0 0 1160 700" className="atlas-svg" role="group" aria-label={zh ? "SpecProof 证据群岛地图" : "SpecProof evidence archipelago map"}>
            <defs>
              <radialGradient id="atlas-sea" cx="50%" cy="36%" r="85%">
                <stop offset="0%" stopColor="#0e2233" />
                <stop offset="55%" stopColor="#081726" />
                <stop offset="100%" stopColor="#050d16" />
              </radialGradient>
              <pattern id="atlas-hatch" width="9" height="9" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
                <line x1="0" y1="0" x2="0" y2="9" stroke="rgba(255,255,255,.055)" strokeWidth="1.3" />
              </pattern>
              <filter id="atlas-soft" x="-20%" y="-20%" width="140%" height="140%">
                <feDropShadow dx="0" dy="10" stdDeviation="18" floodColor="#000000" floodOpacity="0.55" />
              </filter>
            </defs>

            {/* sea */}
            <rect x="10" y="10" width="1140" height="680" fill="url(#atlas-sea)" rx="4" />
            {/* cartographic frame: double hairline */}
            <rect x="10" y="10" width="1140" height="680" fill="none" stroke="#d4af37" strokeOpacity="0.75" strokeWidth="2.4" rx="4" />
            <rect x="20" y="20" width="1120" height="660" fill="none" stroke="#d4af37" strokeOpacity="0.4" strokeWidth="1" rx="2" />

            {/* faint meridian hairlines */}
            {[140, 310, 480, 650, 820, 990].map((x) => (
              <line key={x} x1={x} y1="22" x2={x} y2="678" stroke="#ffffff" strokeOpacity="0.035" strokeWidth="1" />
            ))}
            {[170, 250, 490, 570].map((y) => (
              <line key={y} x1="22" y1={y} x2="1138" y2={y} stroke="#ffffff" strokeOpacity="0.035" strokeWidth="1" />
            ))}

            {/* sea routes between islands (dashed) */}
            <path d="M 890 214 C 940 246, 760 250, 716 292" fill="none" stroke="#5eead4" strokeOpacity="0.5" strokeWidth="1.6" strokeDasharray="6 7" strokeLinecap="round" />
            <path d="M 664 466 C 700 492, 640 500, 600 522" fill="none" stroke="#5eead4" strokeOpacity="0.5" strokeWidth="1.6" strokeDasharray="6 7" strokeLinecap="round" />

            {/* islands */}
            {ATLAS_REGIONS.map((r) => (
              <g key={r.id}>
                <path
                  d={r.shape}
                  fill={r.accent}
                  fillOpacity={regionId === r.id ? 0.22 : 0.085}
                  stroke={r.accent}
                  strokeOpacity={regionId === r.id ? 0.95 : 0.45}
                  strokeWidth={regionId === r.id ? 2.2 : 1.3}
                  filter="url(#atlas-soft)"
                  className="atlas-island"
                  role="button"
                  tabIndex={0}
                  aria-pressed={regionId === r.id}
                  aria-label={pick(r.name, locale)}
                  onClick={() => { setRegionId(r.id); setRoomPath(null); }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setRegionId(r.id); setRoomPath(null); }
                  }}
                />
                <path d={r.shape} fill="url(#atlas-hatch)" pointerEvents="none" />
                <text
                  x={r.labelPos[0]} y={r.labelPos[1]}
                  textAnchor="middle"
                  className="atlas-island-label"
                  style={{ fill: r.accent }}
                  pointerEvents="none"
                >
                  {pick(r.name, locale)}
                </text>
                {/* room dots */}
                {r.rooms.map((room) => (
                  <g
                    key={room.path}
                    className={roomPath === room.path ? "atlas-dot is-active" : "atlas-dot"}
                    role="button"
                    tabIndex={0}
                    aria-label={t(room.navKey)}
                    onClick={() => { setRegionId(r.id); setRoomPath(room.path); }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setRegionId(r.id); setRoomPath(room.path); }
                    }}
                  >
                    <title>{t(room.navKey)}</title>
                    <circle className="atlas-dot-halo" cx={room.x} cy={room.y} r="14" fill={r.accent} />
                    <circle className="atlas-dot-core" cx={room.x} cy={room.y} r="5.6" fill={r.accent} stroke="#050d16" strokeWidth="1.6" />
                  </g>
                ))}
              </g>
            ))}

            {/* compass rose, top-right margin — N engraved inside the dial */}
            <g className="atlas-compass" transform="translate(1102,56)" aria-hidden="true">
              <circle r="26" fill="#081726" stroke="#d4af37" strokeOpacity="0.8" strokeWidth="1.4" />
              <circle r="19" fill="none" stroke="#d4af37" strokeOpacity="0.35" strokeWidth="0.7" />
              <line x1="-13" y1="0" x2="13" y2="0" stroke="#d4af37" strokeOpacity="0.55" strokeWidth="0.9" />
              <path d="M 0 -17 L 4.6 0 L 0 4.6 L -4.6 0 Z" fill="#d4af37" />
              <text y="15.5" textAnchor="middle" className="atlas-compass-n">N</text>
            </g>

            {/* scale bar — anchored to the real commit count */}
            <g className="atlas-scale" transform="translate(56,656)" aria-hidden="true">
              <rect x="0" y="0" width="70" height="4.5" fill="#d4af37" fillOpacity="0.85" />
              <rect x="70" y="0" width="70" height="4.5" fill="#d4af37" fillOpacity="0.45" />
              <rect x="140" y="0" width="70" height="4.5" fill="#d4af37" fillOpacity="0.85" />
              {[0, 70, 140, 210].map((x) => <line key={x} x1={x} y1="-4" x2={x} y2="9" stroke="#d4af37" strokeWidth="1.4" />)}
              <text x="0" y="16.5" className="atlas-scale-num">0</text>
              <text x="70" y="16.5" textAnchor="middle" className="atlas-scale-num">1,000</text>
              <text x="140" y="16.5" textAnchor="middle" className="atlas-scale-num">2,000</text>
              <text x="210" y="16.5" textAnchor="end" className="atlas-scale-num">{stats.git_commit_count.toLocaleString()}</text>
              <text x="222" y="4.6" className="atlas-scale-cap">{zh ? "提交" : "COMMITS"}</text>
            </g>

            {/* engraved caption, top-left margin */}
            <text x="48" y="15" className="atlas-engrave">THE EVIDENCE ARCHIPELAGO · EST. #130 · MMXXVI</text>
          </svg>
        </div>

        {/* ── Side panel: the selected island's halls ── */}
        <aside className="atlas-panel" style={{ ["--accent" as string]: region.accent }}>
          <div className="atlas-region-head">
            <p className="atlas-region-tag">{pick(region.tagline, locale)}</p>
            <h2>{pick(region.name, locale)} <span className="atlas-region-count">{region.rooms.length} {zh ? "厅" : "rooms"}</span></h2>
            <p className="atlas-region-lore">{pick(region.lore, locale)}</p>
          </div>
          <ul className="atlas-rooms">
            {region.rooms.map((room) => (
              <li key={room.path}>
                <a
                  href={`#/${room.path}`}
                  className={roomPath === room.path ? "atlas-room is-active" : "atlas-room"}
                  onMouseEnter={() => setRoomPath(room.path)}
                  onFocus={() => setRoomPath(room.path)}
                >
                  <span className="atlas-room-icon"><ProductIcon name={room.icon} size={17} /></span>
                  <span className="atlas-room-text">
                    <strong>{t(room.navKey)}</strong>
                    <small>{pick(room.desc, locale)}</small>
                  </span>
                  <span className="atlas-room-go"><ProductIcon name="arrow" size={14} /></span>
                </a>
              </li>
            ))}
          </ul>
        </aside>
      </div>

      {/* ── Three expedition routes ── */}
      <section className="atlas-expeditions">
        <h2>{zh ? "三条探险路线" : "Three expedition routes"}</h2>
        <div className="atlas-exp-grid">
          {EXPEDITIONS.map((e, i) => (
            <a key={e.href} href={e.href} className="atlas-exp-card">
              <span className="atlas-exp-num">{zh ? ["壹", "贰", "叁"][i] : ["01", "02", "03"][i]}</span>
              <span className="atlas-exp-body">
                <strong>{zh ? e.zhTitle : e.enTitle}</strong>
                <small>{zh ? e.zhBody : e.enBody}</small>
                <span className="atlas-exp-cta">{zh ? e.zhCta : e.enCta} <ProductIcon name="arrow" size={13} /></span>
              </span>
            </a>
          ))}
        </div>
      </section>

      {/* ── The Midnight Lamps: the audit's three lights ── */}
      <MidnightLamp />

      {/* ── Live landmarks: real numbers, re-derivable ── */}
      <section className="atlas-landmarks">
        <h2>{zh ? "活体地标" : "Living landmarks"} <span className="atlas-landmarks-note">{zh ? "全部由 git ls-files 与账本现推" : "all derived live from git ls-files & the ledger"}</span></h2>
        <div className="atlas-tile-row">
          {tiles.map((tile) => (
            <div key={tile.label} className="atlas-tile">
              <p className="atlas-tile-value">{tile.value}</p>
              <p className="atlas-tile-label">{tile.label}</p>
            </div>
          ))}
        </div>
        <p className="atlas-footnote">
          {zh
            ? "这张舆图会随主线生长：数字不是文案，是测量值——任何人跑 scripts/build_repo_stats.py 都能重算，对不上就是 bug。"
            : "This atlas ages with the trunk: these figures are measurements, not copy — anyone re-running scripts/build_repo_stats.py re-derives them; a mismatch is a bug."}
        </p>
      </section>
    </div>
  );
}
