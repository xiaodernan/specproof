import { useState, type ReactNode } from "react";
import { useTheme, type ThemePreference } from "../theme/useTheme";
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

/* ── demo data ────────────────────────────────────────────── */

interface FruitRow {
  name: string;
  qty: number;
  price: number;
}

const FRUIT_COLUMNS: Column<FruitRow>[] = [
  { key: "name", header: "名称" },
  {
    key: "qty",
    header: "库存",
    align: "right",
    sortable: true,
    render: (row) => <span className="ui-kit-num">{row.qty}</span>,
  },
  {
    key: "price",
    header: "单价 ¥",
    align: "right",
    sortable: true,
    sortValue: (row) => row.price,
    render: (row) => <span className="ui-kit-num">{row.price.toFixed(2)}</span>,
  },
];

const FRUIT_ROWS: FruitRow[] = [
  { name: "荔枝 Lychee", qty: 128, price: 12.5 },
  { name: "山竹 Mangosteen", qty: 64, price: 28.0 },
  { name: "杨梅 Bayberry", qty: 210, price: 9.9 },
  { name: "枇杷 Loquat", qty: 47, price: 16.8 },
  { name: "莲雾 Wax apple", qty: 32, price: 22.0 },
];

const JOB_TIMELINE: TimelineEvent[] = [
  { id: "t1", title: "intake — 需求接收", description: "规格 spec-v1.2 解析完成", time: "09:41:02", status: "success" },
  { id: "t2", title: "compile — 契约编译", description: "6 契约 · 2 高优先级", time: "09:41:18", status: "success" },
  { id: "t3", title: "differential — 差分执行", description: "base→head-v1 JUnit 运行中", time: "09:42:05", status: "running" },
  { id: "t4", title: "review — 审查庭复核", description: "等待证据汇总", time: "—", status: "idle" },
  { id: "t5", title: "publish — 报告发布", description: "矩阵 + 证书", time: "—", status: "idle" },
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

function Section(props: { id: string; title: string; en: string; children: ReactNode }): JSX.Element {
  return (
    <section className="ui-kit-section" id={props.id}>
      <h2 className="ui-kit-h2">
        {props.title} <span className="ui-kit-h2-id">{props.en}</span>
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

  const themePrefs: Array<{ id: ThemePreference; label: string; icon: ReactNode }> = [
    { id: "system", label: "跟随系统", icon: null },
    { id: "dark", label: "深色", icon: <MoonIcon size={12} /> },
    { id: "light", label: "浅色", icon: <SunIcon size={12} /> },
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
        <div className="ui-kit-seg" role="group" aria-label="主题 Theme">
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
          ← 控制台
        </a>
      </div>

      <main className="ui-kit-main">
        <div className="ui-anim-fade-in">
          <h1 className="ui-kit-h1">
            SpecProof 设计系统 · <span className="ui-text-gradient">Aurora</span>
          </h1>
          <p className="ui-kit-lead">
            深色优先 + 浅色主题 · 发丝边框 · 分层海拔 · 紧凑排版 · 克制动效 · 键盘优先。
            按 <Kbd>Ctrl</Kbd> <Kbd>K</Kbd> 打开命令面板体验全局导航。
          </p>
        </div>

        <div className="ui-anim-slide-up ui-anim-delay-1" style={{ marginTop: 24 }}>
          <ControlRoomPreview />
        </div>

        <Section id="colors" title="色彩 Colors" en="tokens.css">
          <p className="ui-kit-lead">
            品牌主色为自研「极光 Aurora」对 —— 电光紫 <span className="ui-kit-chip">#7C5CFF</span> 与极光青{" "}
            <span className="ui-kit-chip">#22D3EE</span>，中性色基于 zinc 灰阶，状态色全部通过 WCAG AA 对比度。
          </p>
          <DemoTitle>品牌 Brand</DemoTitle>
          <div className="ui-kit-grid-4">
            {ACCENT_SWATCHES.map((s) => (
              <SwatchBlock key={s.token} swatch={s} />
            ))}
          </div>
          <DemoTitle>中性 Zinc neutrals</DemoTitle>
          <div className="ui-kit-grid-4">
            {NEUTRAL_SWATCHES.map((s) => (
              <SwatchBlock key={s.token} swatch={s} />
            ))}
          </div>
          <DemoTitle>语义状态 Semantic（随主题切换）</DemoTitle>
          <div className="ui-kit-grid-2">
            {SEMANTIC_SWATCHES.map((s) => (
              <SwatchBlock key={s.token} swatch={s} />
            ))}
          </div>
          <DemoTitle>海拔 Elevation</DemoTitle>
          <div className="ui-kit-grid-4">
            <div className="ui-elev-demo" style={{ boxShadow: "var(--elev-1)" }}>elev-1</div>
            <div className="ui-elev-demo" style={{ boxShadow: "var(--elev-2)" }}>elev-2</div>
            <div className="ui-elev-demo" style={{ boxShadow: "var(--elev-3)" }}>elev-3</div>
            <div className="ui-elev-demo" style={{ boxShadow: "var(--elev-4)" }}>elev-4</div>
          </div>
        </Section>

        <Section id="typography" title="排版 Typography" en="system-ui / Inter stack">
          <p className="ui-kit-lead">
            系统字体栈（Inter 优先），正文 13px 起步，表格与指标一律 tabular-nums，行高 1.25 / 1.55。
          </p>
          {[
            { size: "var(--fs-30)", name: "fs-30", sample: "验证防火墙 Verification Firewall" },
            { size: "var(--fs-24)", name: "fs-24", sample: "差分验证 · AUTH-01" },
            { size: "var(--fs-20)", name: "fs-20", sample: "契约中心 Contract Registry" },
            { size: "var(--fs-16)", name: "fs-16", sample: "合并证书 Merge Certificate" },
            { size: "var(--fs-14)", name: "fs-14", sample: "证据矩阵 Evidence Matrix — 静态 + 运行时双重证据" },
            { size: "var(--fs-12)", name: "fs-12", sample: "辅助信息 Muted caption · 12px" },
            { size: "var(--fs-11)", name: "fs-11", sample: "UPPERCASE LABEL · LETTER-SPACING" },
          ].map((row) => (
            <div className="ui-kit-type-row" key={row.name}>
              <span className="ui-kit-type-label">{row.name}</span>
              <span style={{ fontSize: row.size }}>{row.sample}</span>
            </div>
          ))}
          <div className="ui-kit-type-row">
            <span className="ui-kit-type-label">tabular-nums</span>
            <span className="ui-kit-num" style={{ fontSize: "var(--fs-20)" }}>
              42,918 · 1,024,512 · 96.4% · 4m 12s
            </span>
          </div>
        </Section>

        <Section id="buttons" title="按钮 Buttons" en="primary / secondary / ghost / danger">
          <DemoTitle>变体 Variants</DemoTitle>
          <Demo>
            <Button variant="primary">主要操作</Button>
            <Button variant="secondary">次要操作</Button>
            <Button variant="ghost">幽灵操作</Button>
            <Button variant="danger">危险操作</Button>
          </Demo>
          <DemoTitle>尺寸 Sizes</DemoTitle>
          <Demo>
            <Button variant="primary" size="sm">小 sm</Button>
            <Button variant="primary" size="md">中 md</Button>
            <Button variant="primary" size="lg">大 lg</Button>
            <Button variant="secondary" size="sm">小 sm</Button>
            <Button variant="secondary" size="md">中 md</Button>
            <Button variant="secondary" size="lg">大 lg</Button>
          </Demo>
          <DemoTitle>状态 States</DemoTitle>
          <Demo>
            <Button variant="primary" loading>提交中</Button>
            <Button variant="secondary" loading>同步中</Button>
            <Button variant="primary" disabled>禁用</Button>
            <Button variant="danger" disabled>禁用</Button>
            <Button variant="secondary" fullWidth style={{ maxWidth: 240 }}>
              全宽按钮
            </Button>
          </Demo>
        </Section>

        <Section id="forms" title="表单 Form fields" en="label + error + hint">
          <p className="ui-kit-lead">所有控件自带 label、错误与提示状态，错误态会同步 aria-invalid 与描述文本。</p>
          <div className="ui-kit-grid-2">
            <div className="ui-kit-demo-col" style={{ gap: 16 }}>
              <Input label="仓库地址 Repository" placeholder="https://github.com/org/repo" hint="Base/Head 差分源" />
              <Input label="任务名称 Job name" required error="任务名称不能为空" defaultValue="" placeholder="verify-auth-01" />
              <Input label="禁用 Disabled" disabled defaultValue="不可编辑" />
              <Select label="主题基调 Theme" value={selectValue} onChange={(e) => setSelectValue(e.target.value)}>
                <option value="aurora">Aurora 极光</option>
                <option value="zinc">Zinc 石墨</option>
                <option value="mono">Mono 终端</option>
              </Select>
              <Textarea
                label="需求规范 Specification"
                value={textValue}
                onChange={(e) => setTextValue(e.target.value)}
                placeholder="粘贴需求文本，或从仓库读取…"
                hint={textValue.length + " 字符"}
              />
            </div>
            <div className="ui-kit-demo-col" style={{ gap: 16 }}>
              <Checkbox label="自动生成回归用例" checked={checkA} onChange={(e) => setCheckA(e.target.checked)} />
              <Checkbox label="拦截 BLOCKER 自动阻断合并" checked={checkB} onChange={(e) => setCheckB(e.target.checked)} />
              <Checkbox label="不确定态 Indeterminate" indeterminate />
              <Checkbox label="错误状态" error="需要先配置 Gate" checked={false} onChange={() => undefined} />
              <Checkbox label="禁用 Disabled" disabled checked />
            </div>
          </div>
        </Section>

        <Section id="data" title="数据展示 Data display" en="tables · badges · dots · progress · timeline">
          <DemoTitle>可排序表格（粘性表头 · 紧凑模式）</DemoTitle>
          <Demo col>
            <div style={{ width: "100%", maxWidth: 560 }}>
              <Table columns={FRUIT_COLUMNS} rows={FRUIT_ROWS} rowKey={(row) => row.name} />
            </div>
            <div style={{ width: "100%", maxWidth: 560, maxHeight: 150 }}>
              <Table columns={FRUIT_COLUMNS} rows={FRUIT_ROWS} rowKey={(row) => row.name} dense />
            </div>
            <div style={{ width: "100%", maxWidth: 560 }}>
              <Table
                columns={FRUIT_COLUMNS}
                rows={[]}
                rowKey={(row) => row.name}
                emptyTitle="没有契约 No contracts"
                emptyDescription="为当前任务创建一个契约后重试。"
              />
            </div>
          </Demo>
          <DemoTitle>徽章 Badges</DemoTitle>
          <Demo>
            <Badge tone="neutral">NEUTRAL</Badge>
            <Badge tone="accent">ACCENT</Badge>
            <Badge tone="success">VERIFIED</Badge>
            <Badge tone="warning">MAJOR ×2</Badge>
            <Badge tone="danger">BLOCKED</Badge>
            <Badge tone="info">RUNNING</Badge>
          </Demo>
          <DemoTitle>状态点 StatusDots（running 带脉冲）</DemoTitle>
          <Demo>
            <StatusDot status="running" label="运行中" />
            <StatusDot status="success" label="通过" />
            <StatusDot status="warning" label="警告" />
            <StatusDot status="danger" label="失败" />
            <StatusDot status="idle" label="排队" />
            <StatusDot status="neutral" label="未知" />
          </Demo>
          <DemoTitle>进度 Progress</DemoTitle>
          <div className="ui-kit-grid-2">
            <div className="ui-kit-demo-col">
              <Progress label="门禁通过率" value={98} tone="success" showValue />
              <Progress label="证据覆盖" value={86} showValue />
              <Progress label="回归检测" value={74} tone="warning" showValue />
              <Progress label="风险" value={12} tone="danger" showValue size="sm" />
              <Progress label="大尺寸" value={60} size="lg" />
            </div>
            <Demo col>
              <DemoTitle>事件时间线 Timeline（job events）</DemoTitle>
              <Timeline events={JOB_TIMELINE} />
            </Demo>
          </div>
          <DemoTitle>面包屑 Breadcrumbs</DemoTitle>
          <Demo>
            <Breadcrumbs
              items={[
                { label: "Agent", href: "#/agent" },
                { label: "任务", href: "#/agent" },
                { label: "SP-2480" },
              ]}
            />
          </Demo>
          <DemoTitle>键盘键 Kbd</DemoTitle>
          <Demo>
            <Kbd>Ctrl</Kbd>
            <Kbd>K</Kbd>
            <Kbd>↵</Kbd>
            <Kbd>Esc</Kbd>
            <Kbd>Shift</Kbd>
            <Kbd>Tab</Kbd>
          </Demo>
        </Section>

        <Section id="navigation" title="导航 Navigation" en="tabs · tooltips · command palette">
          <DemoTitle>标签页 Tabs（← → 方向键切换）</DemoTitle>
          <Demo col>
            <Tabs
              ariaLabel="示例标签页"
              items={[
                { id: "overview", label: "总览", content: <p style={{ fontSize: "var(--fs-13)", color: "var(--color-text-2)" }}>总览面板 — 任务统计与最近验证。</p> },
                { id: "matrix", label: "证据矩阵", content: <p style={{ fontSize: "var(--fs-13)", color: "var(--color-text-2)" }}>矩阵面板 — 契约 × 证据类型。</p> },
                { id: "gates", label: "门禁", content: <p style={{ fontSize: "var(--fs-13)", color: "var(--color-text-2)" }}>门禁面板 — 通过 / 阻断 / 待复核。</p> },
                { id: "disabled", label: "禁用", disabled: true },
              ]}
            />
          </Demo>
          <DemoTitle>提示 Tooltip（悬停 / 聚焦 300ms 延迟）</DemoTitle>
          <Demo>
            <Tooltip content="顶部提示 Top">
              <Button variant="secondary" size="sm">Top</Button>
            </Tooltip>
            <Tooltip content="底部提示 Bottom" side="bottom">
              <Button variant="secondary" size="sm">Bottom</Button>
            </Tooltip>
            <Tooltip content="左侧提示 Left" side="left">
              <Button variant="secondary" size="sm">Left</Button>
            </Tooltip>
            <Tooltip content="右侧提示 Right" side="right">
              <Button variant="secondary" size="sm">Right</Button>
            </Tooltip>
          </Demo>
          <DemoTitle>命令面板 CommandPalette（Ctrl / Cmd + K）</DemoTitle>
          <Demo col>
            <p style={{ fontSize: "var(--fs-13)", color: "var(--color-text-2)" }}>
              面板已全局挂载：可导航全部 <span className="ui-kit-chip">/agent/*</span> 与已验证路由、切换主题、打开
              localStorage 中的最近任务。现在按 <Kbd>Ctrl</Kbd> <Kbd>K</Kbd> 试试 —— 本页面无需登录即可使用。
            </p>
          </Demo>
        </Section>

        <Section id="feedback" title="反馈 Feedback" en="modal · toast · skeleton · empty state">
          <DemoTitle>对话框 Modal（焦点陷阱 · Esc 关闭）</DemoTitle>
          <Demo>
            <Button variant="primary" onClick={() => setModalOpen(true)}>打开对话框</Button>
            <span className="ui-kit-chip">Esc 关闭 · Tab 焦点循环 · 关闭后焦点还原</span>
          </Demo>
          <DemoTitle>通知 Toast（右下角堆叠 · 悬停暂停）</DemoTitle>
          <Demo>
            <Button variant="primary" size="sm" onClick={() => toast.toast({ title: "验证通过", description: "SP-2481 · AUTH-01 全部契约通过", tone: "success" })}>成功</Button>
            <Button variant="secondary" size="sm" onClick={() => toast.toast({ title: "正在执行", description: "差分执行运行中，预计 40s", tone: "info" })}>信息</Button>
            <Button variant="secondary" size="sm" onClick={() => toast.toast({ title: "2 个 MAJOR", description: "证据矩阵存在未处理警告", tone: "warning" })}>警告</Button>
            <Button variant="danger" size="sm" onClick={() => toast.toast({ title: "BLOCKER 拦截", description: "base_pass_head_fail · H2 取证", tone: "danger", duration: 0 })}>错误（常驻）</Button>
          </Demo>
          <DemoTitle>骨架屏 Skeleton</DemoTitle>
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
          <DemoTitle>空状态 EmptyState</DemoTitle>
          <Demo col>
            <EmptyState
              icon={<InboxIcon size={18} />}
              title="暂无验证任务 No jobs yet"
              description="创建第一个验证任务后，执行管道与证据矩阵会显示在这里。"
              action={<Button variant="secondary" size="sm">新建任务</Button>}
            />
          </Demo>
        </Section>

        <Section id="cards" title="卡片 Cards" en="hairline + layered elevation">
          <div className="ui-kit-grid-2">
            <Card title="契约中心 Contract registry" subtitle="6 契约 · 2 高优先级" actions={<Badge tone="accent">LIVE</Badge>}>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: "var(--fs-13)" }}>
                <span>AUTH-01 · 邮箱变更认证 — <Badge tone="success">PASS</Badge></span>
                <span>EVT-04 · 事件幂等 — <Badge tone="info">RUNNING</Badge></span>
                <span>BROKER-02 · 重试去重 — <Badge tone="danger">FAIL</Badge></span>
              </div>
            </Card>
            <Card
              title="门禁 Gates"
              subtitle="合并前检查"
              actions={<Button variant="ghost" size="sm">编辑</Button>}
            >
              <Progress label="通过率" value={98} tone="success" showValue />
            </Card>
          </div>
        </Section>

        <footer className="ui-kit-foot">
          <span>SpecProof UI Kit · Phase 1 foundation — tokens / theme / 21 components / palette</span>
          <span>
            动效 <span className="ui-kit-chip">120–240ms</span> · 全部遵循 prefers-reduced-motion
          </span>
        </footer>
      </main>

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title="新建验证任务"
        footer={
          <>
            <Button variant="ghost" onClick={() => setModalOpen(false)}>取消</Button>
            <Button variant="primary" onClick={() => setModalOpen(false)}>创建任务</Button>
          </>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Input label="任务名称" placeholder="verify-auth-01" />
          <Input label="仓库地址" placeholder="https://github.com/org/repo" />
          <Select label="基线 Base">
            <option>main</option>
            <option>release/v1</option>
          </Select>
          <Checkbox label="自动生成回归用例" defaultChecked />
        </div>
      </Modal>
    </div>
  );
}
