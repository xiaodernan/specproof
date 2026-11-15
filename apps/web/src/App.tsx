import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { consumeOidcCallback, getApiKey, getAuthMe, getBearerToken, logout } from "./api";
import type { PrincipalInfo } from "./api";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import TenantSwitcher from "./identity/TenantSwitcher";
import { ThemeProvider, useTheme } from "./theme/ThemeProvider";
import { useI18n } from "./i18n";
import { Button, CoachMarks, CommandPalette, ErrorBoundary, Kbd, ShortcutHelp, Spinner, ToastProvider } from "./ui";
import { recordRouteVisit } from "./ui/onboarding";
import { withViewTransition } from "./ui/viewTransition";
import { MoonIcon, SearchIcon, SunIcon } from "./ui/icons";
import { ProductIcon, type ProductIconName } from "./ui/ProductIcon";
import { AUDIT_ROLES, BILLING_ROLES, IDENTITY_ROLES, roleSetAllows } from "./ui/accessRoles";

const Jobs = lazy(() => import("./pages/Jobs"));
const NewVerification = lazy(() => import("./pages/NewVerification"));
const JobDetail = lazy(() => import("./pages/JobDetail"));
const Matrix = lazy(() => import("./pages/Matrix"));
const FindingDetail = lazy(() => import("./pages/FindingDetail"));
const Contracts = lazy(() => import("./pages/Contracts"));
const Eval = lazy(() => import("./pages/Eval"));
const Health = lazy(() => import("./pages/Health"));
const Billing = lazy(() => import("./pages/Billing"));
const Usage = lazy(() => import("./pages/Usage"));
const Audit = lazy(() => import("./pages/Audit"));
const AgentApp = lazy(() => import("./agent/AgentApp"));
const IdentityApp = lazy(() => import("./identity/IdentityApp"));
const UiKit = lazy(() => import("./ui-kit/UiKit"));
const ModelSettings = lazy(() => import("./pages/ModelSettings"));
const Guide = lazy(() => import("./pages/Guide"));
const Epic = lazy(() => import("./pages/Epic"));
const Tour = lazy(() => import("./pages/Tour"));
const Lexicon = lazy(() => import("./pages/Lexicon"));
const Museum = lazy(() => import("./pages/Museum"));
const Gestures = lazy(() => import("./pages/Gestures"));
const Drill = lazy(() => import("./pages/Drill"));
const Explorer = lazy(() => import("./pages/Explorer"));
const Ide = lazy(() => import("./pages/Ide"));
const Graph = lazy(() => import("./pages/Graph"));
const Census = lazy(() => import("./pages/Census"));
const Atlas = lazy(() => import("./pages/Atlas"));
const WorldBook = lazy(() => import("./pages/WorldBook"));
const NightWatch = lazy(() => import("./pages/NightWatch"));
const Gazette = lazy(() => import("./pages/Gazette"));
const Calendar = lazy(() => import("./pages/Calendar"));
const Manual = lazy(() => import("./pages/Manual"));
const Chronicle = lazy(() => import("./pages/Chronicle"));
const Insight = lazy(() => import("./pages/Insight"));
const Dossier = lazy(() => import("./pages/Dossier"));
const Mint = lazy(() => import("./pages/Mint"));

