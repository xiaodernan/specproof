import type { Locale } from "../i18n";
import type { ProductIconName } from "../ui/ProductIcon";

/**
 * The Atlas — page-local copy for the Evidence Archipelago map.
 * Every route named here is a real route mounted in App.tsx; every number in
 * the live landmarks strip comes from repoStats.json / chronicle.json — none
 * of it is art-directed prose.
 */

export type AtlasRegionId = "north" | "plain" | "south";

export interface AtlasRoom {
  /** Route as mounted in App.tsx (no leading slash). */
  path: string;
  /** i18n key of the sidebar label — reused so the map never invents names. */
  navKey: string;
  icon: ProductIconName;
  desc: Record<Locale, string>;
  /** Dot position inside the 1160×700 viewBox. */
  x: number;
  y: number;
}

export interface AtlasRegion {
  id: AtlasRegionId;
  name: Record<Locale, string>;
  tagline: Record<Locale, string>;
  lore: Record<Locale, string>;
  accent: string;
  /** Island silhouette — stylized, not geographic. */
  shape: string;
  labelPos: [number, number];
  rooms: AtlasRoom[];
}

export const ATLAS_REGIONS: AtlasRegion[] = [
  {
    id: "north",
    name: { zh: "工作台高原", en: "The Workspace Highlands" },
    tagline: { zh: "每天出入的大门", en: "The gate you pass every day" },
    lore: {
      zh: "验收单从这里出生、判定回到这里落座。看板、Jobs、AI 开放石、史诗竹简与巡览阶梯——五个厅，每一间都坐落在「今天该做什么」的时区上。",
      en: "Where a verification is born and a verdict comes to rest. The board, the Jobs list, the AI forge, the epic scrolls and the tour switchbacks — five halls in the timezone of “what today demands”.",
    },
    accent: "#2dd4bf",
    shape: "M 128 122 C 200 72, 360 78, 470 92 C 600 108, 760 64, 900 88 C 1010 106, 1110 112, 1122 152 C 1130 192, 1010 228, 850 232 C 650 236, 380 240, 220 230 C 120 222, 42 180, 66 142 C 80 126, 100 126, 128 122 Z",
    labelPos: [600, 218],
    rooms: [
      { path: "dashboard", navKey: "nav.dashboard", icon: "overview", x: 175, y: 150,
        desc: { zh: "今天的验收航迹——未决 BLOCKER、进行中的判定、刚落座的结论", en: "Today's verification trail — open blockers, in-flight verdicts, landed conclusions" } },
      { path: "jobs", navKey: "nav.jobs", icon: "verify", x: 350, y: 128,
        desc: { zh: "验收单列表——点任一行进详情，每条都带 base/head 指纹", en: "The verification ledger — every row opens to base/head fingerprints" } },
      { path: "agent", navKey: "nav.agent", icon: "agent", x: 525, y: 152,
        desc: { zh: "SpecCraft 铁匠工坊——让 AI 写代码、自我修复、并给出证据", en: "The SpecCraft forge — let the AI write, self-repair and show its evidence" } },
      { path: "epic", navKey: "nav.epic", icon: "guide", x: 705, y: 120,
        desc: { zh: "十二卷竹简创世记——每一卷都锚定真实 git 提交", en: "Twelve scrolls of genesis — every scroll pinned to real git commits" } },
      { path: "tour", navKey: "nav.tour", icon: "scroll", x: 890, y: 158,
        desc: { zh: "六盖印新手巡览——盖完六个印，你才算入门", en: "The six-stamp grand tour — six stamps and you are initiated" } },
    ],
  },
  {
    id: "plain",
    name: { zh: "证据平原", en: "The Evidence Plains" },
    tagline: { zh: "十三间铁证大厅", en: "Thirteen halls of iron evidence" },
    lore: {
      zh: "从词典到法典、从铸炉到河流——这是 SpecProof 的意义本身。每一间大厅的展品、判词、轨迹都能被任何读到的人复算：脚本、账本、git，三件套全都公开在仓库里。",
      en: "From the lexicon to the seals, from the forge to the river — this is SpecProof's meaning itself. Every exhibit, verdict and trace in these halls can be re-derived by any reader: script, ledger, git — all three are in the open.",
    },
    accent: "#818cf8",
    shape: "M 92 316 C 230 272, 400 284, 560 290 C 720 296, 900 262, 1010 276 C 1100 287, 1122 346, 1110 404 C 1092 464, 880 476, 620 476 C 380 476, 180 470, 95 450 C 25 432, 8 360, 50 332 Z",
    labelPos: [435, 462],
    rooms: [
      { path: "lexicon", navKey: "nav.lexicon", icon: "guide", x: 140, y: 322,
        desc: { zh: "铁证词典——十四个别人不懂、这里必须懂的词", en: "The iron lexicon — fourteen words outsiders never learned" } },
      { path: "museum", navKey: "nav.museum", icon: "scroll", x: 268, y: 352,
        desc: { zh: "铁证展厅——十二件被判过、也活过下来的真案例", en: "The evidence museum — twelve real cases that were tried and survived" } },
      { path: "gestures", navKey: "nav.gestures", icon: "guide", x: 152, y: 412,
        desc: { zh: "十四式——验收印章的手势谱与节奏", en: "The fourteen gestures — the hand-forms and cadence of the seals" } },
      { path: "matrix", navKey: "nav.matrix", icon: "matrix", x: 333, y: 312,
        desc: { zh: "判决矩阵——requirement × contract_id，一格一判", en: "The verdict matrix — requirement × contract_id, one cell one judgment" } },
      { path: "explorer", navKey: "nav.explorer", icon: "contracts", x: 330, y: 400,
        desc: { zh: "案卷浏览器——把一份 requirement 拆成可判定的契约族", en: "The case-file explorer — a requirement dissected into contract families" } },
      { path: "contracts", navKey: "nav.contracts", icon: "contracts", x: 452, y: 332,
        desc: { zh: "契约法典——每条契约的 checker_type：http/sql/redis/rabbitmq/openapi", en: "The contract code — every checker_type: http/sql/redis/rabbitmq/openapi" } },
      { path: "eval", navKey: "nav.eval", icon: "chart", x: 462, y: 414,
        desc: { zh: "效果评测——F1 / 召回 / Precision，100 个 golden 样本的真数字", en: "Effectiveness — F1 / recall / precision from the 100-example golden set" } },
      { path: "drill", navKey: "nav.drill", icon: "verify", x: 558, y: 320,
        desc: { zh: "验收快问——十二道题，考完你才有资格按那个绿色按钮", en: "Verify drill — twelve questions before you earn the green button" } },
      { path: "ide", navKey: "nav.ide", icon: "hammer", x: 565, y: 400,
        desc: { zh: "铁匠工坊——锚点抄板 + 本地便笺 + 本仓 RAG 问答", en: "The forge workbench — anchor board + local notes + repo RAG" } },
      { path: "graph", navKey: "nav.graph", icon: "matrix", x: 660, y: 345,
        desc: { zh: "验收之流——18 节点长卷，从 diff 到印章的完整河流", en: "The river of verification — an 18-node scroll from diff to seal" } },
      { path: "chronicle", navKey: "nav.chronicle", icon: "scroll", x: 678, y: 428,
        desc: { zh: "编年史——1570 节，一件事一行：#130 到今天", en: "The chronicle — one line per entry, #130 to today" } },
      { path: "census", navKey: "nav.census", icon: "verify", x: 772, y: 312,
        desc: { zh: "铁样寨地——文件数/LOC/语言 Top 14/账本字节，全部 git ls-files 现推", en: "Iron census — files/LOC/top-14 languages/ledger bytes, all derived from git ls-files" } },
      { path: "manual", navKey: "nav.manual", icon: "guide", x: 782, y: 410,
        desc: { zh: "袖中手札——SPECROOF POCKET CARD，A4 可打印口袋卡", en: "The pocket card — SPECROOF POCKET CARD, printable A4" } },
    ],
  },
  {
    id: "south",
    name: { zh: "治理海岸", en: "The Governance Coast" },
    tagline: { zh: "权限、账单、用量、审计——真实的运维海岸线", en: "Access, billing, usage, audit — the working coast of operations" },
    lore: {
      zh: "大陆不会自己运转——它靠这条海岸线供电：谁能进门（identity）、花了多少 token（usage）、账单怎么算（billing）、每一笔写进 audit_logs、模型怎么接（settings）、服务活着没有（health）。",
      en: "No continent runs itself — the coast powers it: who may enter (identity), how many tokens were spent (usage), what the bill looks like (billing), every write that lands in audit_logs, how the model is wired (settings), and whether anything is alive at all (health).",
    },
    accent: "#fbbf24",
    shape: "M 105 560 C 230 522, 430 530, 600 536 C 770 542, 950 510, 1060 528 C 1122 538, 1124 610, 1035 630 C 800 650, 480 648, 280 640 C 160 634, 40 610, 52 574 Z",
    labelPos: [565, 636],
    rooms: [
      { path: "identity", navKey: "nav.identity", icon: "team", x: 178, y: 566,
        desc: { zh: "团队与权限——RBAC 角色、审批流、谁按的印章", en: "Team & access — RBAC roles, approvals, who pressed which seal" } },
      { path: "billing", navKey: "nav.billing", icon: "billing", x: 352, y: 600,
        desc: { zh: "用量与账单——token 口径的真实账本，出账即证", en: "Usage & billing — the token-true ledger, issued as evidence" } },
      { path: "usage", navKey: "nav.usage", icon: "chart", x: 528, y: 566,
        desc: { zh: "缓存健康——stream + include_usage 车道的命中率观测", en: "Cache health — the stream + include_usage lane's hit-rate telemetry" } },
      { path: "audit", navKey: "nav.audit", icon: "health", x: 700, y: 596,
        desc: { zh: "审计轨迹——audit_logs 全链：谁、何时、改了什么", en: "Audit trail — the full audit_logs chain: who, when, what changed" } },
      { path: "settings", navKey: "nav.settings", icon: "agent", x: 862, y: 568,
        desc: { zh: "模型连接——OpenAI 兼容网关的真连接配置", en: "Model connection — the real OpenAI-compatible gateway wiring" } },
      { path: "health", navKey: "nav.health", icon: "health", x: 1000, y: 598,
        desc: { zh: "服务状态——mysql/redis/rabbitmq/minio 探针，真实延迟分布", en: "Service status — mysql/redis/rabbitmq/minio probes, real latency" } },
    ],
  },
];

