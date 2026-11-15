/**
 * The honest shortcut map: every entry here EXISTS in the code, no aspirational rows.
 * A shortcut that is not wired cannot be advertised. Keep this in sync with
 * CommandPalette.tsx / App.tsx / Tabs.tsx / Table.tsx / ShortcutHelp.tsx.
 *
 * A key, two locales — zh and en are different words, not different rows.
 */
export interface ShortcutText {
  zh: string;
  en: string;
}
export interface ShortcutItem {
  keys: string[];
  label: ShortcutText;
}
export interface ShortcutGroup {
  title: ShortcutText;
  items: ShortcutItem[];
}

export const SHORTCUT_GROUPS: readonly ShortcutGroup[] = [
  {
    title: { zh: "全局", en: "General" },
    items: [
      { keys: ["Ctrl", "K"], label: { zh: "打开 / 关闭命令面板", en: "Open / close the command palette" } },
      { keys: ["?"], label: { zh: "打开 / 关闭快捷键说明", en: "Open / close this shortcut card" } },
      { keys: ["Esc"], label: { zh: "关闭当前浮层（弹窗 / 抽屉 / 菜单）", en: "Close the active overlay (dialog / drawer / menu)" } },
    ],
  },
  {
    title: { zh: "命令面板", en: "Command palette" },
    items: [
      { keys: ["←", "→"], label: { zh: "移动选择", en: "Move selection" } },
      { keys: ["Enter"], label: { zh: "确认选择项", en: "Confirm the selection" } },
      { keys: ["Esc"], label: { zh: "关闭面板", en: "Close the palette" } },
    ],
  },
  {
    title: { zh: "页面内", en: "In-page" },
    items: [
      { keys: ["←", "→"], label: { zh: "切换页签（Tabs），也可点击", en: "Switch tabs (Tabs) — click works too" } },
      { keys: ["Home", "End"], label: { zh: "切到第一个 / 最后一个页签", en: "First / last tab" } },
      { keys: ["Enter", "Space"], label: { zh: "触发行操作（Table）", en: "Trigger the row action (Table)" } },
    ],
  },
  {
    title: { zh: "主界面教学", en: "On the main screen" },
    items: [
      { keys: ["H"], label: { zh: "开关首页教学模式（金色徽章 + 逐按键说明）", en: "Toggle coach marks on the main screen (gold badges + one line per control)" } },
      { keys: ["?"], label: { zh: "打开 / 关闭本说明书（快捷键总览）", en: "Open / close this cheat sheet" } },
    ],
  },
] as const;