type NavItem = {
  path: string;
  /** i18n key — the label itself lives in the locale table, never inline. */
  labelKey: string;
  icon: ProductIconName;
  /** i18n key of the sidebar group heading. */
  groupKey: string;
  /** Roles allowed to open this surface; omitted means ungated. From ui/accessRoles.ts. */
  roles?: readonly string[];
};
const NAV: NavItem[] = [
  { path: "dashboard", labelKey: "nav.dashboard", icon: "overview", groupKey: "group.workspace" },
  { path: "jobs", labelKey: "nav.jobs", icon: "verify", groupKey: "group.workspace" },
  { path: "agent", labelKey: "nav.agent", icon: "agent", groupKey: "group.workspace" },
  { path: "epic", labelKey: "nav.epic", icon: "guide", groupKey: "group.workspace" },
  { path: "tour", labelKey: "nav.tour", icon: "scroll", groupKey: "group.workspace" },
  { path: "atlas", labelKey: "nav.atlas", icon: "map", groupKey: "group.evidence" },
  { path: "worldbook", labelKey: "nav.worldbook", icon: "book", groupKey: "group.evidence" },
  { path: "nightwatch", labelKey: "nav.nightwatch", icon: "lantern", groupKey: "group.evidence" },
  { path: "gazette", labelKey: "nav.gazette", icon: "gazette", groupKey: "group.evidence" },
  { path: "calendar", labelKey: "nav.calendar", icon: "calendar", groupKey: "group.evidence" },
  { path: "lexicon", labelKey: "nav.lexicon", icon: "guide", groupKey: "group.evidence" },
  { path: "museum", labelKey: "nav.museum", icon: "scroll", groupKey: "group.evidence" },
  { path: "gestures", labelKey: "nav.gestures", icon: "guide", groupKey: "group.evidence" },
  { path: "matrix", labelKey: "nav.matrix", icon: "matrix", groupKey: "group.evidence" },
  { path: "explorer", labelKey: "nav.explorer", icon: "contracts", groupKey: "group.evidence" },
  { path: "contracts", labelKey: "nav.contracts", icon: "contracts", groupKey: "group.evidence" },
  { path: "eval", labelKey: "nav.eval", icon: "chart", groupKey: "group.evidence" },
  { path: "drill", labelKey: "nav.drill", icon: "verify", groupKey: "group.evidence" },
  { path: "ide", labelKey: "nav.ide", icon: "hammer", groupKey: "group.evidence" },
  { path: "graph", labelKey: "nav.graph", icon: "matrix", groupKey: "group.evidence" },
  { path: "chronicle", labelKey: "nav.chronicle", icon: "scroll", groupKey: "group.evidence" },
  { path: "dossier", labelKey: "nav.dossier", icon: "scroll", groupKey: "group.evidence" },
  { path: "mint", labelKey: "nav.mint", icon: "seal", groupKey: "group.evidence" },
  { path: "census", labelKey: "nav.census", icon: "verify", groupKey: "group.evidence" },
  { path: "manual", labelKey: "nav.manual", icon: "guide", groupKey: "group.evidence" },
  { path: "identity", labelKey: "nav.identity", icon: "team", groupKey: "group.admin", roles: IDENTITY_ROLES },
  { path: "insight", labelKey: "nav.insight", icon: "chart", groupKey: "group.admin", roles: IDENTITY_ROLES },
  { path: "billing", labelKey: "nav.billing", icon: "billing", groupKey: "group.admin", roles: BILLING_ROLES },
  { path: "usage", labelKey: "nav.usage", icon: "chart", groupKey: "group.admin" },
  { path: "audit", labelKey: "nav.audit", icon: "health", groupKey: "group.admin", roles: AUDIT_ROLES },
  { path: "settings", labelKey: "nav.settings", icon: "agent", groupKey: "group.admin" },
  { path: "health", labelKey: "nav.health", icon: "health", groupKey: "group.admin" },
];

function NotFoundPage(): JSX.Element {
  const { t } = useI18n();
  return (
    <div className="product-empty">
      <ProductIcon name="guide" size={36} />
      <h1>{t("app.notFoundTitle")}</h1>
      <p>{t("app.notFoundBody")}</p>
      <a className="btn btn-primary" href="#/dashboard">{t("app.notFoundCta")}</a>
    </div>
  );
}

