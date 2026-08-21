import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import Billing from "./Billing";
import { ApiError, apiGet, getAuthMe } from "../api";

// The billing page resolves the principal via /auth/me (role gate:
// admin/operator/auditor for billing:read) and then hits four
// /api/v1/billing endpoints. Tests mock the api module and never touch the
// network.

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return { ...actual, apiGet: vi.fn(), getAuthMe: vi.fn() };
});

const apiGetMock = vi.mocked(apiGet);
const getAuthMeMock = vi.mocked(getAuthMe);

const PLANS = {
  plans: [
    {
      id: "free",
      name: "Free",
      price_monthly: 0,
      quotas: { jobs_verify: 20, llm_tokens: 200000 },
      overage: {},
    },
    {
      id: "pro",
      name: "Pro",
      price_monthly: 99,
      quotas: { jobs_verify: 500, llm_tokens: 5000000 },
      overage: { job_verify: 0.1 },
    },
  ],
  count: 2,
};

const SUBSCRIPTION = {
  subscription: {
    id: "sub-1",
    tenant_id: "t-1",
    plan_id: "pro",
    status: "active",
    period_start: 1704067200,
    period_end: 1706745600,
  },
};

const USAGE = {
  usage: [
    {
      id: 1,
      tenant_id: "t-1",
      event_id: "evt-job-verify-0001",
      metric: "job_verify",
      units: 3,
      unit_label: "jobs",
      happened_at: 1704300000,
    },
    {
      id: 2,
      tenant_id: "t-1",
      event_id: "evt-llm-in-0002",
      metric: "llm_tokens_in",
      units: 1284,
      unit_label: "tokens",
      happened_at: 1704400000,
    },
  ],
  count: 2,
  from: 1704067200,
  to: 1706745600,
};

const INVOICES = {
  invoices: [
    {
      id: "inv-2024-01",
      tenant_id: "t-1",
      period: "2024-01",
      line_items: [{ metric: "job_verify", units: 3, amount: 0.3 }],
      total: 0.3,
      currency: "USD",
      status: "draft",
    },
  ],
  count: 1,
};

const ADMIN = {
  principal: {
    user_id: "u-1",
    tenant_id: "t-1",
    roles: ["admin"],
    scopes: ["billing:read"],
  },
};

beforeEach(() => {
  apiGetMock.mockReset();
  getAuthMeMock.mockReset();
  getAuthMeMock.mockResolvedValue(ADMIN);
});

afterEach(() => {
  vi.clearAllMocks();
});

function mockBillingResponses(): void {
  apiGetMock.mockImplementation((path: string) => {
    if (path.startsWith("/api/v1/billing/plans")) return Promise.resolve(PLANS);
    if (path.startsWith("/api/v1/billing/subscription")) {
      return Promise.resolve(SUBSCRIPTION);
    }
    if (path.startsWith("/api/v1/billing/usage")) return Promise.resolve(USAGE);
    if (path.startsWith("/api/v1/billing/invoices")) return Promise.resolve(INVOICES);
    return Promise.reject(new Error("unexpected path " + path));
  });
}

