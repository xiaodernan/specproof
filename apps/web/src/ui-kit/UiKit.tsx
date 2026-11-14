import { useState, type ReactNode } from "react";
import { useTheme, type ThemePreference } from "../theme/useTheme";
import { useI18n } from "../i18n";
import {
  Badge,
  Breadcrumbs,
  Button,
  Card,
  Checkbox,
  EmptyState,
  Input,
  Kbd,
  Modal,
  Progress,
  Select,
  Skeleton,
  StatusDot,
  Table,
  Tabs,
  Textarea,
  Timeline,
  Tooltip,
  useToast,
  type Column,
  type TimelineEvent,
} from "../ui";
import { InboxIcon, MoonIcon, SunIcon } from "../ui/icons";
import { ControlRoomPreview } from "./ControlRoomPreview";
import { SHORTCUT_GROUPS } from "../ui/shortcuts";

interface ShortcutRow {
  group: string;
  label: string;
  keys: string[];
}

const SHORTCUT_ROWS: ShortcutRow[] = SHORTCUT_GROUPS.flatMap((group) =>
  group.items.map((item) => ({ group: group.title, label: item.label, keys: item.keys }))
);

function makeShortcutColumns(locale: "zh" | "en"): Column<ShortcutRow>[] {
  const loc = (zh: string, en: string): string => (locale === "zh" ? zh : en);
  return [

  { key: "group", header: loc("分组", "Group") },
  { key: "label", header: loc("功能", "Function") },
  {
    key: "keys",
    header: loc("按键", "Keys"),
    render: (row) => (
      <span style={{ display: "inline-flex", gap: "4px", alignItems: "center" }}>
        {row.keys.map((key) => <Kbd key={key}>{key}</Kbd>)}
      </span>
    ),
  },
  ];
}

/* ── demo data ────────────────────────────────────────────── */

interface FruitRow {
  name: string;
  qty: number;
  price: number;
}

function makeFruitColumns(locale: "zh" | "en"): Column<FruitRow>[] {
  const loc = (zh: string, en: string): string => (locale === "zh" ? zh : en);
  return [

  { key: "name", header: loc("名称", "Name") },
  {
    key: "qty",
    header: loc("库存", "Stock"),
    align: "right",
    sortable: true,
    render: (row) => <span className="ui-kit-num">{row.qty}</span>,
  },
  {
    key: "price",
    header: loc("单价 ¥", "Unit ¥"),
    align: "right",
    sortable: true,
    sortValue: (row) => row.price,
    render: (row) => <span className="ui-kit-num">{row.price.toFixed(2)}</span>,
  },
  ];
}

const FRUIT_ROWS: FruitRow[] = [
  { name: "荔枝 Lychee", qty: 128, price: 12.5 },
  { name: "山竹 Mangosteen", qty: 64, price: 28.0 },
  { name: "杨梅 Bayberry", qty: 210, price: 9.9 },
  { name: "枇杷 Loquat", qty: 47, price: 16.8 },
  { name: "莲雾 Wax apple", qty: 32, price: 22.0 },
];

const JOB_TIMELINE: TimelineEvent[] = [
  { id: "t1", title: "intake — requirement received", description: "spec-v1.2 parsed", time: "09:41:02", status: "success" },
  { id: "t2", title: "compile — contracts compiled", description: "6 contracts · 2 high priority", time: "09:41:18", status: "success" },
  { id: "t3", title: "differential — running", description: "base→head-v1 JUnit running", time: "09:42:05", status: "running" },
  { id: "t4", title: "review — review court", description: "awaiting evidence roll-up", time: "—", status: "idle" },
  { id: "t5", title: "publish — report", description: "matrix + certificate", time: "—", status: "idle" },
];

interface Swatch {
  token: string;
  css: string;
  fg: string;
}

