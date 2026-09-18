import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { clearApiKey, clearBearerToken, consumeOidcCallback, getApiKey, getAuthMe, getBearerToken } from "./api";
import type { PrincipalInfo } from "./api";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import TenantSwitcher from "./identity/TenantSwitcher";
import { ThemeProvider, useTheme } from "./theme/ThemeProvider";
import { Button, CommandPalette, ErrorBoundary, Kbd, Spinner, ToastProvider } from "./ui";
import { MoonIcon, SearchIcon, SunIcon } from "./ui/icons";
import { ProductIcon, type ProductIconName } from "./ui/ProductIcon";

const Jobs = lazy(() => import("./pages/Jobs"));
const NewVerification = lazy(() => import("./pages/NewVerification"));
const JobDetail = lazy(() => import("./pages/JobDetail"));
const Matrix = lazy(() => import("./pages/Matrix"));
const FindingDetail = lazy(() => import("./pages/FindingDetail"));
const Contracts = lazy(() => import("./pages/Contracts"));
const Eval = lazy(() => import("./pages/Eval"));
const Health = lazy(() => import("./pages/Health"));
const Billing = lazy(() => import("./pages/Billing"));
const AgentApp = lazy(() => import("./agent/AgentApp"));
const IdentityApp = lazy(() => import("./identity/IdentityApp"));
const UiKit = lazy(() => import("./ui-kit/UiKit"));
const ModelSettings = lazy(() => import("./pages/ModelSettings"));
const Guide = lazy(() => import("./pages/Guide"));

type NavItem = { path: string; label: string; icon: ProductIconName; group: string };
const NAV: NavItem[] = [
  { path: "dashboard", label: "工作台", icon: "overview", group: "工作空间" },
  { path: "jobs", label: "变更验收", icon: "verify", group: "工作空间" },
  { path: "agent", label: "AI 开发", icon: "agent", group: "工作空间" },
  { path: "matrix", label: "需求覆盖", icon: "matrix", group: "质量与证据" },
  { path: "contracts", label: "验收规则", icon: "contracts", group: "质量与证据" },
  { path: "eval", label: "效果评测", icon: "chart", group: "质量与证据" },
  { path: "identity", label: "团队与权限", icon: "team", group: "管理" },
  { path: "billing", label: "用量与账单", icon: "billing", group: "管理" },
  { path: "settings", label: "模型连接", icon: "agent", group: "管理" },
  { path: "health", label: "服务状态", icon: "health", group: "管理" },
];

