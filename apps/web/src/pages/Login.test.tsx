import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import Login from "./Login";

function response(status: number, data: unknown) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

describe("workspace connection", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    window.localStorage.clear();
    window.location.hash = "#/login";
  });
  afterEach(() => { vi.unstubAllGlobals(); });

  it("explains the product and offers a guide before requiring credentials", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response(200, { auth_mode: "legacy", oidc: { enabled: false } })));
    await act(async () => { render(<Login />); });
    expect(screen.getByText("需求，真的实现了吗？")).toBeTruthy();
    expect(screen.getByRole("link", { name: /第一次使用/ }).getAttribute("href")).toBe("#/guide");
  });

  it("rejects an invalid API key without navigating into the workspace", async () => {
    const connected = vi.fn();
    const fetchMock = vi.fn(async (url: string) => url.endsWith("/auth/config")
      ? response(200, { auth_mode: "legacy", oidc: { enabled: false } })
      : response(401, { detail: "Invalid API key" }));
    vi.stubGlobal("fetch", fetchMock);
    render(<Login onConnected={connected} />);
    fireEvent.change(screen.getByLabelText("工作区 API Key"), { target: { value: "wrong-key" } });
    fireEvent.click(screen.getByRole("button", { name: "连接工作区" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("凭据未通过验证"));
    expect(connected).not.toHaveBeenCalled();
    expect(window.location.hash).toBe("#/login");
    expect(window.sessionStorage.getItem("specproof_api_key")).toBe("");
  });

  it("clears a stale bearer token before validating an API key and waits for success", async () => {
    window.sessionStorage.setItem("specproof_bearer_token", "old-token");
    const connected = vi.fn();
    const fetchMock = vi.fn(async (url: string) => url.endsWith("/auth/config")
      ? response(200, { auth_mode: "legacy", oidc: { enabled: false } })
      : response(200, { jobs: { total: 0 } }));
    vi.stubGlobal("fetch", fetchMock);
    render(<Login onConnected={connected} />);
    fireEvent.change(screen.getByLabelText("工作区 API Key"), { target: { value: " valid-key " } });
    fireEvent.click(screen.getByRole("button", { name: "连接工作区" }));
    await waitFor(() => expect(connected).toHaveBeenCalledOnce());
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/dashboard", expect.objectContaining({ headers: { Accept: "application/json", "X-API-Key": "valid-key" } }));
    expect(window.location.hash).toBe("#/dashboard");
    expect(window.sessionStorage.getItem("specproof_bearer_token")).toBe("");
  });

  it("defaults to access tokens in tenant mode and validates them before entry", async () => {
    const connected = vi.fn();
    const fetchMock = vi.fn(async (url: string) => url.endsWith("/auth/config")
      ? response(200, { auth_mode: "tenant", oidc: { enabled: false } })
      : response(200, { principal: { tenant_id: "tenant-a" } }));
    vi.stubGlobal("fetch", fetchMock);
    render(<Login onConnected={connected} />);
    const input = await screen.findByLabelText("工作区访问令牌");
    fireEvent.change(input, { target: { value: "sp_test_token" } });
    fireEvent.click(screen.getByRole("button", { name: "连接工作区" }));
    await waitFor(() => expect(connected).toHaveBeenCalledOnce());
    expect(fetchMock).toHaveBeenCalledWith("/auth/me", expect.objectContaining({ headers: { Accept: "application/json", Authorization: "Bearer sp_test_token" } }));
  });

  it("prevents duplicate submissions while a credential is being checked", async () => {
    let resolveConnection!: (result: Response) => void;
    const deferred = new Promise<Response>((resolve) => { resolveConnection = resolve; });
    const fetchMock = vi.fn((url: string) => url.endsWith("/auth/config")
      ? Promise.resolve(response(200, { auth_mode: "legacy", oidc: { enabled: false } }))
      : deferred);
    vi.stubGlobal("fetch", fetchMock);
    render(<Login />);
    fireEvent.change(screen.getByLabelText("工作区 API Key"), { target: { value: "valid-key" } });
    const button = screen.getByRole("button", { name: "连接工作区" });
    fireEvent.click(button);
    fireEvent.submit(button.closest("form")!);
    expect(fetchMock.mock.calls.filter(([url]) => url.endsWith("/api/v1/dashboard"))).toHaveLength(1);
    resolveConnection(response(200, {}));
    await waitFor(() => expect(window.location.hash).toBe("#/dashboard"));
  });
});
