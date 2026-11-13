/**
 * The honest shortcut map: every entry here EXISTS in the code, no aspirational rows.
 * A shortcut that is not wired cannot be advertised. Keep this in sync with
 * CommandPalette.tsx / App.tsx / Tabs.tsx / Table.tsx / ShortcutHelp.tsx.
 */
export interface ShortcutItem {
  keys: string[];
  label: string;
}
export interface ShortcutGroup {
  title: string;
  items: ShortcutItem[];
}

export const SHORTCUT_GROUPS: readonly ShortcutGroup[] = [
  {
    title: "全局",
    items: [
      { keys: ["Ctrl", "K"], label: "打开 / 关闭命令面板" },
      { keys: ["?"], label: "打开 / 关闭本快捷键表" },
      { keys: ["Esc"], label: "关闭当前浮层（面板 / 对话框 / 菜单）" },
    ],
  },
  {
    title: "命令面板",
    items: [
      { keys: ["↑", "↓"], label: "移动选择" },
      { keys: ["Enter"], label: "打开所选条目" },
      { keys: ["Esc"], label: "关闭面板" },
    ],
  },
  {
    title: "页签与表格",
    items: [
      { keys: ["←", "→"], label: "切换页签（Tabs；也可用 ↑ ↓）" },
      { keys: ["Home", "End"], label: "跳到第一个 / 最后一个页签" },
      { keys: ["Enter", "Space"], label: "打开可点击行（Table）" },
    ],
  },
] as const;
