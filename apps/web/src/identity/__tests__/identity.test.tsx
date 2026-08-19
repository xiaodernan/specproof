import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import TenantSwitcher from "../TenantSwitcher";
import TenantUsers from "../pages/TenantUsers";
import TenantTokens from "../pages/TenantTokens";

// Identity pages talk to the backend through fetch; tests stub fetch and
// never touch the network. sessionStorage/localStorage are stubbed with
// in-memory maps (same convention as the agent console tests).

function mockStorage() {
  const store = new Map<string, string>();
  return {
    getItem: vi.fn((k: string) => store.get(k) ?? null),
    setItem: vi.fn((k: string, v: string) => void store.set(k, v)),
    removeItem: vi.fn((k: string) => void store.delete(k)),
    key: vi.fn(() => null),
    clear: vi.fn(() => void store.clear()),
    length: 0,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: () => Promise.resolve(body),
    headers: new Headers(),
  } as Response;
}

const ME_BODY = {
  principal: {
    user_id: "u-1",
    tenant_id: "0f9e0000-0000-0000-0000-000000000001",
    roles: ["operator"],
    scopes: [],
    email: "op@a.example.com",
  },
};

beforeEach(() => {
  vi.stubGlobal("sessionStorage", mockStorage());
  vi.stubGlobal("localStorage", mockStorage());
  vi.stubGlobal("location", { hash: "#/identity" });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("TenantSwitcher", () => {
  it("renders the current tenant and roles from /auth/me", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(ME_BODY)));
    vi.stubGlobal("fetch", fetchMock);
    render(<TenantSwitcher />);
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });
    expect(await screen.findByText("当前租户 TENANT — 0f9e0000")).toBeTruthy();
    expect(screen.getByText("operator")).toBeTruthy();
  });

  it("shows the legacy label when /auth/me rejects", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(jsonResponse({ detail: "no" }, 401))
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<TenantSwitcher />);
    expect(
      await screen.findByText("当前租户 TENANT — 单租户 LEGACY")
    ).toBeTruthy();
  });
});

describe("TenantUsers", () => {
  it("lists users and creates a new one", async () => {
    let created = false;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/admin/users")) {
        if ((init?.method ?? "GET") === "POST") {
          created = true;
          return Promise.resolve(
            jsonResponse({ user: { id: "u-2", email: "b@example.com" } }, 201)
          );
        }
        return Promise.resolve(
          jsonResponse({
            users: [
              {
                id: "u-1",
                tenant_id: "t-1",
                email: "a@example.com",
                role: "viewer",
                status: "active",
                created_at: 1,
              },
              ...(created
                ? [
                    {
                      id: "u-2",
                      tenant_id: "t-1",
                      email: "b@example.com",
                      role: "viewer",
                      status: "active",
                      created_at: 2,
                    },
                  ]
                : []),
            ],
            count: created ? 2 : 1,
          })
        );
      }
      return Promise.resolve(jsonResponse({}, 404));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<TenantUsers />);
    expect(await screen.findByText("a@example.com")).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText("user@example.com"), {
      target: { value: "b@example.com" },
    });
    fireEvent.click(screen.getByText("创建 Create"));
    expect(await screen.findByText("b@example.com")).toBeTruthy();
  });
});

describe("TenantTokens", () => {
  it("mints a token and reveals the show-once cleartext", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/admin/tokens") && (init?.method ?? "GET") === "POST") {
        return Promise.resolve(
          jsonResponse(
            {
              token: {
                id: "tok-2", user_id: "u-1", name: "ci-2",
                scopes: "", expires_at: null, created_at: 1,
              },
              cleartext: "sp_" + "abc_" + "def",
            },
            201
          )
        );
      }
      if (url.endsWith("/api/v1/admin/tokens")) {
        return Promise.resolve(
          jsonResponse({
            tokens: [
              {
                id: "tok-1",
                user_id: "u-1",
                user_email: "op@a.example.com",
                name: "ci",
                scopes: "",
                expires_at: null,
                last_used_at: null,
                created_at: 1,
              },
            ],
            count: 1,
          })
        );
      }
      return Promise.resolve(jsonResponse({}, 404));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<TenantTokens />);
    expect(await screen.findByText("ci")).toBeTruthy();
    fireEvent.click(screen.getByText("签发 Mint"));
    const cleartext = await screen.findByTestId("cleartext");
    expect(cleartext.textContent).toContain("sp_");
    expect(cleartext.textContent).toContain("abc");
  });

  it("revokes a token via DELETE", async () => {
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      if ((init?.method ?? "GET") === "DELETE") {
        return Promise.resolve(jsonResponse({ revoked: true, token_id: "tok-1" }));
      }
      return Promise.resolve(
        jsonResponse({
          tokens: [
            {
              id: "tok-1",
              user_id: "u-1",
              user_email: "op@a.example.com",
              name: "ci",
              scopes: "",
              expires_at: null,
              last_used_at: null,
              created_at: 1,
            },
          ],
          count: 1,
        })
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<TenantTokens />);
    expect(await screen.findByText("ci")).toBeTruthy();
    fireEvent.click(screen.getByText("吊销 Revoke"));
    await waitFor(() => {
      const deletes = fetchMock.mock.calls.filter(
        (c: unknown[]) => c[1] && (c[1] as RequestInit).method === "DELETE"
      );
      expect(deletes.length).toBe(1);
    });
  });
});

describe("permission explanation (§14.4)", () => {
  function viewerFetch(adminPath: string, emptyBody: unknown) {
    return vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) {
        return Promise.resolve(
          jsonResponse({
            principal: {
              user_id: "u-9",
              tenant_id: "t-1",
              roles: ["viewer"],
              scopes: [],
            },
          })
        );
      }
      if (url.endsWith(adminPath)) {
        return Promise.resolve(jsonResponse(emptyBody));
      }
      return Promise.resolve(jsonResponse({}, 404));
    });
  }

  it("TenantUsers forbidden view explains tenant/role/source/expiry with a contact-admin hint", async () => {
    vi.stubGlobal("fetch", viewerFetch("/api/v1/admin/users", { users: [], count: 0 }));
    render(<TenantUsers />);
    expect(await screen.findByTestId("identity-forbidden")).toBeTruthy();
    expect(
      screen.getByText(
        "无权限 NO ACCESS — 用户管理仅对 admin/operator 开放 (RBAC fail-closed)"
      )
    ).toBeTruthy();
    expect(screen.getByText(/租户 Tenant/)).toBeTruthy();
    expect(screen.getByText(/角色 Role/)).toBeTruthy();
    expect(screen.getByText(/来源 Source/)).toBeTruthy();
    expect(screen.getByText(/失效 Expiry/)).toBeTruthy();
    expect(screen.getByTestId("contact-admin-hint").textContent).toContain(
      "请联系租户管理员"
    );
    expect(screen.queryByPlaceholderText("user@example.com")).toBeNull();
  });

  it("TenantTokens forbidden view keeps the same identity-forbidden contract", async () => {
    vi.stubGlobal("fetch", viewerFetch("/api/v1/admin/tokens", { tokens: [], count: 0 }));
    render(<TenantTokens />);
    expect(await screen.findByTestId("identity-forbidden")).toBeTruthy();
    expect(
      screen.getByText(
        "无权限 NO ACCESS — Token 管理仅对 admin/operator 开放 (RBAC fail-closed)"
      )
    ).toBeTruthy();
    expect(screen.getByText(/租户 Tenant/)).toBeTruthy();
    expect(screen.getByText(/失效 Expiry/)).toBeTruthy();
    expect(screen.getByTestId("contact-admin-hint")).toBeTruthy();
  });
});
