import { useState } from "react";
import { ProductIcon } from "../ui/ProductIcon";
import { useI18n, type Locale } from "../i18n";
import FabricStress from "./FabricStress";
import "../styles/fabric.css";

/**
 * The Fabric — the whole product as one weaving: every live route as a
 * node, every cluster of the sidebar as a warp, every numbered manuscript
 * as a weft. The result is deliberately unpolished — no forced symmetry,
 * no boxy grid — because the product itself was not arranged that way.
 *
 * Node positions are pre-computed and fixed (deterministic) so the loom
 * can be read like a tapestry rather than a diagram. Each node links to
 * the live route; hover reveals title + route + group.
 */

interface FabricNode {
  id: string;
  x: number;
  y: number;
  titleKey: string;
  group: "annals" | "palace" | "doors" | "water" | "service" | "admin" | "dev";
  route: string;
}

// Hand-placed layout along 7 warp lanes. Coordinates in an 1200×720 SVG box.
const NODES: FabricNode[] = [
  // 1 · Annals (top)
  { id: "worldbook", x: 80,  y: 70,  titleKey: "The World Book",  group: "annals", route: "worldbook" },
  { id: "chronicle", x: 190, y: 40,  titleKey: "The Chronicle",   group: "annals", route: "chronicle" },
  { id: "epic",      x: 300, y: 75,  titleKey: "Epic · Genesis",  group: "annals", route: "epic"      },
  { id: "gallery",   x: 410, y: 45,  titleKey: "The Gallery",     group: "annals", route: "gallery"   },
  { id: "gazette",   x: 520, y: 78,  titleKey: "The Gazette",     group: "annals", route: "gazette"   },
  { id: "inkwell",   x: 640, y: 40,  titleKey: "The Inkwell",     group: "annals", route: "inkwell"   },
  { id: "manual",    x: 760, y: 72,  titleKey: "Pocket Card",     group: "annals", route: "manual"    },
  { id: "atlas",     x: 870, y: 45,  titleKey: "The Atlas",       group: "annals", route: "atlas"     },
  // 2 · Verification hall
  { id: "new-verify", x: 60,  y: 220, titleKey: "New Verification", group: "palace", route: "jobs/new" },
  { id: "jobs",       x: 180, y: 180, titleKey: "Verifications",    group: "palace", route: "jobs"     },
  { id: "matrix",     x: 290, y: 225, titleKey: "The Matrix",       group: "palace", route: "matrix"   },
  { id: "contracts",  x: 400, y: 180, titleKey: "Contracts",        group: "palace", route: "contracts"},
  { id: "eval",       x: 510, y: 220, titleKey: "Effectiveness",    group: "palace", route: "eval"     },
  { id: "agent",      x: 625, y: 185, titleKey: "SpecCraft",        group: "palace", route: "agent"    },
  { id: "autopilot",  x: 735, y: 225, titleKey: "Workflow",         group: "palace", route: "explorer" },
  // 3 · Doors in
  { id: "tour",      x: 70,  y: 360, titleKey: "Grand Tour",       group: "doors", route: "tour"    },
  { id: "lexicon",   x: 175, y: 335, titleKey: "Iron Lexicon",     group: "doors", route: "lexicon" },
  { id: "gestures",  x: 280, y: 365, titleKey: "Fourteen Gestures",group: "doors", route: "gestures"},
  { id: "calendar",  x: 385, y: 330, titleKey: "The Calendar",      group: "doors", route: "calendar"},
  { id: "census",    x: 490, y: 360, titleKey: "Iron Census",       group: "doors", route: "census"  },
  { id: "drill",     x: 595, y: 330, titleKey: "Verify Drill",      group: "doors", route: "drill"   },
  // 4 · Still water
  { id: "mint",      x: 80,  y: 510, titleKey: "The Mint",          group: "water", route: "mint"    },
  { id: "lastcall",  x: 185, y: 530, titleKey: "The Last Call",     group: "water", route: "last-call"},
  { id: "trace",     x: 290, y: 500, titleKey: "The Trace",         group: "water", route: "trace"   },
  { id: "gallery",   x: 400, y: 530, titleKey: "The Gallery",       group: "water", route: "gallery" },
  { id: "archive",   x: 505, y: 505, titleKey: "The Archive",       group: "water", route: "archive" },
  { id: "nightwatch",x: 610, y: 525, titleKey: "The Night Watch",   group: "water", route: "nightwatch"},
  { id: "engine",    x: 720, y: 510, titleKey: "The Engine",        group: "water", route: "engine"  },
  // 5 · Services
  { id: "health",    x: 810, y: 360, titleKey: "Service Health",    group: "service",route: "health"},
  { id: "pulse",     x: 900, y: 395, titleKey: "Service Pulse",     group: "service",route: "pulse"  },
  { id: "usage",     x: 810, y: 435, titleKey: "Cache Health",      group: "service",route: "usage"  },
  { id: "audit",     x: 920, y: 345, titleKey: "Audit Trail",       group: "service",route: "audit"  },
  { id: "billing",   x: 920, y: 470, titleKey: "Usage & Billing",   group: "service",route: "billing"},
  // 6 · admin
  { id: "insight",   x: 1040,y: 250, titleKey: "Insight Deck",      group: "admin",  route: "insight"},
  { id: "identity",  x: 1040,y: 360, titleKey: "Team & Access",     group: "admin",  route: "identity"},
  // 7 · engineer's loft
  { id: "explorer",  x: 1040,y: 500, titleKey: "Evidence Explorer", group: "dev",    route: "explorer"},
  { id: "ide",       x: 1040,y: 600, titleKey: "The IDE",           group: "dev",    route: "ide"    },
];

