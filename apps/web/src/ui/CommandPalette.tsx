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

type SectionId = "actions" | "recent" | "agent" | "console";

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
  label: string;
  sub?: string;
  keywords?: string;
}

const AGENT_ROUTES: RouteDef[] = [
  { path: "#/agent", label: "Agent 总览", sub: "Agent overview" },
  { path: "#/agent/new", label: "新建任务 · 仓库", sub: "New task — repo" },
  { path: "#/agent/new/spec", label: "新建任务 · 规范", sub: "New task — spec" },
  { path: "#/agent/new/gates", label: "新建任务 · 门禁", sub: "New task — gates" },
  { path: "#/agent/new/review", label: "新建任务 · 复核", sub: "New task — review" },
  { path: "#/agent/approvals", label: "审批收件箱", sub: "Approvals inbox" },
  { path: "#/agent/settings", label: "Agent 设置", sub: "Console settings" },
];

const CONSOLE_ROUTES: RouteDef[] = [
  { path: "#/dashboard", label: "总览", sub: "Dashboard" },
  { path: "#/jobs", label: "任务列表", sub: "Jobs" },
  { path: "#/matrix", label: "需求矩阵", sub: "Matrix" },
  { path: "#/contracts", label: "契约中心", sub: "Contracts" },
  { path: "#/identity", label: "身份 · 用户", sub: "Identity — users" },
  { path: "#/identity/tokens", label: "身份 · 令牌", sub: "Identity — tokens" },
  { path: "#/eval", label: "评测", sub: "Eval" },
  { path: "#/health", label: "健康", sub: "Health" },
  { path: "#/ui-kit", label: "UI Kit 设计系统", sub: "Design system style guide" },
];

const AGENT_JOB_SUBROUTES: Array<{ suffix: string; label: string }> = [
  { suffix: "", label: "详情" },
  { suffix: "/plan", label: "计划" },
  { suffix: "/gates", label: "门禁" },
  { suffix: "/diff", label: "差异" },
  { suffix: "/result", label: "结果" },
];

const SECTION_ORDER: SectionId[] = ["actions", "recent", "agent", "console"];
const SECTION_LABELS: Record<SectionId, string> = {
  actions: "操作 Actions",
  recent: "最近任务 Recent jobs",
  agent: "Agent 路由",
  console: "控制台 Console",
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
      label: resolved === "dark" ? "切换到浅色主题" : "切换到深色主题",
      sub: resolved === "dark" ? "Switch to light theme" : "Switch to dark theme",
      icon: resolved === "dark" ? <SunIcon size={12} /> : <MoonIcon size={12} />,
      keywords: "theme dark light 主题 toggle",
      action: toggle,
    });

    for (const job of listRecentJobs()) {
      const base = job.path;
      const isAgentJob = /^#\/agent\/jobs\//.test(base);
      const routes: RouteDef[] = isAgentJob
        ? AGENT_JOB_SUBROUTES.map((r) => ({
            path: base + r.suffix,
            label: job.label + (r.suffix ? " · " + r.label : ""),
          }))
        : [{ path: base, label: job.label }];
      for (const route of routes) {
        const path = route.path;
        out.push({
          id: "recent-" + path.replace(/[^a-zA-Z0-9]/g, "-"),
          section: "recent",
          label: route.label,
          sub: path.replace(/^#\//, ""),
          icon: chipIcon("J#"),
          keywords: "recent job " + path,
          action: () => {
            recordRecentJob(path, route.label);
            navigate(path);
          },
        });
      }
    }

    for (const route of AGENT_ROUTES) {
      const path = route.path;
      out.push({
        id: "agent-" + path.replace(/[^a-zA-Z0-9]/g, "-"),
        section: "agent",
        label: route.label,
        sub: route.sub ?? path.replace(/^#\//, ""),
        icon: chipIcon(routeChip(path)),
        keywords: "agent " + (route.keywords ?? "") + " " + path,
        action: () => {
          if (/^#\/(jobs|agent\/jobs)\/[^/]+/.test(path)) recordRecentJob(path, route.label);
          navigate(path);
        },
      });
    }

    for (const route of CONSOLE_ROUTES) {
      const path = route.path;
      out.push({
        id: "console-" + path.replace(/[^a-zA-Z0-9]/g, "-"),
        section: "console",
        label: route.label,
        sub: route.sub ?? path.replace(/^#\//, ""),
        icon: chipIcon(routeChip(path)),
        keywords: (route.keywords ?? "") + " " + path,
        action: () => navigate(path),
      });
    }

    return out;
  }, [resolved, toggle]);

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
    return SECTION_ORDER.map((section) => ({
      section,
      items: filtered.filter((e) => e.section === section),
    })).filter((s) => s.items.length > 0);
  }, [filtered]);

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
    <div className="ui-palette-root" role="dialog" aria-modal="true" aria-label="命令面板 Command palette">
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
            placeholder="搜索路由、任务或切换主题…"
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
            <div className="ui-palette-section">无匹配结果 No results</div>
          ) : (
            sections.map((section) => (
              <div key={section.section}>
                <div className="ui-palette-section">{SECTION_LABELS[section.section]}</div>
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
                        ↵
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
            <Kbd>↓</Kbd> 选择
          </span>
          <span className="ui-palette-hint">
            <Kbd>↵</Kbd> 打开
          </span>
          <span className="ui-palette-hint">
            <Kbd>Esc</Kbd> 关闭
          </span>
          <span className="ui-palette-hint">
            <Kbd>Ctrl</Kbd>
            <Kbd>K</Kbd> 开关
          </span>
        </div>
      </div>
    </div>
  );
}
