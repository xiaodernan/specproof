import { useEffect, useState } from "react";
import {
  ApiError,
  apiBase,
  apiGet,
  getApiKey,
  getBearerToken,
} from "../api";
import type { Column } from "../ui";
import { BILLING_ROLES } from "../ui/accessRoles";
import { useRoleAccess } from "../ui/useRoleAccess";
import {
  Empty,
  ErrorBox,
  Panel,
  Spinner,
  StatCard,
  Table,
  shortId,
} from "../ui";
import { useI18n } from "../i18n";
import { BILLING_BY_LOCALE, type BillingCopy } from "./billing.copy";

// ── Wire shapes (mirror api/routes/billing.py) ─────────────────────

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

export interface Invoice {
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

// The role set is the shared one in ui/accessRoles.ts (billing:read), which the
// sidebar uses for the same page; App.tsx used to carry its own copy of it.
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

// Gloss enums into the readable-table language, keeping the raw token visible
// (honesty): "生效中 · active". An unexpected value passes through verbatim.
function glossEnum(labels: Record<string, string>, raw: string): string {
  if (!raw) return "—";
  const gloss = labels[raw];
  return gloss ? gloss + " · " + raw : raw;
}

function planColumns(c: BillingCopy): Column<BillingPlan>[] {
  return [
    {
      key: "name",
      header: c.colPlan,
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
      header: c.colMonthly,
      align: "right",
      sortable: true,
      render: (p) => (p.price_monthly === 0 ? c.freePlan : "$" + p.price_monthly.toFixed(2) + " " + c.perMonth),
    },
    {
      key: "quotas",
      header: c.colQuotas,
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
      header: c.colOverage,
      render: (p) => {
        const entries = Object.entries(p.overage);
        return entries.length === 0 ? (
          <span className="muted">{c.hardStop}</span>
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
}

function usageColumns(c: BillingCopy): Column<UsageRow>[] {
  return [
    {
      key: "happened_at",
      header: c.colTime,
      sortable: true,
      render: (r) => <span className="muted">{fmtEpoch(r.happened_at)}</span>,
    },
    {
      key: "metric",
      header: c.colMetric,
      render: (r) => <span className="mono">{r.metric}</span>,
    },
    {
      key: "units",
      header: c.colUnits,
      align: "right",
      sortable: true,
      render: (r) => r.units.toLocaleString(),
    },
    {
      key: "unit_label",
      header: c.colUnit,
      render: (r) => r.unit_label || <span className="muted">{c.missingUnit}</span>,
    },
    {
      key: "event_id",
      header: c.colEvent,
      render: (r) => (
        <span className="mono muted" title={r.event_id}>
          {shortId(r.event_id)}
        </span>
      ),
    },
    {
      key: "tenant_id",
      header: c.colTenant,
      render: (r) => <span className="mono muted">{r.tenant_id}</span>,
    },
  ];
}

function invoiceColumns(c: BillingCopy): Column<Invoice>[] {
  return [
    {
      key: "period",
      header: c.colPeriod,
      render: (inv) => <span className="mono">{inv.period}</span>,
    },
    {
      key: "id",
      header: c.colInvoice,
      render: (inv) => <span className="mono muted">{inv.id}</span>,
    },
    {
      key: "line_items",
      header: c.colLineItems,
      align: "right",
      sortable: true,
      sortValue: (inv) => (inv.line_items ?? []).length,
      render: (inv) => String((inv.line_items ?? []).length),
    },
    {
      key: "total",
      header: c.colTotal,
      align: "right",
      sortable: true,
      render: (inv) => inv.currency + " " + inv.total.toFixed(2),
    },
    {
      key: "status",
      header: c.colStatus,
      render: (inv) => <span className={"pill " + invoicePill(inv.status)} title={inv.status}>{glossEnum(c.invoiceLabels, inv.status)}</span>,
    },
  ];
}

// UI visibility gate for the billing console (RBAC: billing:read —
// admin/operator/auditor). Fail-open on UNKNOWN identity so legacy deployments
// keep working; the backend enforces fail-closed and answers 403.
function useBillingAccess(): { checked: boolean; canView: boolean } {
  const access = useRoleAccess(BILLING_ROLES);
  return { checked: access.checked, canView: access.allowed };
}

// Shared forbidden view: identity-gate denials and server-side 403
// TENANT_FORBIDDEN land on the same honest state with a contact-admin hint.
function BillingForbidden(props: { reason: string; c: BillingCopy }): JSX.Element {
  const { c } = props;
  return (
    <div>
      <div className="errorbox" data-testid="billing-forbidden" role="alert">
        {props.reason}
      </div>
      <Panel title={c.forbiddenPanelScope}>
        <div className="kv">
          <span className="kv-label">{c.forbiddenPanelScope}</span>
          <span className="kv-value">
            {c.forbiddenScopeValue(BILLING_ROLES.join(" / "))}
          </span>
        </div>
        <div className="kv">
          <span className="kv-label">{c.forbiddenPanelSource}</span>
          <span className="kv-value">
            {c.forbiddenSourceValue}
          </span>
        </div>
        <div className="permission-hint" data-testid="billing-contact-admin-hint">
          {c.forbiddenHint}
        </div>
      </Panel>
    </div>
  );
}

export default function Billing() {
  const { locale } = useI18n();
  const c = BILLING_BY_LOCALE[locale];
  const planCols = planColumns(c);
  const usageCols = usageColumns(c);
  const invoiceCols = invoiceColumns(c);
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
      <h1>{c.title}</h1>
      <div className="page-sub">{c.sub}</div>
    </div>
  );

  if (!canView) {
    return (
      <div>
        {pageHead}
        <BillingForbidden reason={c.forbiddenReasonIdentity} c={c} />
      </div>
    );
  }

  if (forbidden) {
    return (
      <div>
        {pageHead}
        <BillingForbidden reason={c.forbiddenReasonServer} c={c} />
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
              label={c.subActivePlan}
              value={planName}
              tone={
                data.subscription
                  ? data.subscription.status === "active"
                    ? "ok"
                    : "warn"
                  : "mute"
              }
              sub={data.subscription ? data.subscription.plan_id : c.noSubscriptionChip}
            />
            <StatCard
              label={c.usageLabel(month)}
              value={String(data.usage.length)}
              tone="info"
            />
            <StatCard
              label={c.invoicesLabel(month)}
              value={String(data.invoices.length)}
              tone="info"
            />
          </div>

          <div data-testid="billing-plans">
            <Panel title={c.plansTitle}>
              <Table<BillingPlan>
                columns={planCols}
                rows={data.plans}
                rowKey={(p) => p.id}
                emptyTitle={c.noPlansTitle}
                emptyDescription={c.noPlansDescription}
              />
            </Panel>
          </div>

          <div data-testid="billing-subscription">
            <Panel title={c.subTitle}>
              {data.subscription ? (
                <div>
                  <div className="kv">
                    <span className="kv-label">{c.colPlan}</span>
                    <span className="kv-value">{planName}</span>
                  </div>
                  <div className="kv">
                    <span className="kv-label">{c.colStatus}</span>
                    <span className="kv-value">
                      <span className={"pill " + subscriptionPill(data.subscription.status)} title={data.subscription.status}>
                        {glossEnum(c.subscriptionLabels, data.subscription.status)}
                      </span>
                    </span>
                  </div>
                  <div className="kv">
                    <span className="kv-label">{c.colPeriod}</span>
                    <span className="kv-value">
                      {fmtEpoch(data.subscription.period_start)} →{" "}
                      {fmtEpoch(data.subscription.period_end)}
                    </span>
                  </div>
                  <div className="kv">
                    <span className="kv-label">{c.colTenant}</span>
                    <span className="kv-value mono">{data.subscription.tenant_id}</span>
                  </div>
                </div>
              ) : (
                <Empty text={c.noSubscription} />
              )}
            </Panel>
          </div>

          <div data-testid="billing-usage">
            <Panel
              title={c.usageTitle(month)}
              right={
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <input
                    type="month"
                    value={month}
                    data-testid="billing-month"
                    aria-label={c.monthAria}
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
                    {c.downloadCsv}
                  </a>
                </div>
              }
            >
              <Table<UsageRow>
                columns={usageCols}
                rows={data.usage}
                rowKey={(r) => String(r.id)}
                emptyTitle={c.noUsageTitle}
                emptyDescription={c.noUsageDescription}
              />
            </Panel>
          </div>

          <div data-testid="billing-invoices">
            <Panel title={c.invoicesTitle(month)}>
              <Table<Invoice>
                columns={invoiceCols}
                rows={data.invoices}
                rowKey={(inv) => inv.id}
                emptyTitle={c.noInvoicesTitle}
                emptyDescription={c.noInvoicesDescription}
              />
            </Panel>
          </div>
        </>
      ) : null}
    </div>
  );
}
