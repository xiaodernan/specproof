import { useEffect, useState } from "react";
import {
  clearApiKey,
  clearBearerToken,
  consumeOidcCallback,
  getApiKey,
  getAuthMe,
  getBearerToken,
} from "./api";
import type { PrincipalInfo } from "./api";
import { ErrorBoundary } from "./ui";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Jobs from "./pages/Jobs";
import JobDetail from "./pages/JobDetail";
import Matrix from "./pages/Matrix";
import FindingDetail from "./pages/FindingDetail";
import Contracts from "./pages/Contracts";
import Eval from "./pages/Eval";
import Health from "./pages/Health";
import AgentApp from "./agent/AgentApp";
import IdentityApp from "./identity/IdentityApp";
import TenantSwitcher from "./identity/TenantSwitcher";
import { ThemeProvider } from "./theme/ThemeProvider";
import { Button, CommandPalette, Kbd, ToastProvider } from "./ui";
import UiKit from "./ui-kit/UiKit";

// Minimal hash router: keeps deep links working behind the FastAPI SPA
// fallback without any routing dependency.

function useHashRoute(): string {
  const [route, setRoute] = useState<string>(() => window.location.hash || "#/dashboard");
  useEffect(() => {
    const onChange = () => setRoute(window.location.hash || "#/dashboard");
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

function navigate(path: string): void {
  window.location.hash = path;
}

interface NavItem {
  path: string;
  label: string;
  en: string;
}

const NAV: NavItem[] = [
  { path: "#/dashboard", label: "总览", en: "Dashboard" },
  { path: "#/jobs", label: "任务", en: "Jobs" },
  { path: "#/agent", label: "Agent", en: "SpecCraft" },
  { path: "#/matrix", label: "需求矩阵", en: "Matrix" },
  { path: "#/contracts", label: "契约中心", en: "Contracts" },
  { path: "#/identity", label: "身份", en: "Identity" },
  { path: "#/eval", label: "评测", en: "Eval" },
  { path: "#/health", label: "健康", en: "Health" },
];

function renderRoute(route: string): JSX.Element {
  const path = route.startsWith("#") ? route.slice(1) : route;
  const seg = path.split("/").filter(Boolean);
  if (seg.length === 0 || seg[0] === "dashboard") return <Dashboard />;
  if (seg[0] === "login") return <Login />;
  if (seg[0] === "agent") return <AgentApp seg={seg} />;
  if (seg[0] === "identity") return <IdentityApp seg={seg} />;
  if (seg[0] === "jobs") {
    if (seg.length >= 2) return <JobDetail jobId={decodeURIComponent(seg[1])} />;
    return <Jobs />;
  }
  if (seg[0] === "matrix") return <Matrix />;
  if (seg[0] === "findings" && seg.length >= 3) {
    return (
      <FindingDetail
        jobId={decodeURIComponent(seg[1])}
        findingId={decodeURIComponent(seg[2])}
      />
    );
  }
  if (seg[0] === "contracts") return <Contracts />;
  if (seg[0] === "eval") return <Eval />;
  if (seg[0] === "health") return <Health />;
  if (seg[0] === "ui-kit") return <UiKit />;
  return <Dashboard />;
}

// The identity console is RBAC-managed (admin/operator). The nav entry is
// hidden only when the bearer principal is KNOWN and lacks those roles;
// unknown identity (legacy X-API-Key mode, /auth/me unreachable) keeps the
// legacy nav. Enforcement always stays server-side (fail-closed).
function canManageIdentity(principal: PrincipalInfo | null): boolean {
  if (principal == null || !Array.isArray(principal.roles)) return true;
  return principal.roles.includes("admin") || principal.roles.includes("operator");
}

export default function App() {
  const route = useHashRoute();
  const [hasKey, setHasKey] = useState<boolean>(
    () => getApiKey() !== "" || getBearerToken() !== ""
  );
  const [principal, setPrincipal] = useState<PrincipalInfo | null>(null);

  // OIDC login returns via /#oidc_token=...: stash the id_token, drop the
  // fragment, and enter the shell.
  useEffect(() => {
    if (consumeOidcCallback()) setHasKey(true);
  }, []);

  // Resolve the bearer principal once a credential exists (tenant mode).
  useEffect(() => {
    if (!hasKey || getBearerToken() === "") return;
    let alive = true;
    getAuthMe()
      .then((me) => {
        if (alive && me && me.principal) setPrincipal(me.principal);
      })
      .catch(() => {
        // unknown identity keeps the legacy behavior
      });
    return () => {
      alive = false;
    };
  }, [hasKey]);

  const path = route.startsWith("#") ? route.slice(1) : route;
  const seg = path.split("/").filter(Boolean);
  const active = seg[0] || "dashboard";

  let body: JSX.Element;
  if (seg[0] === "ui-kit") {
    // Design-system style guide: standalone and reviewable without an API key.
    body = <UiKit />;
  } else if (!hasKey) {
    body = <Login onConnected={() => setHasKey(true)} />;
  } else {
    body = (
      <div className="shell">
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-mark" aria-hidden="true">
              SP
            </div>
            <div>
              <div className="brand-name">SpecProof</div>
              <div className="brand-sub">CONTROL ROOM</div>
            </div>
          </div>
          <nav aria-label="主导航 Primary navigation">
            {NAV.filter(
              (item) => item.path !== "#/identity" || canManageIdentity(principal)
            ).map((item) => (
              <a
                key={item.path}
                href={item.path}
                aria-current={item.path === "#/" + active ? "page" : undefined}
                className={
                  "nav-item" +
                  ((item.path === "#/" + active ? true : false) ? " nav-active" : "")
                }
              >
                <span className="nav-label">{item.label}</span>
                <span className="nav-en">{item.en}</span>
              </a>
            ))}
          </nav>
          <div className="sidebar-foot">
            <div className="foot-line">FAIL-CLOSED AUTH</div>
            <TenantSwitcher />
            <div style={{ marginTop: 10 }}>
              <Button
                variant="ghost"
                size="sm"
                fullWidth
                onClick={() => {
                  clearApiKey();
                  clearBearerToken();
                  setHasKey(false);
                  navigate("#/login");
                }}
              >
                断开 Disconnect
              </Button>
            </div>
            <div className="shell-hint">
              <Kbd>Ctrl</Kbd>
              <Kbd>K</Kbd>
              <span>命令面板</span>
            </div>
          </div>
        </aside>
        <main className="content">{renderRoute(route)}</main>
      </div>
    );
  }

  return (
    <ThemeProvider>
      <ToastProvider>
        <ErrorBoundary>{body}</ErrorBoundary>
        <CommandPalette />
      </ToastProvider>
    </ThemeProvider>
  );
}