function renderRoute(route: string): JSX.Element {
  // Query params (e.g. #/jobs/new?repo=...) belong to the page, not routing.
  const seg = route.replace(/^#/, "").split("?")[0].split("/").filter(Boolean);
  if (!seg.length || seg[0] === "dashboard") return <Dashboard />;
  if (seg[0] === "settings") return <ModelSettings />;
  if (seg[0] === "guide") return <Guide />;
  if (seg[0] === "login") return <Login />;
  if (seg[0] === "agent") return <AgentApp seg={seg} />;
  if (seg[0] === "identity") return <IdentityApp seg={seg} />;
  if (seg[0] === "jobs") {
    if (seg[1] === "new") return <NewVerification />;
    return seg[1] ? <JobDetail jobId={decodeURIComponent(seg[1])} /> : <Jobs />;
  }
  if (seg[0] === "matrix") return <Matrix />;
  if (seg[0] === "findings" && seg.length >= 3) return <FindingDetail jobId={decodeURIComponent(seg[1])} findingId={decodeURIComponent(seg[2])} />;
  if (seg[0] === "contracts") return <Contracts />;
  if (seg[0] === "eval") return <Eval />;
  if (seg[0] === "health") return <Health />;
  if (seg[0] === "billing") return <Billing />;
  return <div className="product-empty"><ProductIcon name="guide" size={36} /><h1>没有找到这个页面</h1><p>链接可能已更新，你可以回到工作台继续。</p><a className="btn btn-primary" href="#/dashboard">返回工作台</a></div>;
}

function Workspace() {
  const [route, setRoute] = useState(() => window.location.hash || "#/dashboard");
  const [hasKey, setHasKey] = useState(() => getApiKey() !== "" || getBearerToken() !== "");
  const [principal, setPrincipal] = useState<PrincipalInfo | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const contentRef = useRef<HTMLElement>(null);
  const { resolved, toggle } = useTheme();
  useEffect(() => {
    const onChange = () => { setRoute(window.location.hash || "#/dashboard"); setMenuOpen(false); };
    window.addEventListener("hashchange", onChange);
    if (consumeOidcCallback()) setHasKey(true);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  useEffect(() => {
    if (!hasKey || !getBearerToken()) return;
    let alive = true;
    getAuthMe().then(me => { if (alive && me?.principal) setPrincipal(me.principal); }).catch(() => {});
    return () => { alive = false; };
  }, [hasKey]);
  const active = route.replace(/^#\//, "").split("/")[0] || "dashboard";
  const label = NAV.find(item => item.path === active)?.label || (active === "guide" ? "上手指南" : "验收详情");
  useEffect(() => {
    document.title = label + " · SpecProof";
    contentRef.current?.scrollTo?.(0, 0);
  }, [route, label]);
  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setMenuOpen(false); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, []);

  if (active === "ui-kit") return <Suspense fallback={<Spinner />}><UiKit /></Suspense>;
  if (!hasKey && active !== "guide") return <Login onConnected={() => setHasKey(true)} />;
  const canManage = principal == null || principal.roles?.some(r => ["admin", "operator"].includes(r));
  const canBill = principal == null || principal.roles?.some(r => ["admin", "operator", "auditor"].includes(r));
  const nav = NAV.filter(item => (item.path !== "identity" || canManage) && (item.path !== "billing" || canBill));

  return <div className="shell product-shell">
    <a className="skip-link" href="#main-content" onClick={e => { e.preventDefault(); contentRef.current?.focus(); }}>跳至主要内容</a>
    {menuOpen && <button className="nav-backdrop" aria-label="关闭导航" onClick={() => setMenuOpen(false)} />}
    <aside className={"sidebar" + (menuOpen ? " sidebar-open" : "")} id="workspace-navigation">
      <a className="brand" href="#/dashboard" aria-label="SpecProof 工作台"><span className="brand-mark"><ProductIcon name="shield" size={23} /></span><span><span className="brand-name">SpecProof<span className="brand-dot">.</span></span><span className="brand-sub">让每一次交付，有据可依</span></span></a>
      <div className="workspace-selector"><span className="workspace-avatar">W</span><span><strong>我的工作空间</strong><small>代码变更验收平台</small></span><ProductIcon name="verify" size={16} /></div>
      <nav aria-label="主导航 Primary navigation">
        {["工作空间", "质量与证据", "管理"].map(group => <div className="nav-group" key={group}><div className="nav-group-label">{group}</div>{nav.filter(item => item.group === group).map(item => <a key={item.path} href={"#/" + item.path} aria-current={active === item.path ? "page" : undefined} className={"nav-item" + (active === item.path ? " nav-active" : "")}><ProductIcon name={item.icon} size={18} /><span className="nav-label">{item.label}</span>{item.path === "agent" && <span className="nav-tag">CRAFT</span>}</a>)}</div>)}
      </nav>
      <div className="sidebar-guide"><ProductIcon name="guide" /><strong>第一次使用 SpecProof？</strong><p>从一个变更开始，了解完整验收流程。</p><a href="#/guide">阅读上手指南 <span aria-hidden="true">↗</span></a></div>
      <div className="sidebar-foot"><TenantSwitcher /><div className="account-row"><span className="account-avatar">{hasKey ? "SP" : "?"}</span><span><strong>{hasKey ? "当前会话" : "访客"}</strong><small>{hasKey ? "凭据已配置" : "连接后开始验收"}</small></span><Button variant="ghost" size="sm" onClick={() => { clearApiKey(); clearBearerToken(); setPrincipal(null); setHasKey(false); window.location.hash = "#/login"; }}>{hasKey ? "退出" : "连接"}</Button></div></div>
    </aside>
    <div className="workspace-main"><header className="workspace-topbar"><div className="topbar-left"><button className="icon-button mobile-menu" aria-label="打开导航" aria-expanded={menuOpen} aria-controls="workspace-navigation" onClick={() => setMenuOpen(!menuOpen)}><ProductIcon name={menuOpen ? "close" : "menu"} /></button><span className="topbar-workspace">工作空间</span><span className="breadcrumb-separator">/</span><strong>{label}</strong></div><div className="topbar-actions"><button className="command-trigger" onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }))}><SearchIcon /><span>搜索页面与操作</span><Kbd>Ctrl K</Kbd></button><a className="topbar-help" href="#/guide">使用帮助</a><button className="icon-button" aria-label={resolved === "dark" ? "切换浅色主题" : "切换深色主题"} onClick={toggle}>{resolved === "dark" ? <SunIcon size={18} /> : <MoonIcon size={18} />}</button></div></header>
      <main className="content" id="main-content" tabIndex={-1} ref={contentRef}><ErrorBoundary key={active}><Suspense fallback={<Spinner />}>{renderRoute(route)}</Suspense></ErrorBoundary><footer className="workspace-footer"><span>SpecProof · 为交付提供可核验的证据</span><a href="#/guide">从这里开始 <span aria-hidden="true">↗</span></a></footer></main>
    </div>
  </div>;
}

export default function App() {
  return <ThemeProvider><ToastProvider><ErrorBoundary><Workspace /></ErrorBoundary><CommandPalette /></ToastProvider></ThemeProvider>;
}
