import { useEffect, useState } from "react";
import {
  ApiError,
  apiBase,
  apiGet,
  getApiKey,
  getAuthMe,
  getBearerToken,
} from "../api";
import type { PrincipalInfo } from "../api";
import type { Column } from "../ui";
import {
  Empty,
  ErrorBox,
  Panel,
  Spinner,
  StatCard,
  Table,
  shortId,
} from "../ui";

// ── Wire shapes (mirror api/routes/billing.py) ──

interface BillingPlan {
  id: string;
  name: string;
  price_monthly: number;
  quotas: Record<string, number>;
  overage: Record<string, number>;
}

interface Subscription {
  id: string;
  tenant_id: string;
  plan_id: string;
  status: string;
  period_start: number;
  period_end: number;
}

interface UsageRow {
  id: number;
  tenant_id: string;
  event_id: string;
  metric: string;
  units: number;
  unit_label: string;
  happened_at: number;
}

interface Invoice {
  id: string;
  tenant_id: string;
  period: string;
  line_items: Array<Record<string, unknown>>;
  total: number;
  currency: string;
  status: string;
}

interface BillingData {
  plans: BillingPlan[];
  subscription: Subscription | null;
  usage: UsageRow[];
  invoices: Invoice[];
}

// billing:read roles per the §2 RBAC matrix; viewer is refused with
// TENANT_FORBIDDEN by the middleware and by every handler, so the UI gate
// mirrors that exact role set (auditor included).
const BILLING_ROLES = ["admin", "operator", "auditor"];
const MONTH_RE = /^\d{4}-\d{2}$/;

function currentMonth(): string {
  const d = new Date();
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0");
}

// Ledger window [from, to) for a YYYY-MM period, in epoch seconds — the
// same unit the API uses (Date.UTC(y, 12, 1) rolls into next January).
function monthRange(month: string): { from: number; to: number } {
  const [y, m] = month.split("-").map((s) => Number(s));
  const from = Date.UTC(y, m - 1, 1) / 1000;
  const to = Date.UTC(y, m, 1) / 1000;
  return { from, to };
}

function fmtEpoch(sec: number): string {
  return new Date(sec * 1000).toLocaleString();
}

function subscriptionPill(status: string): string {
  return status === "active" ? "pill-ok" : "pill-mute";
}

function invoicePill(status: string): string {
  if (status === "paid") return "pill-ok";
  if (status === "issued") return "pill-run";
  return "pill-mute";
}