const ACCENT_SWATCHES: Swatch[] = [
  { token: "accent-100", css: "var(--accent-100)", fg: "#3a228a" },
  { token: "accent-200", css: "var(--accent-200)", fg: "#3a228a" },
  { token: "accent-300", css: "var(--accent-300)", fg: "#3a228a" },
  { token: "accent-400", css: "var(--accent-400)", fg: "#ffffff" },
  { token: "accent-500", css: "var(--accent-500)", fg: "#ffffff" },
  { token: "accent-600", css: "var(--accent-600)", fg: "#ffffff" },
  { token: "accent-700", css: "var(--accent-700)", fg: "#ffffff" },
  { token: "accent-800", css: "var(--accent-800)", fg: "#ffffff" },
  { token: "accent-900", css: "var(--accent-900)", fg: "#ffffff" },
  { token: "gradient-aurora", css: "var(--gradient-aurora)", fg: "#ffffff" },
  { token: "accent-2-300", css: "var(--accent-2-300)", fg: "#083344" },
  { token: "accent-2-400", css: "var(--accent-2-400)", fg: "#083344" },
];

const NEUTRAL_SWATCHES: Swatch[] = [
  { token: "zinc-0", css: "var(--zinc-0)", fg: "#18181b" },
  { token: "zinc-50", css: "var(--zinc-50)", fg: "#18181b" },
  { token: "zinc-100", css: "var(--zinc-100)", fg: "#18181b" },
  { token: "zinc-200", css: "var(--zinc-200)", fg: "#18181b" },
  { token: "zinc-300", css: "var(--zinc-300)", fg: "#18181b" },
  { token: "zinc-400", css: "var(--zinc-400)", fg: "#18181b" },
  { token: "zinc-500", css: "var(--zinc-500)", fg: "#ffffff" },
  { token: "zinc-600", css: "var(--zinc-600)", fg: "#ffffff" },
  { token: "zinc-700", css: "var(--zinc-700)", fg: "#ffffff" },
  { token: "zinc-800", css: "var(--zinc-800)", fg: "#ffffff" },
  { token: "zinc-850", css: "var(--zinc-850)", fg: "#ffffff" },
  { token: "zinc-875", css: "var(--zinc-875)", fg: "#ffffff" },
  { token: "zinc-900", css: "var(--zinc-900)", fg: "#ffffff" },
  { token: "zinc-925", css: "var(--zinc-925)", fg: "#ffffff" },
  { token: "zinc-950", css: "var(--zinc-950)", fg: "#ffffff" },
];

const SEMANTIC_SWATCHES: Swatch[] = [
  { token: "success", css: "var(--success-tint)", fg: "var(--success-fg)" },
  { token: "warning", css: "var(--warning-tint)", fg: "var(--warning-fg)" },
  { token: "danger", css: "var(--danger-tint)", fg: "var(--danger-fg)" },
  { token: "info", css: "var(--info-tint)", fg: "var(--info-fg)" },
];

/* ── small layout helpers ─────────────────────────────────── */

function Section(props: { id: string; zh: string; en: string; children: ReactNode }): JSX.Element {
  const { locale } = useI18n();
  return (
    <section className="ui-kit-section" id={props.id}>
      <h2 className="ui-kit-h2">
        {locale === "zh" ? props.zh : props.en} <span className="ui-kit-h2-id">{locale === "zh" ? props.en : props.zh}</span>
      </h2>
      {props.children}
    </section>
  );
}

function Demo(props: { children: ReactNode; col?: boolean }): JSX.Element {
  return (
    <div className={"ui-kit-demo" + (props.col ? " ui-kit-demo-col" : "")}>{props.children}</div>
  );
}

function DemoTitle(props: { children: ReactNode }): JSX.Element {
  return <h3 className="ui-kit-demo-title">{props.children}</h3>;
}

function SwatchBlock(props: { swatch: Swatch }): JSX.Element {
  return (
    <div>
      <div className="ui-kit-swatch" style={{ background: props.swatch.css, color: props.swatch.fg }}>
        <span>{props.swatch.token}</span>
      </div>
      <div className="ui-kit-swatch-label">{props.swatch.token}</div>
    </div>
  );
}

