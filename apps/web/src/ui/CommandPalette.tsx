import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from "react";
import { useTheme } from "../theme/useTheme";
import { Kbd } from "./Kbd";
import { MoonIcon, SearchIcon, SunIcon } from "./icons";
import { listRecentJobs, recordRecentJob } from "./recentJobs";
import { useI18n, type Locale } from "../i18n";

// Every label on this surface renders per stored locale — zh mode shows 中文,
// en mode shows English, never a "工作台 Dashboard" hybrid on a screen.
// `keywords` are deliberately mixed-script: they serve BOTH locales' search
// behavior (a zh query matches the zh terms, an en query matches the en
// terms), so leaving them bilingual is a feature, not residue.

type SectionId = "actions" | "recent" | "agent" | "console";

type LocaleText = Record<Locale, string>;
const pick = (locale: Locale, rec: LocaleText): string => rec[locale];
const T = (zh: string, en: string): LocaleText => ({ zh, en });

interface PaletteEntry {
  id: string;
  section: SectionId;
  label: string;
  sub?: string;
  icon: ReactNode;
  keywords: string;
  action: () => void;
}

interface RouteDef {
  path: string;
  label: LocaleText;
  sub?: LocaleText;
  keywords?: string;
}

const agentRoutes = (): RouteDef[] => [
  { path: "#/agent", label: T("Agent 总览", "Agent overview"), sub: T("代理调度中枢", "Console hub") },
  { path: "#/agent/new", label: T("新建任务 · 仓库", "New task · repo"), sub: T("选择仓库", "Pick the repo") },
  { path: "#/agent/new/spec", label: T("新建任务 · 规范", "New task · spec"), sub: T("编辑需求规格", "Write the spec") },
  { path: "#/agent/new/review", label: T("新建任务 · 提交", "New task · review"), sub: T("审阅并提交", "Review & run") },
  { path: "#/agent/approvals", label: T("审批收件箱", "Approvals inbox"), sub: T("等待你的审批", "Awaiting you") },
  { path: "#/agent/settings", label: T("Agent 设置", "Agent settings"), sub: T("控制台配置", "Console settings") },
];

const consoleRoutes = (): RouteDef[] => [
  { path: "#/dashboard", label: T("工作台", "Dashboard"), sub: T("总览与下一步行动", "Overview & next steps") },
  { path: "#/jobs/new", label: T("新建验证", "New verification"), sub: T("检查代码变更是否满足需求", "Verify a change against its requirement") },
  { path: "#/jobs", label: T("变更验收", "Verifications"), sub: T("验证任务与结论", "Verification jobs & verdicts") },
  { path: "#/matrix", label: T("需求覆盖", "Requirement Coverage"), sub: T("逐项验收矩阵", "Requirement-by-requirement matrix") },
  { path: "#/contracts", label: T("验收规则", "Contracts"), sub: T("契约与版本", "Contracts & versions") },
  { path: "#/identity", label: T("团队与权限", "Team & Access"), sub: T("成员管理 · RBAC", "Members · RBAC") },
  { path: "#/identity/tokens", label: T("访问令牌", "Access tokens"), sub: T("API 令牌管理", "Manage API tokens") },
  { path: "#/billing", label: T("用量与账单", "Usage & Billing"), sub: T("套餐、订阅和使用量", "Plans, subscriptions and usage") },
  { path: "#/settings", label: T("模型连接", "Model Connection"), sub: T("配置模型 API Key、协议与推理强度", "Configure the model gateway, keys, protocol and reasoning") },
  { path: "#/eval", label: T("效果评测", "Effectiveness"), sub: T("F1 / 召回 / Precision", "F1 / recall / precision") },
  { path: "#/health", label: T("服务状态", "Service Status"), sub: T("环境检查与排障", "Environment checks & triage") },
  { path: "#/guide", label: T("上手指南", "Onboarding guide"), sub: T("SpecProof 是什么、怎么用、如何读结果", "What SpecProof is, how to run it, how to read results") },
  { path: "#/ui-kit", label: T("UI Kit 设计系统", "UI Kit"), sub: T("设计系统样式指南", "Design system style guide") },
];

const AGENT_JOB_SUBROUTES: Array<{ suffix: string; label: LocaleText }> = [
  { suffix: "", label: T("详情", "Detail") },
  { suffix: "/plan", label: T("计划", "Plan") },
  { suffix: "/gates", label: T("门禁", "Gates") },
  { suffix: "/diff", label: T("差异", "Diff") },
  { suffix: "/result", label: T("结果", "Result") },
];

const SECTION_ORDER: SectionId[] = ["actions", "recent", "agent", "console"];
const sectionLabels = (locale: Locale): Record<SectionId, string> => ({
  actions: pick(locale, T("操作", "Actions")),
  recent: pick(locale, T("最近任务", "Recent jobs")),
  agent: pick(locale, T("Agent 路由", "Agent routes")),
  console: pick(locale, T("控制台", "Console")),
});