export interface Expedition {
  zhTitle: string;
  enTitle: string;
  zhBody: string;
  enBody: string;
  href: string;
  zhCta: string;
  enCta: string;
  minutes: number;
}

export const EXPEDITIONS: Expedition[] = [
  {
    zhTitle: "快速上岸 · 90 秒",
    enTitle: "Fast Shore · 90 seconds",
    zhBody: "巡览六盖印 → 袖中手札口袋卡 → 按需打开游牧指南。给第一次登岛的人。",
    enBody: "Six stamps on the grand tour → the pocket card → the onboarding guide if you still want more. For the first landing.",
    href: "#/tour",
    zhCta: "开始巡览",
    enCta: "Start the tour",
    minutes: 2,
  },
  {
    zhTitle: "证据考察 · 25 分钟",
    enTitle: "Evidence Expedition · 25 min",
    zhBody: "史诗十二卷 → 编年史开卷 → 铁样寨地核对体量。每一步脚下都有 git 真实提交垫底。",
    enBody: "Twelve epic scrolls → the chronicle index → the census cross-check. Every step stands on real git commits.",
    href: "#/epic",
    zhCta: "进入史诗",
    enCta: "Open the epic",
    minutes: 25,
  },
  {
    zhTitle: "验收实战 · 10 分钟",
    enTitle: "Live-Fire Course · 10 min",
    zhBody: "新建验收 → 判决矩阵 → 深链进 FindingDetail。用 demo 仓的 @PreAuthorize 消失，真的跑一次。",
    enBody: "New verification → verdict matrix → deep-link into the finding. Run it once against the demo repo's deleted @PreAuthorize.",
    href: "#/jobs/new",
    zhCta: "新建验收",
    enCta: "New verification",
    minutes: 10,
  },
];
