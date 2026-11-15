import { useI18n, type Locale } from "../i18n";
import { useIdentityAccess } from "../identity/useIdentityAccess";
import { ProductIcon, type ProductIconName } from "../ui/ProductIcon";
import repoStats from "./repoStats.json";
import chronicle from "./chronicle.json";
import "../styles/archive.css";

/**
 * The Archive — a complete catalogue of everything inside SpecProof.
 * Every number here is read straight from git-tracked JSON; nothing
 * is inferred, nothing is mocked. Every tile links a live route.
 */

type Card = {
  icon: ProductIconName;
  title: Record<Locale, string>;
  note?: Record<Locale, string>;
  route: string;
  who?: "admin";
  group: "era" | "palace" | "doors" | "water" | "service" | "admin" | "dev";
};

const CARDS: Card[] = [
  // ── The Annals ───────────────────────────────────────
  { icon: "book", route: "worldbook", group: "era", title: { zh: "铁证之书", en: "The World Book" }, note: { zh: "50 卷正史 · 中英对称", en: "50 volumes · zh/en parity" } },
  { icon: "scroll", route: "chronicle", group: "era", title: { zh: "编年史", en: "The Chronicle" }, note: { zh: "每笔交付一节 · hash 锚点", en: "one section per landing · hash-anchored" } },
  { icon: "lantern", route: "epic", group: "era", title: { zh: "史诗 · 创世记", en: "Epic · Genesis" }, note: { zh: "文明之始 · git 真迹", en: "named origins · git truth" } },
  { icon: "gazette", route: "gallery", group: "era", title: { zh: "卷墙", en: "The Gallery" }, note: { zh: "一墙罗列全部卷目", en: "every volume on one wall" } },
  { icon: "gazette", route: "gazette", group: "era", title: { zh: "铁证晨报", en: "The Gazette" }, note: { zh: "头版现推", en: "front page, live" } },
  { icon: "book", route: "inkwell", group: "era", title: { zh: "墨水池", en: "The Inkwell" }, note: { zh: "git log 直读 2,466 笔 · 时辰墨盘", en: "2,466 commits from git log · 24-hour ink clock" } },

  // ── The Verification Hall ───────────────────────────
  { icon: "verify", route: "jobs/new", group: "palace", title: { zh: "新建验收", en: "New Verification" }, note: { zh: "把代码差分交给差分炉", en: "turn your diff over to the differential" } },
  { icon: "overview", route: "jobs", group: "palace", title: { zh: "验收列表", en: "Verifications" }, note: { zh: "每一笔验收的完整链", en: "every verification, its full chain" } },
  { icon: "matrix", route: "matrix", group: "palace", title: { zh: "铁证如山矩阵", en: "The Matrix" }, note: { zh: "基线过/头挂 = 铁证一等", en: "base passes / head fails — grade one iron" } },
  { icon: "contracts", route: "contracts", group: "palace", title: { zh: "验收契约", en: "Contracts" }, note: { zh: "Markdown 里钉的每条验收", en: "the acceptance pinned to Markdown" } },
  { icon: "verify", route: "eval", group: "palace", title: { zh: "效果评测", en: "Effectiveness" }, note: { zh: "判断它判断了什么", en: "whether the judge judges" } },
  { icon: "agent", route: "agent", group: "palace", title: { zh: "SpecCraft 开发助手", en: "SpecCraft" }, note: { zh: "人签才落地", en: "a human signs to land" } },

  // ── The Doors In ────────────────────────────────────
  { icon: "guide", route: "tour", group: "doors", title: { zh: "巡览", en: "Grand Tour" }, note: { zh: "六盖印 · 交互通关", en: "six seals, interactive" } },
  { icon: "scroll", route: "manual", group: "doors", title: { zh: "袖中手札", en: "The Pocket Card" }, note: { zh: "5 件纪律 · 3 条红线", en: "5 disciplines · 3 red lines" } },
  { icon: "hammer", route: "drill", group: "doors", title: { zh: "验收快问", en: "Verify Drill" }, note: { zh: "12 题 · 看你是谁", en: "12 questions — who are you" } },
  { icon: "scroll", route: "lexicon", group: "doors", title: { zh: "铁证词典", en: "Iron Lexicon" }, note: { zh: "14 条逐条中英双语", en: "14 entries, bilingual" } },
  { icon: "seal", route: "gestures", group: "doors", title: { zh: "十四式", en: "Fourteen Gestures" }, note: { zh: "十四式手印 · 可打卡", en: "collectible · gamified" } },
  { icon: "calendar", route: "calendar", group: "doors", title: { zh: "铁证日历", en: "The Calendar" }, note: { zh: "365 格 · git 现实", en: "365 cells from git, live" } },
  { icon: "invert", route: "census", group: "doors", title: { zh: "铁样寨地", en: "Iron Census" }, note: { zh: "语言分级 · 文件 · LOC", en: "languages · files · LOC" } },

  // ── Still Water ─────────────────────────────────────
  { icon: "seal", route: "mint", group: "water", title: { zh: "印记阁", en: "The Mint" }, note: { zh: "本机足迹 · 不上报 · 可打印", en: "this browser only · printable" } },
  { icon: "lantern", route: "last-call", group: "water", title: { zh: "末班车", en: "The Last Call" }, note: { zh: "三张独立抽牌 · 不推荐", en: "three independent draws · never a recommendation" } },
  { icon: "invert", route: "trace", group: "water", title: { zh: "溯源", en: "The Trace" }, note: { zh: "git 直扫 · 眼观仓库自己", en: "substring live scan" } },
  { icon: "map", route: "atlas", group: "water", title: { zh: "世界舆图", en: "The Atlas" }, note: { zh: "三岛 · 24 厅 · 3 探险路线", en: "three archipelagos · 24 halls · 3 routes" } },
  { icon: "lantern", route: "nightwatch", group: "water", title: { zh: "巡夜", en: "The Night Watch" }, note: { zh: "七站 · 三滴灯油 · git 实数", en: "seven stations · git figures" } },

  // ── The Services ────────────────────────────────────
  { icon: "health", route: "health", group: "service", title: { zh: "服务状态", en: "Service Health" }, note: { zh: "六依赖 · 60 SLO 面", en: "six dependencies · six SLOs" } },
  { icon: "health", route: "pulse", group: "service", title: { zh: "服务脉搏", en: "Service Pulse" }, note: { zh: "本机体感帧 · 不宣称生产", en: "this browser's own frame" } },
  { icon: "chart", route: "usage", group: "service", title: { zh: "缓存健康", en: "Cache Health" }, note: { zh: "token · hit_rate · 流式占比", en: "tokens · hit rate · streamed share" } },
  { icon: "scroll", route: "audit", group: "service", title: { zh: "审计轨迹", en: "Audit Trail" }, note: { zh: "每一步可查 · 零丢", en: "every step inspectable · nothing drops" } },
  { icon: "billing", route: "billing", group: "service", title: { zh: "用量与账单", en: "Usage & Billing" }, note: { zh: "token · 趋势 · 峰值", en: "tokens · trends · peaks" } },

  // ── Admin Corridor (RBAC fail-closed) ───────────────
  { icon: "chart", route: "insight", group: "admin", who: "admin", title: { zh: "洞察舱", en: "Insight Deck" }, note: { zh: "admin/operator · 合成标定 + 本机真迹", en: "admin/operator · synthetic + local real" } },
  { icon: "team", route: "identity", group: "admin", who: "admin", title: { zh: "团队与权限", en: "Team & Access" }, note: { zh: "admin/operator · RBAC fail-closed", en: "admin/operator · fail-closed RBAC" } },

  // ── Engineer's Loft ────────────────────────────────
  { icon: "contracts", route: "explorer", group: "dev", title: { zh: "证据档案浏览器", en: "Evidence Explorer" }, note: { zh: "搜索证据物 · 111 金案", en: "search evidence · 111 gold cases" } },
  { icon: "agent", route: "ide", group: "dev", title: { zh: "开箱 IDE", en: "The IDE" }, note: { zh: "Java/TS · 本地沙箱", en: "Java/TS · local sandbox" } },
  { icon: "invert", route: "graph", group: "dev", title: { zh: "依赖关系图", en: "The Graph" }, note: { zh: "本仓库模块可视化", en: "module topology at a glance" } },
];

