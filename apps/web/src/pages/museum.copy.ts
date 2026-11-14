import type { Locale } from "../i18n/strings";

/**
 * The Evidence Museum — twelve exhibits, every one a true record in this
 * repository's ledger. Exhibits are not decoration: each anchor points at a
 * ledger entry number, a real verification run, a real commit and a real
 * measured number. Nothing here is lore.
 *
 * Exhibits carry an `anchor` displayed verbatim (ledger id · file or commit)
 * — there is intentionally no decorative "impact" metric.
 */

export interface MuseumExhibit {
  id: string;
  numeral: string;
  title: Record<Locale, string>;
  story: Record<Locale, string>;
  /** Verbatim pointer into the repository — shown exactly as stored. */
  anchor: string;
  /** Short category label shown as a tag. */
  tag: Record<Locale, string>;
}

export const EXHIBITS: MuseumExhibit[] = [
  {
    id: "auth-01-fast-verify",
    numeral: "I",
    title: { zh: "AUTH-01 · 被抓住的一次合并", en: "AUTH-01 · the catch" },
    story: {
      zh: "demo/spring-backend 的 head-v1 移除了 changeEmail 接口的 @PreAuthorize。真机 FAST 闭环（#1689）抓住了它：契约 AUTH-01 FAIL，结论 honestly BLOCKED，HTML 报告 + capsule-…zip 落地。铁证：base_pass_head_fail。",
      en: "demo/spring-backend's head-v1 removes @PreAuthorize from changeEmail. The real-machine FAST loop (#1689) caught it: contract AUTH-01 FAIL, the honest verdict BLOCKED, an HTML report and a reproduction capsule landed. The iron evidence: base_pass_head_fail.",
    },
    anchor: "#1689 · demo/spring-backend (tag head-v1) · capsule-COURT-AUTH-01.zip",
    tag: { zh: "铁证", en: "Iron evidence" },
  },
  {
    id: "cache-96-5",
    numeral: "II",
    title: { zh: "96.5% · 那 2272 字节", en: "96.5% · the 2272-byte prefix" },
    story: {
      zh: "_JUNIT_GENERATION_PROMPT 的稳定前缀由 270 字符扩大到 ~2272 字节、~567 tokens，缓存命中率 96.5%（#1645 实测）；同前缀换变量命中 75–90%（#1679/#1681）；双车道统一 stream=True + include_usage。",
      en: "The stable prefix of _JUNIT_GENERATION_PROMPT (~2272 bytes / ~567 tokens) hit 96.5% cache reuse (#1645, measured); the same prefix with swapped variables hits 75–90% (#1679/#1681); both lanes now speak stream=True + include_usage.",
    },
    anchor: "#1644/#1645/#1663/#1679/#1681 · scripts/probe_cache_efficiency.py",
    tag: { zh: "缓存", en: "Cache" },
  },
  {
    id: "gateway-breaker",
    numeral: "III",
    title: { zh: "第五次，门落下", en: "The fifth call, and the gate fell" },
    story: {
      zh: "Spring Cloud Gateway + Eureka + Config 全链路真跑：对死上游连打 12 次，Resilience4j 在第 5 次翻开（specproof-edge），503 circuit-open 而不是卡死；POST /actuator/refresh 让 specproof_edge_config_refresh_events_total 0→1。",
      en: "Spring Cloud Gateway + Eureka + Config wired live: 12 calls against a dead upstream, Resilience4j tripped at the fifth (specproof-edge) — 503 circuit-open instead of a hang; POST /actuator/refresh moved specproof_edge_config_refresh_events_total 0→1.",
    },
    anchor: "#1674 · demo/spring-backend/gateway · Eureka 8769",
    tag: { zh: "微服务", en: "Microservices" },
  },
  {
    id: "done-frame-bug",
    numeral: "IV",
    title: { zh: "AI 解读卡住的那个晚上", en: "The night the AI got stuck" },
    story: {
      zh: "openEventStream 丢弃了命名帧 data——AI 解读永远停在「正在解读…」。e2e 抓住了它，修成按命名帧转发 onEvent；从此每颗星星都落在钱包里。",
      en: "openEventStream was dropping named-frame payloads — the AI reading froze on 「正在解读…」 forever. The e2e caught it; named frames now forward onEvent, and no reader is left waiting at 「正在解读…」.",
    },
    anchor: "#1672 · 54b561c · apps/web/src/api/openEventStream.ts",
    tag: { zh: "界面", en: "Frontend" },
  },
  {
    id: "lightningcss",
    numeral: "V",
    title: { zh: "那个炸掉构建的 CSS 类", en: "The class that broke the build" },
    story: {
      zh: "#1680 引入了中文 class 名 .tier-铁 / .tier-?，lightningcss 压缩直接报错。修法：class 改 ASCII slug（tier-iron/…/unknown），读者看到的字形仍是中文 铁/半铁/静/坏/文/?.",
      en: "#1680 shipped Chinese class names (.tier-铁 / .tier-?); lightningcss could not minify them and the build went red. Fix: classes are ASCII slugs (tier-iron/…/unknown); the glyphs readers see stay Chinese.",
    },
    anchor: "#1693 · apps/web/src/styles/verification.css · .tier-iron …",
    tag: { zh: "界面", en: "Frontend" },
  },
  {
    id: "en-book-restructure",
    numeral: "VI",
    title: { zh: "《铁证之书》英文卷的失序之后", en: "After the English book's broken order" },
    story: {
      zh: "英文版《铁证之书》丢失 Scroll 9/10，Final Scroll 被错放在 Scroll 8 之前。#1701 逐节补回：Scroll 9 · The Seal and the Window、Appendix C/D、Scroll 10，并让 Final Scroll 归位到全书末尾。",
      en: "The English edition was missing Scroll 9 & 10, and Final Scroll sat before Scroll 8. #1701 restored them scroll by scroll — The Seal and the Window, Appendices C/D, Before the Reader — and returned Final Scroll to the end where it belongs.",
    },
    anchor: "#1701 · docs/world/EN/SPECROOF_WORLD_EN.md",
    tag: { zh: "正史", en: "Chronicles" },
  },
  {
    id: "health-five-category",
    numeral: "VII",
    title: { zh: "五类健康，绝不刷绿", en: "Five truths, never painted green" },
    story: {
      zh: "/health 页与 five-category health 从不把未知抹成绿色：服务可达 / 依赖可达 / 能力清单 / 当前降级 / 数据可查询。数据未知就是未知，降级如实、探针失败为红，unknown 永远灰。",
      en: "The health page never paints unknown as green: service reachable, dependencies, capabilities, degraded, data queryable. Unknown stays unknown; missing flags are reported as missing; a dead probe is red.",
    },
    anchor: "#1703 · apps/web/src/pages/healthCategories.ts",
    tag: { zh: "后端", en: "Backend" },
  },
  {
    id: "audit-three-way",
    numeral: "VIII",
    title: { zh: "没有审计行 ≠ 审计没有", en: "No rows is not the same as no audit" },
    story: {
      zh: "审计轨迹页拒绝「一条三因的糊涂账」：作业不存在 / 作业在册但无行 / job_present=null（服务端未回传）——三种情况三套文案，绝不认领为「暂无记录」。",
      en: "The audit page refuses one muddled sentence for three different truths: job missing, job on roster with no rows, job_present=null — three honest copy branches, never a bare “no records”.",
    },
    anchor: "#1708 · apps/web/src/pages/Audit.tsx",
    tag: { zh: "治理", en: "Governance" },
  },
  {
    id: "lexicon-live",
    numeral: "IX",
    title: { zh: "十四个真跑过的词", en: "Fourteen words that ran" },
    story: {
      zh: "铁证词典（#1698）把 appendix 里的十四个词搬进产品：每词可点开，看到铁语境 + 仓库锚点。base_pass_head_fail、AUTH-01、_JUNIT_GENERATION_PROMPT……都能在仓库里指到确切位置。",
      en: "The Iron Lexicon (#1698) moves the appendix into the product: tap any of the fourteen words and read its iron context plus a repository anchor — base_pass_head_fail, AUTH-01, _JUNIT_GENERATION_PROMPT … all point somewhere real.",
    },
    anchor: "#1698 · apps/web/src/pages/lexicon.copy.ts",
    tag: { zh: "界面", en: "Frontend" },
  },
  {
    id: "i18n-parity",
    numeral: "X",
    title: { zh: "一个 key，两种语言", en: "One key, two tongues" },
    story: {
      zh: "i18n 层立下规矩：一个 key 两个 locale、parity 门守缺 key、unknown key 回 key 本身——没有任何一屏是「中英夹杂」。切换时 <html lang> 也随之宣告。",
      en: "The i18n layer sets a rule: one key, two locales, a parity gate that refuses missing keys, and unknown keys echo themselves — no screen ever ships half-translated. <html lang> declares the truth on every switch.",
    },
    anchor: "#1693 · apps/web/src/i18n/ · i18n.parity.test.ts",
    tag: { zh: "界面", en: "Frontend" },
  },
  {
    id: "tour-six-stamps",
    numeral: "XI",
    title: { zh: "六卷盖印，「验讫」", en: "Six stamps, and the seal falls" },
    story: {
      zh: "巡览（#1677）是产品里唯一的游戏：六卷盖章、无分数、无计时、无假进度、印只存本机 localStorage——换浏览器，一切重走。信任，必须从零捡起。",
      en: "The Grand Tour (#1677) is the one game in the product: six stamps, no score, no timer, no fake progress — seals live in this browser's localStorage, and another browser walks from zero. Trust must be picked up a little at a time.",
    },
    anchor: "#1677 · docs/operations/TOUR_MANUAL.md · specproof_tour_v1",
    tag: { zh: "玩法", en: "Play" },
  },
  {
    id: "ledger-discipline",
    numeral: "XII",
    title: { zh: "史官的笔，从不擦", en: "The chronicler never erases" },
    story: {
      zh: "DEEP_OPTIMIZATION_PLAN.md 累计 1700+ 条账目：#1681 实测 wkapi 命中 75.2–84% 被如实写下、#1674 Gw 冒烟被如实写下、#1689 verify 真机 BLOCKED 被如实写下——每一条都能 git log 对账。",
      en: "DEEP_OPTIMIZATION_PLAN.md carries #1620 onward: the 75.2–84% hit-rate A/B (#1681), the gateway smoke run (#1674), the real BLOCKED verdict (#1689) — every entry checks out against git log; nothing was erased.",
    },
    anchor: "#1681/#1674/#1689 · docs/operations/DEEP_OPTIMIZATION_PLAN.md",
    tag: { zh: "治理", en: "Governance" },
  },
];