describe("Billing page", () => {
  it("renders plans, the current subscription, usage rows and invoices", async () => {
    mockBillingResponses();
    render(<Billing />);
    await screen.findByTestId("billing-plans");

    const plans = within(screen.getByTestId("billing-plans"));
    expect(plans.getByText("Free")).toBeTruthy();
    expect(plans.getByText("Pro")).toBeTruthy();
    expect(plans.getByText("jobs_verify: 20")).toBeTruthy();
    expect(plans.getByText("jobs_verify: 500")).toBeTruthy();
    expect(plans.getByText("job_verify: $0.1/unit")).toBeTruthy();
    expect(plans.getByText("硬上限 Hard stop")).toBeTruthy();

    const sub = within(screen.getByTestId("billing-subscription"));
    expect(sub.getByText("active")).toBeTruthy();
    expect(sub.getByText("Pro")).toBeTruthy();
    expect(sub.getByText("t-1")).toBeTruthy();

    const usage = within(screen.getByTestId("billing-usage"));
    expect(usage.getByText("job_verify")).toBeTruthy();
    expect(usage.getByText("llm_tokens_in")).toBeTruthy();
    expect(usage.getByText(/1[,.s]?284/)).toBeTruthy();

    const invoices = within(screen.getByTestId("billing-invoices"));
    expect(invoices.getByText("2024-01")).toBeTruthy();
    expect(invoices.getByText("USD 0.30")).toBeTruthy();
    expect(invoices.getByText("draft")).toBeTruthy();
  });

  it("renders a CSV download link for the selected period", async () => {
    mockBillingResponses();
    render(<Billing />);
    await screen.findByTestId("usage-csv-link");

    const link = screen.getByTestId("usage-csv-link") as HTMLAnchorElement;
    expect(link.textContent).toContain("下载 CSV");
    expect(link.getAttribute("href")).toContain("/api/v1/billing/usage?from=");
    expect(link.getAttribute("href")).toContain("&to=");
    expect(link.getAttribute("href")).toContain("format=csv");
  });

  it("denies a known viewer before any API call with TENANT_FORBIDDEN and a contact-admin hint", async () => {
    getAuthMeMock.mockResolvedValue({
      principal: {
        user_id: "u-2",
        tenant_id: "t-1",
        roles: ["viewer"],
        scopes: ["jobs:read"],
      },
    });
    render(<Billing />);

    const forbidden = await screen.findByTestId("billing-forbidden");
    expect(forbidden.textContent).toContain("TENANT_FORBIDDEN");
    expect(screen.getByTestId("billing-contact-admin-hint").textContent).toContain(
      "Contact admin"
    );
    expect(apiGetMock).not.toHaveBeenCalled();
  });

  it("renders the TENANT_FORBIDDEN state when the API answers 403", async () => {
    // Unknown identity keeps the fail-open legacy behavior; the backend is
    // the authority and answers 403 TENANT_FORBIDDEN for a viewer.
    getAuthMeMock.mockRejectedValue(new Error("no /auth/me"));
    apiGetMock.mockRejectedValue(
      new ApiError(403, "role ['viewer'] may not read billing")
    );
    render(<Billing />);

    const forbidden = await screen.findByTestId("billing-forbidden");
    expect(forbidden.textContent).toContain("TENANT_FORBIDDEN");
    expect(screen.getByTestId("billing-contact-admin-hint").textContent).toContain(
      "Contact admin"
    );
    expect(apiGetMock).toHaveBeenCalled();
  });

  it("reports a non-403 API error in the errorbox", async () => {
    apiGetMock.mockRejectedValue(new Error("PROVIDER_UNAVAILABLE"));
    render(<Billing />);
    await screen.findByTestId("errorbox");

    expect(screen.getByTestId("errorbox").textContent).toContain(
      "PROVIDER_UNAVAILABLE"
    );
  });

  it("renders honest empty states without a subscription, usage or invoices", async () => {
    apiGetMock.mockImplementation((path: string) => {
      if (path.startsWith("/api/v1/billing/plans")) return Promise.resolve(PLANS);
      if (path.startsWith("/api/v1/billing/subscription")) {
        return Promise.resolve({ subscription: null });
      }
      if (path.startsWith("/api/v1/billing/usage")) {
        return Promise.resolve({ usage: [], count: 0, from: 0, to: 1 });
      }
      if (path.startsWith("/api/v1/billing/invoices")) {
        return Promise.resolve({ invoices: [], count: 0 });
      }
      return Promise.reject(new Error("unexpected path " + path));
    });
    render(<Billing />);
    await screen.findByTestId("billing-subscription");

    expect(
      screen.getByText("当前租户暂无订阅 No active subscription for this tenant")
    ).toBeTruthy();
    expect(screen.getByText("本期暂无用量记录")).toBeTruthy();
    expect(screen.getByText("本期暂无发票")).toBeTruthy();
  });

  it("shows the loading spinner while the identity check is pending", () => {
    getAuthMeMock.mockReturnValue(new Promise<never>(() => {}));
    render(<Billing />);

    expect(screen.getByText("加载中 LOADING…")).toBeTruthy();
  });
});