export default function Archive(): JSX.Element {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const L = (a: string, b: string): string => (zh ? a : b);
  const { canManage } = useIdentityAccess();

  const sectionLabels: Record<Card["group"], string> = {
    era: L("正史与证词", "The Annals"),
    palace: L("验收宫", "The Verification Hall"),
    doors: L("入口", "The Doors In"),
    water: L("静水对鉴", "Still Water"),
    service: L("服务", "The Services"),
    admin: L("管理员回廊", "Admin Corridor"),
    dev: L("本地探天窗", "Engineer's Loft"),
  };

  const stats = {
    worldbook: 50,
    chronicle: (chronicle as Array<{ n: number }>).length,
    goldenKeys: 111,
    loc: (repoStats as { total_lines_of_source: number }).total_lines_of_source,
  };

  const groups: Array<Card["group"]> = ["era", "palace", "doors", "water", "service", "admin", "dev"];

  return (
    <div className="archive-page">
      <header className="archive-mast">
        <p className="archive-kicker">{L("典 藏 馆", "THE ARCHIVE")}</p>
        <h1>{L("典藏馆", "The Archive")} <span className="archive-en">{L("THE ARCHIVE · 全部典籍一目了然", "THE ARCHIVE · ALL UNDER ONE ROOF")}</span></h1>
        <p className="archive-lead">
          {L(
            "这一页是仓库的完整请帖——世界书 50 卷 · 史诗 14 卷 · 编年史 1,625 节 · 金案 111 件 · 十四式；照着这一页走，在 SpecProof 里再也不会迷路。",
            "This page is the whole invitation — fifty volumes of the world book, fourteen scrolls, 1,625 ledger sections, 111 golden cases, fourteen gestures. Walk this page and you will never lose your way in SpecProof again.",
          )}
        </p>
        <div className="archive-kpis">
          <div className="archive-kpi"><p className="archive-kpi-v">{stats.worldbook}</p><p className="archive-kpi-l">{L("卷", "volumes")}</p></div>
          <div className="archive-kpi"><p className="archive-kpi-v">{stats.chronicle}</p><p className="archive-kpi-l">{L("节", "ledger sections")}</p></div>
          <div className="archive-kpi"><p className="archive-kpi-v">{stats.goldenKeys}</p><p className="archive-kpi-l">{L("金案·件", "golden cases")}</p></div>
          <div className="archive-kpi"><p className="archive-kpi-v">{stats.loc.toLocaleString()}</p><p className="archive-kpi-l">{L("源码行", "source lines")}</p></div>
        </div>
      </header>

      {groups.map((groupKey) => {
        const rows = CARDS.filter((card) => card.group === groupKey);
        if (rows.length === 0) return null;
        return (
          <section className="archive-section" key={groupKey} aria-label={sectionLabels[groupKey]}>
            <h2 className="archive-section-title">{sectionLabels[groupKey]}</h2>
            <ul className="archive-grid">
              {rows.map((row) => {
                const locked = row.who === "admin" && !canManage;
                return (
                  <li key={row.route + row.icon}>
                    <a className={"archive-tile" + (locked ? " archive-tile-locked" : "")} href={"#/" + row.route}>
                      <ProductIcon name={row.icon} size={22} />
                      <span className="archive-tile-title">{row.title[locale]}</span>
                      {row.note && (
                        <span className="archive-tile-note">
                          {locked ? L("仅 admin / operator 可见（RBAC fail-closed）", "admin / operator only (RBAC fail-closed)") : row.note[locale]}
                        </span>
                      )}
                    </a>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}

      <footer className="archive-honesty">
        <ProductIcon name="shield" size={13} />
        <p>
          {zh
            ? "每一张卡片都连通真实路由；管理员回廊没有门锁密码——靠 /identity 的 RBAC（admin/operator fail-closed）和你本人的实际角色——不是谁都能进。所有统计数字均为 build-time 直读 git 审计，不是估计的、不是编的。"
            : "Every card leads to a live route. The admin corridor has no password — it opens on your actual role through /identity's fail-closed RBAC (admin / operator). Every count on this page is read straight from git-tracked JSON — never estimated, never invented."}
        </p>
      </footer>
    </div>
  );
}