function renderRoute(route: string): JSX.Element {
  // Query params (e.g. #/jobs/new?repo=...) belong to the page, not routing.
  const seg = route.replace(/^#/, "").split("?")[0].split("/").filter(Boolean);
  if (!seg.length || seg[0] === "dashboard") return <Dashboard />;
  if (seg[0] === "settings") return <ModelSettings />;
  if (seg[0] === "guide") return <Guide />;
  if (seg[0] === "epic") return <Epic />;
  if (seg[0] === "tour") return <Tour />;
  if (seg[0] === "lexicon") return <Lexicon />;
  if (seg[0] === "museum") return <Museum />;
  if (seg[0] === "gestures") return <Gestures />;
  if (seg[0] === "explorer") return <Explorer />;
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
  if (seg[0] === "drill") return <Drill />;
  if (seg[0] === "ide") return <Ide />;
  if (seg[0] === "graph") return <Graph />;
  if (seg[0] === "chronicle") return <Chronicle />;
  if (seg[0] === "dossier") return <Dossier />;
  if (seg[0] === "mint") return <Mint />;
  if (seg[0] === "atlas") return <Atlas />;
  if (seg[0] === "worldbook") return <WorldBook />;
  if (seg[0] === "nightwatch") return <NightWatch />;
  if (seg[0] === "gazette") return <Gazette />;
  if (seg[0] === "calendar") return <Calendar />;
  if (seg[0] === "census") return <Census />;
  if (seg[0] === "manual") return <Manual />;
  if (seg[0] === "health") return <Health />;
  if (seg[0] === "billing") return <Billing />;
  if (seg[0] === "usage") return <Usage />;
  if (seg[0] === "audit") return <Audit />;
  if (seg[0] === "insight") return <Insight />;
  return <NotFoundPage />;
}

function Workspace() {
  const [route, setRoute] = useState(() => window.location.hash || "#/dashboard");
  const [hasKey, setHasKey] = useState(() => getApiKey() !== "" || getBearerToken() !== "");
  const [principal, setPrincipal] = useState<PrincipalInfo | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  // Natural scrolling by default (scroll down = look down) — what the owner asked for,
  // repeatedly. The topbar invert button stays as an opt-in escape hatch for users
  // whose own mouse/system stack reverses scroll globally; localStorage "1" opts in.
  const [invertScroll, setInvertScroll] = useState((): boolean => {
    try {
      return window.localStorage.getItem("specproof_invert_scroll") === "1";
    } catch {
      return false;
    }
  });
  const contentRef = useRef<HTMLElement>(null);
  const { resolved, toggle } = useTheme();
  // Opt-in wheel inversion for the main content column. Default OFF ("scroll
  // down = look down" — the comfortable direction); users whose system or
  // mouse stack reverses scroll globally can flip this once and get the
  // app-standard direction back inside SpecProof.
  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    const onWheel = (event: WheelEvent) => {
      const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? (el.clientHeight || 1) : 1;
      event.preventDefault();
      el.scrollTop -= event.deltaY * unit;
    };
    if (invertScroll) {
      el.addEventListener("wheel", onWheel, { passive: false });
      return () => el.removeEventListener("wheel", onWheel);
    }
    return;
  }, [invertScroll]);
  const { t, toggleLocale, locale } = useI18n();
  useEffect(() => {
    const onChange = () => {
      const hash = window.location.hash || "#/dashboard";
      recordRouteVisit(hash);
      withViewTransition(() => setRoute(hash));
      setMenuOpen(false);
    };
    window.addEventListener("hashchange", onChange);
    recordRouteVisit(window.location.hash || "#/dashboard");
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
  const label = NAV.find(item => item.path === active)
    ? t(NAV.find((item) => item.path === active)!.labelKey)
    : active === "guide"
      ? t("nav.guide")
      : t("nav.jobDetail");
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
  // A gated item is hidden unless the principal holds one of its roles, so the
  // sidebar cannot advertise a page the server would refuse. The sets come from
  // ui/accessRoles.ts — tests/unit/test_access_role_parity.py re-derives each
  // one from ROLE_MATRIX applied to the calls that page actually makes.
  const nav = NAV.filter(item =>
    item.roles == null || principal == null || roleSetAllows(principal.roles, item.roles));

  return <div className="shell product-shell">
    <a className="skip-link" href="#main-content" onClick={e => { e.preventDefault(); contentRef.current?.focus(); }}>{t("skip.link.main")}</a>
    {menuOpen && <button className="nav-backdrop" aria-label={t("nav.backdrop")} onClick={() => setMenuOpen(false)} />}
    <aside className={"sidebar" + (menuOpen ? " sidebar-open" : "")} id="workspace-navigation">
      <a className="brand" data-coach="boot.brand" href="#/dashboard" aria-label={t("brand.ariaLabel")}><span className="brand-mark"><ProductIcon name="shield" size={23} /></span><span><span className="brand-name">SpecProof<span className="brand-dot">.</span></span><span className="brand-sub">{t("brand.sub")}</span></span></a>
      <div className="workspace-selector"><span className="workspace-avatar">W</span><span><strong>{t("workspace.my")}</strong><small>{t("workspace.product")}</small></span><ProductIcon name="verify" size={16} /></div>
      <nav aria-label={t("nav.primaryAria")}>
        {["group.workspace", "group.evidence", "group.admin"].map((groupKey) => <div className="nav-group" key={groupKey}><div className="nav-group-label">{t(groupKey)}</div>{nav.filter(item => item.groupKey === groupKey).map(item => <a key={item.path} data-coach={"nav:" + item.path} href={"#/" + item.path} aria-current={active === item.path ? "page" : undefined} className={"nav-item" + (active === item.path ? " nav-active" : "")}><ProductIcon name={item.icon} size={18} /><span className="nav-label">{t(item.labelKey)}</span>{item.path === "agent" && <span className="nav-tag">CRAFT</span>}</a>)}</div>)}
      </nav>
      <div className="sidebar-guide" data-coach="boot.guide"><ProductIcon name="guide" /><strong>{t("sidebar.guideTitle")}</strong><p>{t("sidebar.guideBody")}</p><a href="#/guide">{t("sidebar.guideCta")} <span aria-hidden="true">↗</span></a></div>
      <div className="sidebar-foot"><TenantSwitcher /><div className="account-row"><span className="account-avatar">{hasKey ? "SP" : "?"}</span><span><strong>{hasKey ? t("session.current") : t("session.guest")}</strong><small>{hasKey ? t("session.currentHint") : t("session.guestHint")}</small></span><Button variant="ghost" size="sm" onClick={async () => { const idpUrl = await logout(); setPrincipal(null); setHasKey(false); if (idpUrl) { window.location.href = idpUrl; } else { window.location.hash = "#/login"; } }}>{hasKey ? t("session.logout") : t("session.connect")}</Button></div></div>
    </aside>
    <div className="workspace-main"><header className="workspace-topbar"><div className="topbar-left"><button className="icon-button mobile-menu" data-coach="topbar.menu" aria-label={t("topbar.menu")} aria-expanded={menuOpen} aria-controls="workspace-navigation" onClick={() => setMenuOpen(!menuOpen)}><ProductIcon name={menuOpen ? "close" : "menu"} /></button><span className="topbar-workspace">{t("topbar.workspace")}</span><span className="breadcrumb-separator">/</span><strong>{label}</strong></div><div className="topbar-actions"><button className="command-trigger" data-coach="topbar.search" onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }))}><SearchIcon /><span>{t("topbar.searchPages")}</span><Kbd>Ctrl K</Kbd></button><a className="topbar-help" data-coach="topbar.help" href="#/guide">{t("topbar.helpLink")}</a><button className="icon-button" data-coach="topbar.theme" aria-label={resolved === "dark" ? t("topbar.theme.toLight") : t("topbar.theme.toDark")} onClick={toggle}>{resolved === "dark" ? <SunIcon size={18} /> : <MoonIcon size={18} />}</button><button type="button" className="icon-button" data-coach="topbar.locale" onClick={toggleLocale} aria-label={t("topbar.switchLocale")} title={t("topbar.switchLocale")}>{locale === "zh" ? "EN" : "中"}</button><button type="button" className="icon-button" data-coach="topbar.invert" aria-label={t(invertScroll ? "topbar.invertScrollOn" : "topbar.invertScroll")} aria-pressed={invertScroll} title={t(invertScroll ? "topbar.invertScrollOn" : "topbar.invertScroll")} onClick={() => setInvertScroll((prev) => { const next = !prev; try { window.localStorage.setItem("specproof_invert_scroll", next ? "1" : "0"); } catch { /* unavailable */ } return next; })}><ProductIcon name="invert" size={18} /></button><button type="button" className="icon-button" data-coach="topbar.coach" onClick={() => window.dispatchEvent(new Event("specproof-coach-marks:toggle"))} aria-label={t("coach.toggleAria")} title={t("coach.toggleAria")}><Kbd>H</Kbd></button></div></header>
      <main className="content" id="main-content" tabIndex={-1} ref={contentRef}><ErrorBoundary key={active}><Suspense fallback={<Spinner />}>{renderRoute(route)}</Suspense></ErrorBoundary><footer className="workspace-footer"><span>{t("footer.tagline")}</span><a href="#/guide">{t("footer.startLink")} <span aria-hidden="true">↗</span></a></footer></main>
    </div>
  </div>;
}

export default function App() {
  return <ThemeProvider><ToastProvider><ErrorBoundary><Workspace /></ErrorBoundary><CommandPalette /><ShortcutHelp /><CoachMarks /></ToastProvider></ThemeProvider>;
}