// UI visibility gate for the billing console (RBAC: billing:read —
// admin/operator/auditor). Mirrors identity/useIdentityAccess: fail-open
// on UNKNOWN identity so legacy (non-auth) deployments keep the existing
// behavior; the backend enforces fail-closed and answers 403
// TENANT_FORBIDDEN, which this page renders as its own state.
function useBillingAccess(): { checked: boolean; canView: boolean } {
  const [principal, setPrincipal] = useState<PrincipalInfo | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    let alive = true;
    getAuthMe()
      .then((me) => {
        if (alive && me && me.principal) setPrincipal(me.principal);
      })
      .catch(() => {
        // unknown identity: render as before (legacy mode answers 503 anyway)
      })
      .finally(() => {
        if (alive) setChecked(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const canView =
    !checked ||
    principal == null ||
    !Array.isArray(principal.roles) ||
    BILLING_ROLES.some((role) => principal.roles.includes(role));
  return { checked, canView };
}

// Shared forbidden view: identity-gate denials and server-side 403
// TENANT_FORBIDDEN land on the same honest state with a contact-admin
// hint (§14.4 permission explanation).
function BillingForbidden(props: { reason: string }): JSX.Element {
  return (
    <div>
      <div className="errorbox" data-testid="billing-forbidden" role="alert">
        {props.reason}
      </div>
      <Panel title="权限说明 Permission explanation">
        <div className="kv">
          <span className="kv-label">范围 Scope</span>
          <span className="kv-value">
            计费读取 billing:read — 套餐 / 订阅 / 用量账本 / 发票仅对 admin /
            operator / auditor 开放; viewer 角色一律被服务端以 TENANT_FORBIDDEN
            (403) 拒绝。
          </span>
        </div>
        <div className="kv">
          <span className="kv-label">来源 Source</span>
          <span className="kv-value">
            权限来自服务端 /auth/me 解析的当前身份 (sp_* 令牌或 OIDC
            id_token); 本页门控仅影响可见性, 服务端 RBAC fail-closed 才是权威。
          </span>
        </div>
        <div className="permission-hint" data-testid="billing-contact-admin-hint">
          需要访问? 请联系租户管理员 Contact admin — 请管理员在 身份 Identity
          页将你的角色调整为 admin / operator / auditor, 或为你签发相应范围的令牌。
        </div>
      </Panel>
    </div>
  );
}

const planColumns: Column<BillingPlan>[] = [
  {
    key: "name",
    header: "套餐 Plan",
    sortable: true,
    render: (p) => (
      <div>
        <div>{p.name}</div>
        <div className="muted mono">{p.id}</div>
      </div>
    ),
  },
  {
    key: "price_monthly",
    header: "月费 Monthly",
    align: "right",
    sortable: true,
    render: (p) => (p.price_monthly === 0 ? "免费 Free" : "$" + p.price_monthly.toFixed(2) + " /月"),
  },
  {
    key: "quotas",
    header: "配额 Quotas",
    render: (p) => (
      <div>
        {Object.entries(p.quotas).map(([k, v]) => (
          <div key={k} className="mono">
            {k}: {v.toLocaleString()}
          </div>
        ))}
      </div>
    ),
  },
  {
    key: "overage",
    header: "超额 Overage",
    render: (p) => {
      const entries = Object.entries(p.overage);
      return entries.length === 0 ? (
        <span className="muted">硬上限 Hard stop</span>
      ) : (
        <div>
          {entries.map(([k, v]) => (
            <div key={k} className="mono">
              {k}: {"$" + v + "/unit"}
            </div>
          ))}
        </div>
      );
    },
  },
];

const usageColumns: Column<UsageRow>[] = [
  {
    key: "happened_at",
    header: "时间 Time",
    sortable: true,
    render: (r) => <span className="muted">{fmtEpoch(r.happened_at)}</span>,
  },
  {
    key: "metric",
    header: "指标 Metric",
    render: (r) => <span className="mono">{r.metric}</span>,
  },
  {
    key: "units",
    header: "数量 Units",
    align: "right",
    sortable: true,
    render: (r) => r.units.toLocaleString(),
  },
  {
    key: "unit_label",
    header: "单位 Unit",
    render: (r) => r.unit_label || <span className="muted">—</span>,
  },
  {
    key: "event_id",
    header: "事件 Event",
    render: (r) => (
      <span className="mono muted" title={r.event_id}>
        {shortId(r.event_id)}
      </span>
    ),
  },
  {
    key: "tenant_id",
    header: "租户 Tenant",
    render: (r) => <span className="mono muted">{r.tenant_id}</span>,
  },
];

const invoiceColumns: Column<Invoice>[] = [
  {
    key: "period",
    header: "周期 Period",
    render: (inv) => <span className="mono">{inv.period}</span>,
  },
  {
    key: "id",
    header: "发票 Invoice",
    render: (inv) => <span className="mono muted">{inv.id}</span>,
  },
  {
    key: "line_items",
    header: "行项目 Line items",
    align: "right",
    sortable: true,
    sortValue: (inv) => (inv.line_items ?? []).length,
    render: (inv) => String((inv.line_items ?? []).length),
  },
  {
    key: "total",
    header: "合计 Total",
    align: "right",
    sortable: true,
    render: (inv) => inv.currency + " " + inv.total.toFixed(2),
  },
  {
    key: "status",
    header: "状态 Status",
    render: (inv) => <span className={"pill " + invoicePill(inv.status)}>{inv.status}</span>,
  },
];

export default function Billing() {
  const { checked, canView } = useBillingAccess();
  const [month, setMonth] = useState(currentMonth);
  const [data, setData] = useState<BillingData | null>(null);
  const [error, setError] = useState<Error | string | null>(null);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);

  useEffect(() => {
    if (!checked || !canView) return;
    let alive = true;
    setError(null);
    setForbidden(false);
    const { from, to } = monthRange(month);
    Promise.all([
      apiGet<{ plans: BillingPlan[]; count: number }>("/api/v1/billing/plans"),
      apiGet<{ subscription: Subscription | null }>("/api/v1/billing/subscription"),
      apiGet<{ usage: UsageRow[]; count: number; from: number; to: number }>(
        "/api/v1/billing/usage?from=" + from + "&to=" + to
      ),
      apiGet<{ invoices: Invoice[]; count: number }>(
        "/api/v1/billing/invoices?period=" + encodeURIComponent(month)
      ),
    ])
      .then(([plans, sub, usage, invoices]) => {
        if (!alive) return;
        setData({
          plans: plans.plans,
          subscription: sub.subscription,
          usage: usage.usage,
          invoices: invoices.invoices,
        });
      })
      .catch((e) => {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 403) setForbidden(true);
        else setError(e instanceof Error ? e : new Error(String(e)));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [checked, canView, month]);

  const pageHead = (
    <div className="page-head">
      <h1>计费与用量 Billing &amp; Usage</h1>
      <div className="page-sub">
        BILLING — PLANS / SUBSCRIPTION / USAGE LEDGER / INVOICES (RBAC:
        billing:read)
      </div>
    </div>
  );

  if (!canView) {
    return (
      <div>
        {pageHead}
        <BillingForbidden reason="TENANT_FORBIDDEN — 当前角色无计费读取权限 billing:read (仅 admin / operator / auditor)" />
      </div>
    );
  }

  if (forbidden) {
    return (
      <div>
        {pageHead}
        <BillingForbidden reason="TENANT_FORBIDDEN — 服务端拒绝计费读取 billing:read (RBAC fail-closed)" />
      </div>
    );
  }

  const { from, to } = monthRange(month);
  const csvUrl =
    apiBase() +
    "/api/v1/billing/usage?from=" +
    from +
    "&to=" +
    to +
    "&format=csv";

  // CSV answers as an attachment; a plain <a href> cannot carry the
  // Authorization header, so the link downloads through fetch + blob with
  // the same credential headers as every other API call.
  async function downloadUsageCsv(): Promise<void> {
    try {
      const h: Record<string, string> = { Accept: "text/csv" };
      const bearer = getBearerToken();
      if (bearer) {
        h["Authorization"] = "Bearer " + bearer;
      } else {
        const key = getApiKey();
        if (key) h["X-API-Key"] = key;
      }
      const resp = await fetch(csvUrl, { headers: h });
      if (!resp.ok) {
        let detail = resp.statusText;
        try {
          const body = await resp.json();
          if (body && typeof body.detail === "string") detail = body.detail;
        } catch {
          // non-JSON error body; keep statusText
        }
        throw new ApiError(resp.status, detail);
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "usage-" + month + ".csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
    }
  }

  const subscription = data ? data.subscription : null;
  const planName =
    data && subscription
      ? (data.plans.find((p) => p.id === subscription.plan_id)?.name ??
        subscription.plan_id)
      : "—";

  return (
    <div>
      {pageHead}
      <ErrorBox error={error} />
      {loading || !checked ? (
        <Spinner />
      ) : data ? (
        <>
          <div className="stat-grid" style={{ marginBottom: 16 }}>
            <StatCard
              label="当前套餐 Current plan"
              value={planName}
              tone={
                data.subscription
                  ? data.subscription.status === "active"
                    ? "ok"
                    : "warn"
                  : "mute"
              }
              sub={data.subscription ? data.subscription.plan_id : "无订阅 No subscription"}
            />
            <StatCard
              label={"本期用量记录 Usage (" + month + ")"}
              value={String(data.usage.length)}
              tone="info"
            />
            <StatCard
              label={"本期发票 Invoices (" + month + ")"}
              value={String(data.invoices.length)}
              tone="info"
            />
          </div>

          <div data-testid="billing-plans">
            <Panel title="套餐 Plans">
              <Table<BillingPlan>
                columns={planColumns}
                rows={data.plans}
                rowKey={(p) => p.id}
                emptyTitle="暂无套餐"
                emptyDescription="服务端启动时按配置播种 free / pro 套餐"
              />
            </Panel>
          </div>

          <div data-testid="billing-subscription">
            <Panel title="当前订阅 Subscription">
              {data.subscription ? (
                <div>
                  <div className="kv">
                    <span className="kv-label">套餐 Plan</span>
                    <span className="kv-value">{planName}</span>
                  </div>
                  <div className="kv">
                    <span className="kv-label">状态 Status</span>
                    <span className="kv-value">
                      <span className={"pill " + subscriptionPill(data.subscription.status)}>
                        {data.subscription.status}
                      </span>
                    </span>
                  </div>
                  <div className="kv">
                    <span className="kv-label">周期 Period</span>
                    <span className="kv-value">
                      {fmtEpoch(data.subscription.period_start)} →{" "}
                      {fmtEpoch(data.subscription.period_end)}
                    </span>
                  </div>
                  <div className="kv">
                    <span className="kv-label">租户 Tenant</span>
                    <span className="kv-value mono">{data.subscription.tenant_id}</span>
                  </div>
                </div>
              ) : (
                <Empty text="当前租户暂无订阅 No active subscription for this tenant" />
              )}
            </Panel>
          </div>

          <div data-testid="billing-usage">
            <Panel
              title={"用量 Usage — " + month + " (JSON)"}
              right={
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <input
                    type="month"
                    value={month}
                    data-testid="billing-month"
                    aria-label="账单周期 Billing period"
                    onChange={(e) => {
                      if (MONTH_RE.test(e.target.value)) setMonth(e.target.value);
                    }}
                  />
                  <a
                    className="ui-btn ui-btn-secondary ui-btn-sm"
                    href={csvUrl}
                    data-testid="usage-csv-link"
                    onClick={(e) => {
                      e.preventDefault();
                      void downloadUsageCsv();
                    }}
                  >
                    下载 CSV Download
                  </a>
                </div>
              }
            >
              <Table<UsageRow>
                columns={usageColumns}
                rows={data.usage}
                rowKey={(r) => String(r.id)}
                emptyTitle="本期暂无用量记录"
                emptyDescription="meter 事件写入账本后按 [from, to) 窗口显示在这里"
              />
            </Panel>
          </div>

          <div data-testid="billing-invoices">
            <Panel title={"发票 Invoices — " + month}>
              <Table<Invoice>
                columns={invoiceColumns}
                rows={data.invoices}
                rowKey={(inv) => inv.id}
                emptyTitle="本期暂无发票"
                emptyDescription="GET /billing/invoices?period= 会按需从账本生成草稿发票"
              />
            </Panel>
          </div>
        </>
      ) : null}
    </div>
  );
}