/* ── page ─────────────────────────────────────────────────── */

export default function UiKit(): JSX.Element {
  const { theme, resolved, setTheme } = useTheme();
  const toast = useToast();
  const [modalOpen, setModalOpen] = useState(false);
  const [checkA, setCheckA] = useState(true);
  const [checkB, setCheckB] = useState(false);
  const [textValue, setTextValue] = useState("");
  const [selectValue, setSelectValue] = useState("aurora");

  const { locale } = useI18n();
  const loc = (zh: string, en: string): string => (locale === "zh" ? zh : en);

  const themePrefs: Array<{ id: ThemePreference; label: string; icon: ReactNode }> = [
    { id: "system", label: loc("跟随系统", "System"), icon: null },
    { id: "dark", label: loc("深色", "Dark"), icon: <MoonIcon size={12} /> },
    { id: "light", label: loc("浅色", "Light"), icon: <SunIcon size={12} /> },
  ];

  return (
    <div className="ui-kit">
      <div className="ui-kit-topbar">
        <span className="ui-kit-logo" aria-hidden="true">
          SP
        </span>
        <span className="ui-kit-brand">SpecProof UI Kit</span>
        <span className="ui-kit-brand-sub">DESIGN SYSTEM · PHASE 1</span>
        <span className="ui-kit-spacer" />
        <div className="ui-kit-seg" role="group" aria-label={loc("主题 Theme", "Theme")}>
          {themePrefs.map((pref) => (
            <button
              key={pref.id}
              type="button"
              className="ui-kit-seg-btn"
              aria-pressed={theme === pref.id}
              onClick={() => setTheme(pref.id)}
            >
              <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                {pref.icon}
                {pref.label}
              </span>
            </button>
          ))}
        </div>
        <span className="ui-kit-brand-sub">resolved: {resolved}</span>
        <a className="ui-kit-brand-sub" href="#/dashboard" style={{ textDecoration: "none" }}>
          {loc("← 控制台", "← Console")}
        </a>
      </div>

      <main className="ui-kit-main">
        <div className="ui-anim-fade-in">
          <h1 className="ui-kit-h1">
            SpecProof {loc("设计系统", "Design System")} · <span className="ui-text-gradient">Aurora</span>
          </h1>
          <p className="ui-kit-lead">
            {loc("深色优先 + 浅色主题 · 发丝边框 · 分层海拔 · 紧凑排版 · 克制动效 · 键盘优先。", "Dark-first + light theme · hairline borders · layered elevation · compact type · restrained motion · keyboard-first.")}
            {loc("按 ", "Press ")}<Kbd>Ctrl</Kbd> <Kbd>K</Kbd> {loc("打开命令面板体验全局导航。", "to open the command palette.")}
          </p>
        </div>

        <div className="ui-anim-slide-up ui-anim-delay-1" style={{ marginTop: 24 }}>
          <ControlRoomPreview />
        </div>

        <Section id="colors" zh="色彩" en="Colors">
          <p className="ui-kit-lead">
            {loc("品牌主色为自研「极光 Aurora」对 —— 电光紫", "The brand pair is our own Aurora — electric violet")} <span className="ui-kit-chip">#7C5CFF</span> {loc("与极光青", "and aurora cyan")}{" "}
            <span className="ui-kit-chip">#22D3EE</span>{loc("，中性色基于 zinc 灰阶，状态色全部通过 WCAG AA 对比度。", "Neutrals are zinc shades; status colors all pass WCAG AA contrast.")}
          </p>
          <DemoTitle>{loc("品牌", "Brand")}</DemoTitle>
          <div className="ui-kit-grid-4">
            {ACCENT_SWATCHES.map((s) => (
              <SwatchBlock key={s.token} swatch={s} />
            ))}
          </div>
          <DemoTitle>{loc("中性 Zinc neutrals", "Zinc neutrals")}</DemoTitle>
          <div className="ui-kit-grid-4">
            {NEUTRAL_SWATCHES.map((s) => (
              <SwatchBlock key={s.token} swatch={s} />
            ))}
          </div>
          <DemoTitle>{loc("语义状态 Semantic（随主题切换）", "Semantics (switch with the theme)")}</DemoTitle>
          <div className="ui-kit-grid-2">
            {SEMANTIC_SWATCHES.map((s) => (
              <SwatchBlock key={s.token} swatch={s} />
            ))}
          </div>
          <DemoTitle>{loc("海拔 Elevation", "Elevation")}</DemoTitle>
          <div className="ui-kit-grid-4">
            <div className="ui-elev-demo" style={{ boxShadow: "var(--elev-1)" }}>elev-1</div>
            <div className="ui-elev-demo" style={{ boxShadow: "var(--elev-2)" }}>elev-2</div>
            <div className="ui-elev-demo" style={{ boxShadow: "var(--elev-3)" }}>elev-3</div>
            <div className="ui-elev-demo" style={{ boxShadow: "var(--elev-4)" }}>elev-4</div>
          </div>
        </Section>

        <Section id="typography" zh="排版" en="Typography">
          <p className="ui-kit-lead">
            {loc("系统字体栈（Inter 优先），正文 13px 起步，表格与指标一律 tabular-nums，行高 1.25 / 1.55。", "System font stack (Inter first), body from 13px; tables and metrics are tabular-nums; line-height 1.25 / 1.55.")}
          </p>
          {[
            { size: "var(--text-4xl)", name: "fs-30", sample: loc("验证防火墙 Verification Firewall", "Verification Firewall")},
            { size: "var(--text-3xl)", name: "fs-24", sample: loc("差分验证 · AUTH-01", "Differential verification · AUTH-01")},
            { size: "var(--text-2xl)", name: "fs-20", sample: loc("契约中心 Contract Registry", "Contract Registry")},
            { size: "var(--text-xl)", name: "fs-16", sample: loc("合并证书 Merge Certificate", "Merge Certificate")},
            { size: "var(--text-lg)", name: "fs-14", sample: loc("证据矩阵 Evidence Matrix — 静态 + 运行时双重证据", "Evidence Matrix — static + runtime evidence")},
            { size: "var(--text-sm)", name: "fs-12", sample: loc("辅助信息 Muted caption · 12px", "Muted caption · 12px")},
            { size: "var(--text-xs)", name: "fs-11", sample: "UPPERCASE LABEL · LETTER-SPACING" },
          ].map((row) => (
            <div className="ui-kit-type-row" key={row.name}>
              <span className="ui-kit-type-label">{row.name}</span>
              <span style={{ fontSize: row.size }}>{row.sample}</span>
            </div>
          ))}
          <div className="ui-kit-type-row">
            <span className="ui-kit-type-label">tabular-nums</span>
            <span className="ui-kit-num" style={{ fontSize: "var(--text-2xl)" }}>
              42,918 · 1,024,512 · 96.4% · 4m 12s
            </span>
          </div>
        </Section>

        <Section id="buttons" zh="按钮" en="Buttons">
          <DemoTitle>{loc("变体 Variants", "Variants")}</DemoTitle>
          <Demo>
            <Button variant="primary">{loc("主要操作", "Primary")}</Button>
            <Button variant="secondary">{loc("次要操作", "Secondary")}</Button>
            <Button variant="ghost">{loc("幽灵操作", "Ghost")}</Button>
            <Button variant="danger">{loc("危险操作", "Danger")}</Button>
          </Demo>
          <DemoTitle>{loc("尺寸 Sizes", "Sizes")}</DemoTitle>
          <Demo>
            <Button variant="primary" size="sm">{loc("小 sm", "sm")}</Button>
            <Button variant="primary" size="md">{loc("中 md", "md")}</Button>
            <Button variant="primary" size="lg">{loc("大 lg", "lg")}</Button>
            <Button variant="secondary" size="sm">{loc("小 sm", "sm")}</Button>
            <Button variant="secondary" size="md">{loc("中 md", "md")}</Button>
            <Button variant="secondary" size="lg">{loc("大 lg", "lg")}</Button>
          </Demo>
          <DemoTitle>{loc("状态 States", "States")}</DemoTitle>
          <Demo>
            <Button variant="primary" loading>{loc("提交中", "Submitting…")}</Button>
            <Button variant="secondary" loading>{loc("同步中", "Syncing…")}</Button>
            <Button variant="primary" disabled>{loc("禁用", "Disabled")}</Button>
            <Button variant="danger" disabled>{loc("禁用", "Disabled")}</Button>
            <Button variant="secondary" fullWidth style={{ maxWidth: 240 }}>
              {loc("全宽按钮", "Full width")}
            </Button>
          </Demo>
        </Section>

        <Section id="forms" zh="表单" en="Form fields">
          <p className="ui-kit-lead">{loc("所有控件自带 label、错误与提示状态，错误态会同步 aria-invalid 与描述文本。", "Every control ships label, error and hint states — errors sync aria-invalid and the description text.")}</p>
          <div className="ui-kit-grid-2">
            <div className="ui-kit-demo-col" style={{ gap: 16 }}>
              <Input label={loc("仓库地址 Repository", "Repository")} placeholder="https://github.com/org/repo" hint={loc("Base/Head 差分源", "Base/head differential")} />
              <Input label={loc("任务名称 Job name", "Job name")} required error={loc("任务名称不能为空", "Job name is required")} defaultValue="" placeholder="verify-auth-01" />
              <Input label={loc("禁用 Disabled", "Disabled")} disabled defaultValue={loc("不可编辑", "Read-only")} />
              <Select label={loc("主题基调 Theme", "Theme")} value={selectValue} onChange={(e) => setSelectValue(e.target.value)}>
                <option value="aurora">{loc("Aurora 极光", "Aurora")}</option>
                <option value="zinc">{loc("Zinc 石墨", "Zinc")}</option>
                <option value="mono">{loc("Mono 终端", "Mono")}</option>
              </Select>
              <Textarea
                label={loc("需求规范 Specification", "Specification")}
                value={textValue}
                onChange={(e) => setTextValue(e.target.value)}
                placeholder={loc("粘贴需求文本，或从仓库读取…", "Paste the requirement, or read it from the repo…")}
                hint={textValue.length + " " + loc("字符", "characters")}
              />
            </div>
            <div className="ui-kit-demo-col" style={{ gap: 16 }}>
              <Checkbox label={loc("自动生成回归用例", "Auto-generate regression cases")} checked={checkA} onChange={(e) => setCheckA(e.target.checked)} />
              <Checkbox label={loc("拦截 BLOCKER 自动阻断合并", "Block merges on BLOCKER")} checked={checkB} onChange={(e) => setCheckB(e.target.checked)} />
              <Checkbox label={loc("不确定态 Indeterminate", "Indeterminate")} indeterminate />
              <Checkbox label={loc("错误状态", "Error state")} error={loc("需要先配置 Gate", "Configure a gate first")} checked={false} onChange={() => undefined} />
              <Checkbox label={loc("禁用 Disabled", "Disabled")} disabled checked />
            </div>
          </div>
        </Section>

        <Section id="data" zh="数据展示" en="Data display">
          <DemoTitle>{loc("可排序表格（粘性表头 · 紧凑模式）", "Sortable table (sticky header · compact)")}</DemoTitle>
          <Demo col>
            <div style={{ width: "100%", maxWidth: 560 }}>
              <Table columns={makeFruitColumns(locale)} rows={FRUIT_ROWS} rowKey={(row) => row.name} />
            </div>
            <div style={{ width: "100%", maxWidth: 560, maxHeight: 150 }}>
              <Table columns={makeFruitColumns(locale)} rows={FRUIT_ROWS} rowKey={(row) => row.name} dense />
            </div>
            <div style={{ width: "100%", maxWidth: 560 }}>
              <Table
                columns={makeFruitColumns(locale)}
                rows={[]}
                rowKey={(row) => row.name}
                emptyTitle={loc("没有契约 No contracts", "No contracts")}
                emptyDescription={loc("为当前任务创建一个契约后重试。", "Install a contract for the current task and retry.")}
              />
            </div>
          </Demo>
          <DemoTitle>{loc("徽章 Badges", "Badges")}</DemoTitle>
          <Demo>
            <Badge tone="neutral">NEUTRAL</Badge>
            <Badge tone="accent">ACCENT</Badge>
            <Badge tone="success">VERIFIED</Badge>
            <Badge tone="warning">MAJOR ×2</Badge>
            <Badge tone="danger">BLOCKED</Badge>
            <Badge tone="info">RUNNING</Badge>
          </Demo>
          <DemoTitle>{loc("状态点 StatusDots（running 带脉冲）", "StatusDots (running pulses)")}</DemoTitle>
          <Demo>
            <StatusDot status="running" label={loc("运行中", "Running")} />
            <StatusDot status="success" label={loc("通过", "Passed")} />
            <StatusDot status="warning" label={loc("警告", "Warning")} />
            <StatusDot status="danger" label={loc("失败", "Failed")} />
            <StatusDot status="idle" label={loc("排队", "Queued")} />
            <StatusDot status="neutral" label={loc("未知", "Unknown")} />
          </Demo>
          <DemoTitle>{loc("进度 Progress", "Progress")}</DemoTitle>
          <div className="ui-kit-grid-2">
            <div className="ui-kit-demo-col">
              <Progress label={loc("门禁通过率", "Gate pass rate")} value={98} tone="success" showValue />
              <Progress label={loc("证据覆盖", "Evidence coverage")} value={86} showValue />
              <Progress label={loc("回归检测", "Regressions caught")} value={74} tone="warning" showValue />
              <Progress label={loc("风险", "Risk")} value={12} tone="danger" showValue size="sm" />
              <Progress label={loc("大尺寸", "Large size")} value={60} size="lg" />
            </div>
            <Demo col>
              <DemoTitle>{loc("事件时间线 Timeline（job events）", "Timeline (job events)")}</DemoTitle>
              <Timeline events={JOB_TIMELINE} />
            </Demo>
          </div>
          <DemoTitle>{loc("面包屑 Breadcrumbs", "Breadcrumbs")}</DemoTitle>
          <Demo>
            <Breadcrumbs
              items={[
                { label: "Agent", href: "#/agent" },
                { label: loc("任务", "Tasks"), href: "#/agent" },
                { label: "SP-2480" },
              ]}
            />
          </Demo>
          <DemoTitle>{loc("键盘键 Kbd", "Kbd")}</DemoTitle>
          <Demo>
            <Kbd>Ctrl</Kbd>
            <Kbd>K</Kbd>
            <Kbd>↵</Kbd>
            <Kbd>Esc</Kbd>
            <Kbd>Shift</Kbd>
            <Kbd>Tab</Kbd>
          </Demo>
        </Section>

        <Section id="navigation" zh="导航" en="Navigation">
          <DemoTitle>{loc("标签页 Tabs（← → 方向键切换）", "Tabs (← → to switch)")}</DemoTitle>
          <Demo col>
            <Tabs
              ariaLabel={loc("示例标签页", "Example tabs")}
              items={[
                { id: "overview", label: loc("总览", "Overview"), content: <p style={{ fontSize: "var(--text-md)", color: "var(--color-text-2)" }}>{loc("总览面板 — 任务统计与最近验证。", "Overview — task stats and recent verifications.")}</p> },
                { id: "matrix", label: loc("证据矩阵", "Matrix"), content: <p style={{ fontSize: "var(--text-md)", color: "var(--color-text-2)" }}>{loc("矩阵面板 — 契约 × 证据类型。", "Matrix panel — contract × evidence type.")}</p> },
                { id: "gates", label: loc("门禁", "Gates"), content: <p style={{ fontSize: "var(--text-md)", color: "var(--color-text-2)" }}>{loc("门禁面板 — 通过 / 阻断 / 待复核。", "Gates panel — pass / block / review.")}</p> },
                { id: "disabled", label: loc("禁用", "Disabled"), content: loc("禁用", "Disabled"), disabled: true },
              ]}
            />
          </Demo>
          <DemoTitle>{loc("提示 Tooltip（悬停 / 聚焦 300ms 延迟）", "Tooltip (hover / focus, 300ms delay)")}</DemoTitle>
          <Demo>
            <Tooltip content={loc("顶部提示 Top", "Top")}>
              <Button variant="secondary" size="sm">Top</Button>
            </Tooltip>
            <Tooltip content={loc("底部提示 Bottom", "Bottom")} side="bottom">
              <Button variant="secondary" size="sm">Bottom</Button>
            </Tooltip>
            <Tooltip content={loc("左侧提示 Left", "Left")} side="left">
              <Button variant="secondary" size="sm">Left</Button>
            </Tooltip>
            <Tooltip content={loc("右侧提示 Right", "Right")} side="right">
              <Button variant="secondary" size="sm">Right</Button>
            </Tooltip>
          </Demo>
          <DemoTitle>{loc("命令面板 CommandPalette（Ctrl / Cmd + K）", "CommandPalette (Ctrl / Cmd + K)")}</DemoTitle>
          <Demo col>
            <p style={{ fontSize: "var(--text-md)", color: "var(--color-text-2)" }}>
              {loc("面板已全局挂载：可导航全部 ", "Mounted globally — navigate all ")}<span className="ui-kit-chip">/agent/*</span> {loc("与已验证路由、切换主题、打开", " and verified routes, switch themes, and open")}
              {loc("localStorage 中的最近任务。现在按 ", "Recent tasks in localStorage. Press ")}<Kbd>Ctrl</Kbd> <Kbd>K</Kbd> {loc("试试 —— 本页面无需登录即可使用。", "to try it — no login required on this page.")}
            </p>
          </Demo>
          <DemoTitle>{loc("键盘快捷键 ShortcutHelp（按 ", "ShortcutHelp (press ")}<Kbd>?</Kbd>{loc(" 打开）", ") to open")}</DemoTitle>
          <Demo col>
            <Table
              columns={makeShortcutColumns(locale)}
              rows={SHORTCUT_ROWS}
              rowKey={(row) => row.group + ":" + row.label}
              dense
            />
          </Demo>
        </Section>

        <Section id="feedback" zh="反馈" en="Feedback">
          <DemoTitle>{loc("对话框 Modal（焦点陷阱 · Esc 关闭）", "Modal (focus trap · Esc closes)")}</DemoTitle>
          <Demo>
            <Button variant="primary" onClick={() => setModalOpen(true)}>{loc("打开对话框", "Open dialog")}</Button>
            <span className="ui-kit-chip">{loc("Esc 关闭 · Tab 焦点循环 · 关闭后焦点还原", "Esc closes · Tab cycles focus · focus returns on close")}</span>
          </Demo>
          <DemoTitle>{loc("通知 Toast（右下角堆叠 · 悬停暂停）", "Toast (bottom-right · hover pauses)")}</DemoTitle>
          <Demo>
            <Button variant="primary" size="sm" onClick={() => toast.toast({ title: loc("验证通过", "Verified"), description: loc("SP-2481 · AUTH-01 全部契约通过", "SP-2481 · AUTH-01 all contracts passed"), tone: "success" })}>{loc("成功", "Success")}</Button>
            <Button variant="secondary" size="sm" onClick={() => toast.toast({ title: loc("正在执行", "Running"), description: loc("差分执行运行中，预计 40s", "Differential running, ~40s left"), tone: "info" })}>{loc("信息", "Info")}</Button>
            <Button variant="secondary" size="sm" onClick={() => toast.toast({ title: loc("2 个 MAJOR", "2 MAJORS"), description: loc("证据矩阵存在未处理警告", "The matrix carries unhandled warnings"), tone: "warning" })}>{loc("警告", "Warning")}</Button>
            <Button variant="danger" size="sm" onClick={() => toast.toast({ title: loc("BLOCKER 拦截", "BLOCKER gate"), description: loc("base_pass_head_fail · H2 取证", "base_pass_head_fail · H2 evidence"), tone: "danger", duration: 0 })}>{loc("错误（常驻）", "Error (persistent)")}</Button>
          </Demo>
          <DemoTitle>{loc("骨架屏 Skeleton", "Skeleton")}</DemoTitle>
          <Demo col>
            <Skeleton variant="text" width={240} />
            <Skeleton variant="text" width={320} />
            <Skeleton variant="rect" width={320} height={64} />
            <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <Skeleton variant="circle" width={36} height={36} />
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <Skeleton variant="text" width={160} />
                <Skeleton variant="text" width={110} />
              </div>
            </div>
          </Demo>
          <DemoTitle>{loc("空状态 EmptyState", "EmptyState")}</DemoTitle>
          <Demo col>
            <EmptyState
              icon={<InboxIcon size={18} />}
              title={loc("暂无验证任务 No jobs yet", "No jobs yet")}
              description={loc("创建第一个验证任务后，执行管道与证据矩阵会显示在这里。", "Run your first verification — the pipeline and evidence matrix appear here.")}
              action={<Button variant="secondary" size="sm">{loc("新建任务", "New task")}</Button>}
            />
          </Demo>
        </Section>

        <Section id="cards" zh="卡片" en="Cards">
          <div className="ui-kit-grid-2">
            <Card title={loc("契约中心 Contract registry", "Contract registry")} subtitle={loc("6 契约 · 2 高优先级", "6 contracts · 2 high priority")} actions={<Badge tone="accent">LIVE</Badge>}>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: "var(--text-md)" }}>
                <span>{loc("AUTH-01 · 邮箱变更认证 — ", "AUTH-01 · email-change auth — ")}<Badge tone="success">PASS</Badge></span>
                <span>{loc("EVT-04 · 事件幂等 — ", "EVT-04 · event idempotency — ")}<Badge tone="info">RUNNING</Badge></span>
                <span>{loc("BROKER-02 · 重试去重 — ", "BROKER-02 · retry dedup — ")}<Badge tone="danger">FAIL</Badge></span>
              </div>
            </Card>
            <Card
              title={loc("门禁 Gates", "Gates")}
              subtitle={loc("合并前检查", "Pre-merge check")}
              actions={<Button variant="ghost" size="sm">{loc("编辑", "Edit")}</Button>}
            >
              <Progress label={loc("通过率", "Pass rate")} value={98} tone="success" showValue />
            </Card>
          </div>
        </Section>

        <footer className="ui-kit-foot">
          <span>SpecProof UI Kit · Phase 1 foundation — tokens / theme / 21 components / palette</span>
          <span>
            {loc("动效 ", "Motion ")}<span className="ui-kit-chip">120–240ms</span>{loc(" · 全部遵循 prefers-reduced-motion", " · all honoring prefers-reduced-motion")}
          </span>
        </footer>
      </main>

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={loc("新建验证任务", "New verification")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setModalOpen(false)}>{loc("取消", "Cancel")}</Button>
            <Button variant="primary" onClick={() => setModalOpen(false)}>{loc("创建任务", "Create task")}</Button>
          </>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Input label={loc("任务名称", "Job name")} placeholder="verify-auth-01" />
          <Input label={loc("仓库地址", "Repository")} placeholder="https://github.com/org/repo" />
          <Select label={loc("基线 Base", "Baseline")}>
            <option>main</option>
            <option>release/v1</option>
          </Select>
          <Checkbox label={loc("自动生成回归用例", "Auto-generate regression cases")} defaultChecked />
        </div>
      </Modal>
    </div>
  );
}