// Keywords stay bilingual on purpose — see the note at the top of the file.
const KEYWORDS = {
  theme: "theme dark light 主题 toggle",
  recent: "recent job 最近任务",
  agent: "agent 代 理",
};

function chipIcon(text: string): ReactNode {
  return <span className="ui-palette-item-icon">{text}</span>;
}

function routeChip(path: string): string {
  const seg = path.replace(/^#\//, "").split("/")[0] || "sp";
  if (seg === "agent") return "AG";
  if (seg === "jobs") return "JB";
  if (seg === "dashboard") return "DS";
  if (seg === "matrix") return "MX";
  if (seg === "contracts") return "CT";
  if (seg === "identity") return "ID";
  if (seg === "eval") return "EV";
  if (seg === "health") return "HL";
  if (seg === "ui-kit") return "UI";
  return "SP";
}

function navigate(path: string): void {
  window.location.hash = path;
}

export function CommandPalette(): JSX.Element | null {
  const { locale } = useI18n();
  const L = useCallback((zh: string, en: string) => (locale === "zh" ? zh : en), [locale]);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const { resolved, toggle } = useTheme();

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setActiveIndex(0);
  }, []);

  // Global shortcut: Ctrl/Cmd+K toggles the palette.
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((prev) => {
          if (prev) {
            setQuery("");
            setActiveIndex(0);
          }
          return !prev;
        });
      } else if (e.key === "Escape" && open) {
        e.stopPropagation();
        close();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, close]);

  // Focus the search input on open.
  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const entries = useMemo<PaletteEntry[]>(() => {
    const out: PaletteEntry[] = [];

    out.push({
      id: "action-theme",
      section: "actions",
      label: resolved === "dark" ? L("切换到浅色主题", "Switch to light theme") : L("切换到深色主题", "Switch to dark theme"),
      sub: resolved === "dark" ? L("Switch to light theme", "Switch to light theme") : L("Switch to dark theme", "Switch to dark theme"),
      icon: resolved === "dark" ? <SunIcon size={12} /> : <MoonIcon size={12} />,
      keywords: KEYWORDS.theme,
      action: toggle,
    });

    for (const job of listRecentJobs()) {
      const base = job.path;
      const isAgentJob = /^#\/agent\/jobs\//.test(base);
      const routes: RouteDef[] = isAgentJob
        ? AGENT_JOB_SUBROUTES.map((r) => ({
            path: base + r.suffix,
            label: T(job.label + (r.suffix ? " · " : "") + pick(locale, r.label), job.label + (r.suffix ? " · " : "") + pick(locale, r.label)),
          }))
        : [{ path: base, label: T(job.label, job.label) }];
      for (const route of routes) {
        const path = route.path;
        const label = pick(locale, route.label);
        out.push({
          id: "recent-" + path.replace(/[^a-zA-Z0-9]/g, "-"),
          section: "recent",
          label,
          sub: path.replace(/^#\//, ""),
          icon: chipIcon("J#"),
          keywords: KEYWORDS.recent + " " + path,
          action: () => {
            recordRecentJob(path, label);
            navigate(path);
          },
        });
      }
    }

    for (const route of agentRoutes()) {
      const path = route.path;
      const label = pick(locale, route.label);
      out.push({
        id: "agent-" + path.replace(/[^a-zA-Z0-9]/g, "-"),
        section: "agent",
        label,
        sub: route.sub ? pick(locale, route.sub) : path.replace(/^#\//, ""),
        icon: chipIcon(routeChip(path)),
        keywords: KEYWORDS.agent + " " + path,
        action: () => {
          if (/^#\/(jobs|agent\/jobs)\/[^/]+/.test(path)) recordRecentJob(path, label);
          navigate(path);
        },
      });
    }

    for (const route of consoleRoutes()) {
      const path = route.path;
      const label = pick(locale, route.label);
      out.push({
        id: "console-" + path.replace(/[^a-zA-Z0-9]/g, "-"),
        section: "console",
        label,
        sub: route.sub ? pick(locale, route.sub) : path.replace(/^#\//, ""),
        icon: chipIcon(routeChip(path)),
        keywords: (route.keywords ?? "") + " " + path,
        action: () => navigate(path),
      });
    }

    return out;
  }, [locale, resolved, toggle]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return entries;
    return entries.filter((entry) =>
      (entry.label + " " + (entry.sub ?? "") + " " + entry.keywords)
        .toLowerCase()
        .includes(q)
    );
  }, [entries, query]);

  // Sections in fixed order, only those with matching entries.
  const sections = useMemo(() => {
    const labels = sectionLabels(locale);
    return SECTION_ORDER.map((section) => ({
      section,
      label: labels[section],
      items: filtered.filter((e) => e.section === section),
    })).filter((s) => s.items.length > 0);
  }, [filtered, locale]);

  const itemCount = sections.reduce((n, s) => n + s.items.length, 0);

  useEffect(() => {
    if (activeIndex > itemCount - 1) setActiveIndex(Math.max(0, itemCount - 1));
  }, [itemCount, activeIndex]);

  // Keep the active item in view.
  useEffect(() => {
    if (!open) return;
    const flat = sections.flatMap((s) => s.items);
    const active = flat[activeIndex];
    if (!active) return;
    const el = listRef.current?.querySelector<HTMLElement>(
      '[data-palette-id="' + active.id.replace(/"/g, '\\"') + '"]'
    );
    if (el && typeof el.scrollIntoView === "function") {
      el.scrollIntoView({ block: "nearest" });
    }
  }, [open, activeIndex, sections]);

  const runEntry = useCallback(
    (entry: PaletteEntry): void => {
      close();
      entry.action();
    },
    [close]
  );

  const onInputKeyDown = useCallback(
    (e: ReactKeyboardEvent<HTMLInputElement>): void => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((i) => (itemCount === 0 ? 0 : (i + 1) % itemCount));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((i) => (itemCount === 0 ? 0 : (i - 1 + itemCount) % itemCount));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const flat = sections.flatMap((s) => s.items);
        const entry = flat[activeIndex];
        if (entry) runEntry(entry);
      } else if (e.key === "Escape") {
        e.preventDefault();
        close();
      }
    },
    [activeIndex, itemCount, sections, runEntry, close]
  );

  const onItemMouseDown = useCallback(
    (e: ReactMouseEvent<HTMLButtonElement>, entry: PaletteEntry): void => {
      e.preventDefault();
      runEntry(entry);
    },
    [runEntry]
  );

  if (!open) return null;

  let cursor = -1;
  const activeId = ((): string | undefined => {
    const flat = sections.flatMap((s) => s.items);
    return flat[activeIndex]?.id;
  })();

  return (
    <div className="ui-palette-root" role="dialog" aria-modal="true" aria-label={L("命令面板", "Command palette")}>
      <div
        className="ui-palette-backdrop"
        aria-hidden="true"
        onMouseDown={(e) => {
          if (e.target === e.currentTarget) close();
        }}
      />
      <div className="ui-palette-panel">
        <div className="ui-palette-search">
          <span className="ui-palette-search-icon" aria-hidden="true">
            <SearchIcon size={16} />
          </span>
          <input
            ref={inputRef}
            className="ui-palette-input"
            type="text"
            role="combobox"
            aria-expanded="true"
            aria-controls="ui-palette-list"
            aria-activedescendant={activeId ? "ui-palette-opt-" + activeId : undefined}
            placeholder={L("搜索路由、任务或切换主题…", "Search routes, jobs, or toggle the theme…")}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={onInputKeyDown}
          />
          <Kbd>Esc</Kbd>
        </div>
        <div className="ui-palette-list" id="ui-palette-list" role="listbox" ref={listRef}>
          {sections.length === 0 ? (
            <div className="ui-palette-section">{L("无匹配结果", "No results")}</div>
          ) : (
            sections.map((section) => (
              <div key={section.section}>
                <div className="ui-palette-section">{section.label}</div>
                {section.items.map((entry) => {
                  cursor += 1;
                  const index = cursor;
                  return (
                    <button
                      key={entry.id}
                      type="button"
                      role="option"
                      id={"ui-palette-opt-" + entry.id}
                      data-palette-id={entry.id}
                      aria-selected={index === activeIndex}
                      className="ui-palette-item"
                      onMouseDown={(e) => onItemMouseDown(e, entry)}
                      onMouseEnter={() => setActiveIndex(index)}
                    >
                      {entry.icon}
                      <span className="ui-palette-item-main">
                        <span className="ui-palette-item-label">{entry.label}</span>
                        {entry.sub ? <span className="ui-palette-item-sub">{entry.sub}</span> : null}
                      </span>
                      <span className="ui-palette-enter" aria-hidden="true">
                        ⏎
                      </span>
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>
        <div className="ui-palette-foot">
          <span className="ui-palette-hint">
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd> {L("选择", "navigate")}
          </span>
          <span className="ui-palette-hint">
            <Kbd>⏎</Kbd> {L("打开", "open")}
          </span>
          <span className="ui-palette-hint">
            <Kbd>Esc</Kbd> {L("关闭", "close")}
          </span>
          <span className="ui-palette-hint">
            <Kbd>Ctrl</Kbd>
            <Kbd>K</Kbd> {L("开启", "toggle")}
          </span>
        </div>
      </div>
    </div>
  );
}
