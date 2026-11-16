import type { Locale } from "../i18n/strings";

/**
 * Coach marks — the teaching layer over the main interface.
 *
 * Every actionable element worth explaining carries `data-coach="<key>"`.
 * This table maps those keys to their bilingual "what this does" text.
 * Order fixes the badge numbers; keys not listed here are simply not badged.
 */

export interface CoachMark {
  /** matches the element's data-coach attribute */
  key: string;
  title: Record<Locale, string>;
  body: Record<Locale, string>;
}

export const COACH_MARKS: readonly CoachMark[] = [
  { key: "topbar.search",
    title: { zh: "全局搜索", en: "Global search" },
    body: {
      zh: "Ctrl+K 打开命令面板——输入任意页面、动作或最近的工作，直接跳到。按 ? 查看全部快捷键。",
      en: "Ctrl+K opens the command palette — any page, action, or recent job, one keystroke away. Press ? for all shortcuts.",
    } },
  { key: "topbar.help",
    title: { zh: "使用帮助", en: "Help" },
    body: {
      zh: "任何疑问先看这里：渐进式上手指南，从 30 秒口袋卡走到六盖印巡览。",
      en: "Start here when lost: the progressive onboarding guide — from the 30-second pocket card to the six-stamp tour.",
    } },
  { key: "topbar.theme",
    title: { zh: "切换深/浅色", en: "Toggle theme" },
    body: {
      zh: "深色（夜行）、浅色（白天）——跟随系统，也可手动钉一个。",
      en: "Dark (the night watch) or light (the daylight) — follows system, or pin it.",
    } },
  { key: "topbar.locale",
    title: { zh: "中/EN 切换", en: "Switch language" },
    body: {
      zh: "全界面中文⇄English——两表逐键对齐，不会半中半英。",
      en: "Whole UI Chinese ⇄ English — every string parity-tested; never a half-and-half screen.",
    } },
  { key: "topbar.menu",
    title: { zh: "移动菜单", en: "Mobile menu" },
    body: {
      zh: "窄屏下抽屉式侧导——全部 41 个入口一样齐全。",
      en: "Drawer navigation on narrow screens — all 41 destinations, same as desktop.",
    } },
  { key: "nav:dashboard",
    title: { zh: "工作台", en: "Dashboard" },
    body: {
      zh: "今天的验收航迹：未决 BLOCKER、进行中的判定、刚落座的结论——进门先落这一眼。",
      en: "Today's verification trail — open blockers, in-flight verdicts, landed conclusions. First glance, every visit.",
    } },
  { key: "nav:jobs",
    title: { zh: "变更验收", en: "Verifications" },
    body: {
      zh: "验收单列表：每一条都是 base/head 指纹——点任一行进详情，按时间看谁验的。",
      en: "The verification ledger — every row is a base/head fingerprint. Open any to see who verified what, when.",
    } },
  { key: "nav:agent",
    title: { zh: "AI 开发", en: "AI Developer" },
    body: {
      zh: "SpecCraft 工坊：让 AI 写代码、自我修复——它每步都留下了可对照的证据。",
      en: "The SpecCraft forge — the AI writes, self-repairs, and leaves diffable evidence at every step.",
    } },
  { key: "nav:tour",
    title: { zh: "巡览", en: "Grand Tour" },
    body: {
      zh: "六盖印交互通关：从连接工作区到亲手盖最后一枚印——通关之前你还不是这里的人。",
      en: "The six-stamp interactive tour — from connecting a workspace to pressing the last seal yourself.",
    } },
  { key: "nav:atlas",
    title: { zh: "世界舆图", en: "Atlas" },
    body: {
      zh: "三座岛 × 24 个厅的大陆地图——带你看清整个 SpecProof 的地形。",
      en: "The continent map — three islands, 24 halls — see the whole terrain of SpecProof at a glance.",
    } },
  { key: "nav:worldbook",
    title: { zh: "世界书", en: "World Book" },
    body: {
      zh: "铁证之书：27 卷正史+附录——可读、可搜、可标记、可翻印。",
      en: "The Book of Iron Evidence — 27 volumes plus appendices; readable, searchable, badgeable, printable.",
    } },
  { key: "nav:gazette",
    title: { zh: "铁证晨报", en: "The Gazette" },
    body: {
      zh: "仓库的每日报纸——头版现播、数字现推，打印即一张纸。",
      en: "The repo's daily paper — live lead, live numbers; one page when printed.",
    } },
  { key: "nav:calendar",
    title: { zh: "铁证日历", en: "The Calendar" },
    body: {
      zh: "365 天 × 每天提交数——git 说了算的一年。",
      en: "365 days × commits-per-day — one year as git tells it.",
    } },
  { key: "nav:manual",
    title: { zh: "说明书", en: "Manual" },
    body: {
      zh: "A4 一页口袋卡——打出来贴身边，30 秒看完就会用。",
      en: "A4 pocket card — print it, keep it close; 30 seconds and you know where everything is.",
    } },
  { key: "nav:recall",
    title: { zh: "问铁证", en: "Ask the Iron" },
    body: {
      zh: "把账本和更正卷轴当作答案库——BM25 现敲，不联网、不调用模型、分数可复现。",
      en: "The ledger and the errata scroll become your answer key — BM25 struck locally, no network, no model call, reproducible scores.",
    } },
  { key: "boot.guide",
    title: { zh: "上手指南", en: "Onboarding" },
    body: {
      zh: "第一次来先看这里：从 0 到跑出第一份验收，分阶段一步一步带你走。",
      en: "First time here? — from zero to your first verification, in stages, all the way.",
    } },
  { key: "topbar.coach",
    title: { zh: "教学模式", en: "Coach marks" },
    body: {
      zh: "按 H 或点此——全主界面的每个按键、按钮、入口，都带了一句教学说明。",
      en: "Press H or this button — every control on the main screen gets its one-line lesson.",
    } },
  { key: "boot.brand",
    title: { zh: "回首页", en: "Home" },
    body: {
      zh: "点这回工作台——验收的航迹都从这里出发和收档。",
      en: "Back to the dashboard — where every trail starts and lands.",
    } },
];

const STORAGE_KEY = "specproof_coach_marks";
const TOGGLE_EVENT = "specproof-coach-marks:toggle";

export function readCoachEnabled(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === null) return true; // first visit: ON
    return raw === "1";
  } catch {
    return false;
  }
}

export function writeCoachEnabled(enabled: boolean): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, enabled ? "1" : "0");
  } catch {
    /* storage unavailable — legend still dismissible for the session */
  }
}

export function toggleCoachMarks(): void {
  if (typeof window === "undefined") return;
  writeCoachEnabled(!readCoachEnabled());
  window.dispatchEvent(new Event(TOGGLE_EVENT));
}

export function coachToggleEvent(): string {
  return TOGGLE_EVENT;
}
