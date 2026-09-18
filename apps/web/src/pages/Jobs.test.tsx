import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import Jobs from "./Jobs";
import { apiGet } from "../api";

vi.mock("../api", () => ({ apiGet: vi.fn() }));
const get = vi.mocked(apiGet);
beforeEach(() => { get.mockReset(); });

describe("verification history", () => {
  it("requests server pagination and searches across the complete history", async () => {
    get.mockResolvedValue({ jobs: [{ id: "job-1", repo_path: "/workspace/orders", status: "VERIFIED" }], total: 67 });
    render(<Jobs />);
    await screen.findByRole("link", { name: "orders" });
    expect(get.mock.calls[0][0]).toBe("/jobs?limit=25&offset=0");
    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() => expect(get.mock.calls[get.mock.calls.length - 1]?.[0]).toBe("/jobs?limit=25&offset=25"));
    fireEvent.change(screen.getByRole("searchbox", { name: "搜索验证" }), { target: { value: "payments" } });
    await waitFor(() => expect(get.mock.calls[get.mock.calls.length - 1]?.[0]).toBe("/jobs?limit=25&offset=0&q=payments"));
    fireEvent.change(screen.getByRole("combobox", { name: "验证状态" }), { target: { value: "BLOCKED" } });
    await waitFor(() => expect(get.mock.calls[get.mock.calls.length - 1]?.[0]).toBe("/jobs?limit=25&offset=0&status=BLOCKED&q=payments"));
  });

  it("makes the first action available without requiring API knowledge", async () => {
    get.mockResolvedValue({ jobs: [], total: 0 });
    render(<Jobs />);
    await screen.findByText("从第一次验证开始");
    fireEvent.click(screen.getByRole("button", { name: "创建第一次验证 →" }));
    expect(window.location.hash).toBe("#/jobs/new");
  });
});
