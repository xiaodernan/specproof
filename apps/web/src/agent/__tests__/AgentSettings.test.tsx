import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import AgentSettings from "../pages/AgentSettings";

const storedConfig = {
  base_url: "https://model.example/v1", model: "test-model", reasoning_effort: "max",
  protocol: "responses", configured: true, key_hint: "已保存", source: "local_file",
};

function reply(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

describe("model connection settings", () => {
  beforeEach(() => { sessionStorage.clear(); localStorage.clear(); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it("keeps the server secret masked and saves all selected model options", async () => {
    const fetchMock = vi.fn(async (_url: string, options?: RequestInit) => reply(options?.method === "POST"
      ? { ...storedConfig, model: "updated-model" } : storedConfig));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentSettings />);
    const model = await screen.findByLabelText("模型名称");
    const key = screen.getByLabelText("模型 API Key") as HTMLInputElement;
    expect(key.value).toBe("");
    expect(key.type).toBe("password");
    fireEvent.change(model, { target: { value: "updated-model" } });
    fireEvent.change(key, { target: { value: "secret-value" } });
    expect((screen.getByRole("button", { name: "测试连接" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "保存配置" }));
    await screen.findByText("模型配置已保存。点击测试连接，确认服务能够实际返回内容。");
    const savedCall = fetchMock.mock.calls.find(([, options]) => options?.method === "POST");
    expect(savedCall?.[0]).toBe("/api/v1/model/config");
    expect(JSON.parse(savedCall?.[1]?.body as string)).toEqual({
      base_url: "https://model.example/v1", model: "updated-model", api_key: "secret-value",
      reasoning_effort: "max", protocol: "responses",
    });
    expect(key.value).toBe("");
    expect(JSON.stringify({ ...localStorage })).not.toContain("secret-value");
    expect(JSON.stringify({ ...sessionStorage })).not.toContain("secret-value");
  });

  it("preserves an existing key when saving other fields", async () => {
    const fetchMock = vi.fn(async () => reply(storedConfig));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentSettings />);
    await screen.findByLabelText("模型名称");
    fireEvent.click(screen.getByRole("button", { name: "保存配置" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(JSON.parse((fetchMock.mock.calls as unknown as [string, RequestInit][])[1][1].body as string).api_key).toBe("");
  });

  it("reports a real test result separately from saving configuration", async () => {
    const fetchMock = vi.fn(async (url: string) => reply(url.endsWith("/test")
      ? { ok: false, message: "模型服务拒绝访问，请检查账号的模型权限。", model: "test-model", protocol: "responses", latency_ms: 250, reasoning_effort: "max" }
      : storedConfig));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentSettings />);
    await screen.findByLabelText("模型名称");
    expect(screen.queryByText("连接测试通过")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "测试连接" }));
    await screen.findByText("连接测试未通过");
    expect(screen.getByText("模型服务拒绝访问，请检查账号的模型权限。")).toBeTruthy();
  });

  it("renders an explicit administrator-only state for tenant credentials", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply({ detail: "shared model configuration" }, 403)));
    render(<AgentSettings />);
    await screen.findByText("由部署管理员管理");
    expect(screen.queryByLabelText("模型 API Key")).toBeNull();
    expect(screen.queryByRole("button", { name: "保存配置" })).toBeNull();
  });

  it("allows testing but prevents overwriting deployment environment settings", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply({ ...storedConfig, source: "environment" })));
    render(<AgentSettings />);
    const model = await screen.findByLabelText("模型名称");
    expect(model.closest("fieldset")?.disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "保存配置" })).toBeNull();
    expect((screen.getByRole("button", { name: "测试连接" }) as HTMLButtonElement).disabled).toBe(false);
  });
});