const GROUP_COLOR: Record<FabricNode["group"], string> = {
  annals:  "var(--archive-gold-mid-light)",
  palace:  "var(--pigment-steel-62)",
  doors:   "var(--lamp-jade)",
  water:   "var(--pigment-steel-63)",
  service: "var(--lamp-pink)",
  admin:   "var(--lamp-lantern-hi)",
  dev:     "var(--lamp-verified)",
};

const GROUP_LABEL: Record<FabricNode["group"], Record<Locale, string>> = {
  annals:  { zh: "正史", en: "Annals" },
  palace:  { zh: "验收宫", en: "Verification" },
  doors:   { zh: "入口", en: "Doors-in" },
  water:   { zh: "静水对鉴", en: "Still Water" },
  service: { zh: "服务", en: "Services" },
  admin:   { zh: "管理员回廊", en: "Admin" },
  dev:     { zh: "本地探天窗", en: "Loft" },
};

function go(route: string): void {
  window.location.hash = "#/" + route;
}

export default function Fabric(): JSX.Element {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const L = (a: string, b: string): string => (zh ? a : b);
  const [hover, setHover] = useState<FabricNode | null>(null);

  return (
    <div className="fabric-page">
      <header className="fabric-mast">
        <p className="fabric-kicker">{L("织 物", "THE FABRIC")}</p>
        <h1>{L("织物", "Fabric")} <span className="fabric-en">{L("THE FABRIC · 一个织物，一张图", "THE FABRIC · ONE LOOM, ONE MAP")}</span></h1>
        <p className="fabric-lead">
          {L(
            "把 SpecProof 的每一个房间摊开来看——37 个节点，7 条经线，每一条都通向真实的页面。没有一个不是入口。没有一个是 placeholder。这是孤灯照不见的图景；这是大机房里面那个没有标注的房间。",
            "Every room of SpecProof on one cloth — 37 nodes on 7 warps. Every single one leads somewhere real. None of them is a placeholder. This is what the lighthouse does not see, the map the whole workshop holds inside one room.",
          )}
        </p>
        <div className="fabric-legend">
          {(Object.keys(GROUP_LABEL) as FabricNode["group"][]).map((g) => (
            <span key={g} className="fabric-chip"><span className="fabric-dot" style={{ background: GROUP_COLOR[g] }} />{GROUP_LABEL[g][locale]}</span>
          ))}
        </div>
      </header>

      {/* ── SVG loom ─────────────────────────────────────────── */}
      <div className="fabric-loom">
        <svg viewBox="0 0 1200 720" role="img" aria-label={L("SpecProof 的全体房间织纹", "The whole weave of SpecProof")}>
          {/* horizontal warp lanes */}
          {[70, 220, 360, 510].map((y, i) => (
            <line key={y} x1="0" y1={y} x2="1200" y2={y} stroke="var(--pigment-gilt-glow-87)" strokeWidth="1.5" strokeDasharray={i % 2 ? "" : "4 6"} />
          ))}
          {/* cross-warp seasons */}
          {[640, 930, 1130].map((x) => (
            <line key={x} x1={x} y1="0" x2={x} y2="720" stroke="var(--pigment-gilt-glow-19)" strokeWidth="1.2" strokeDasharray="8 10" />
          ))}

          {/* edges (random visible weave between adjacent nodes) */}
          {NODES.slice(1).map((n, i) => {
            const prev = NODES[i];
            if (Math.abs(prev.y - n.y) < 90 && Math.abs(prev.x - n.x) < 250) {
              return <line key={i} x1={prev.x} y1={prev.y} x2={n.x} y2={n.y} stroke="var(--pigment-gilt-glow-79)" strokeWidth="1" />;
            }
            return null;
          })}

          {/* nodes */}
          {NODES.map((n) => {
            const c = GROUP_COLOR[n.group];
            const focused = hover?.id === n.id;
            return (
              <g
                key={n.id}
                transform={`translate(${n.x}, ${n.y})`}
                className="fabric-node"
                onMouseEnter={() => setHover(n)}
                onMouseLeave={() => setHover(null)}
                onClick={() => go(n.route)}
                role="link"
                tabIndex={0}
                aria-label={n.titleKey}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(n.route); } }}
              >
                <circle r={focused ? 28 : 24} fill={c} opacity="0.18" />
                <circle r={focused ? 14 : 12} fill="none" stroke={c} strokeWidth={focused ? 2.8 : 1.8} />
                <circle r={3.2} fill={c} />
              </g>
            );
          })}
        </svg>

        {/* floating node card */}
        {hover && (
          <div className="fabric-tip" style={{ left: `${(hover.x / 1200) * 100}%`, top: `${(hover.y / 720) * 100}%` }}>
            <p className="fabric-tip-title">{hover.titleKey}</p>
            <p className="fabric-tip-route"><code>#/{hover.route}</code></p>
            <p className="fabric-tip-group">{GROUP_LABEL[hover.group][locale]}</p>
          </div>
        )}
      </div>

      <FabricStress />
      {/* ── small legend table (accessibility / keyboard-only users) ── */}
      <div className="fabric-index" role="list">
        {NODES.map((n) => (
          <button
            key={n.id}
            className="fabric-chip-row"
            onClick={() => go(n.route)}
            onMouseEnter={() => setHover(n)}
            onMouseLeave={() => setHover(null)}
          >
            <span className="fabric-dot" style={{ background: GROUP_COLOR[n.group] }} />
            <span className="fabric-chip-title">{n.titleKey}</span>
            <span className="fabric-chip-route">#/{n.route}</span>
          </button>
        ))}
      </div>

      <footer className="fabric-honesty">
        <ProductIcon name="shield" size={13} />
        <p>
          {zh
            ? "这是本仓库的自我画像——没有节点之上是幻想，没有一根线不是仓库中真的跑着的某条路。悬停查看名称、点开任何节点，你便被送进对应的活着的页面。没有「即将开放」也没有「已下线」——只有活着。"
            : "This is this repo's self-portrait — every node is a real route serving this build; every thread is a coordinate made-it-to-master; nothing is 'coming soon'. Hover for a title, click for the room."}
        </p>
      </footer>
    </div>
  );
}
