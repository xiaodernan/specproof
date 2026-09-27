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

  it("lets the user sort the visible rows by clicking a header", async () => {
    get.mockResolvedValue({
      jobs: [
        { id: "job-b", repo_path: "/workspace/zeta", status: "BLOCKED", updated_at: "2026-09-01T10:00:00Z" },
        { id: "job-a", repo_path: "/workspace/alpha", status: "VERIFIED", updated_at: "2026-09-02T10:00:00Z" },
      ],
      total: 2,
    });
    render(<Jobs />);
    await screen.findByRole("link", { name: "zeta" });
    const order = () => screen.getAllByRole("link", { name: /alpha|zeta/ }).map((el) => el.textContent);
    expect(order()[0]).toBe("zeta");
    fireEvent.click(screen.getByRole("button", { name: /项目 \/ 验证编号/ }));
    expect(order()[0]).toBe("alpha");
    // second click reverses the direction
    fireEvent.click(screen.getByRole("button", { name: /项目 \/ 验证编号/ }));
    expect(order()[0]).toBe("zeta");
  });

  it("makes the first action available without requiring API knowledge", async () => {
    get.mockResolvedValue({ jobs: [], total: 0 });
    render(<Jobs />);
    await screen.findByText("从第一次验证开始");
    fireEvent.click(screen.getByRole("button", { name: "创建第一次验证 →" }));
    expect(window.location.hash).toBe("#/jobs/new");
  });

  it("renders one canonical status label per row (no 正在验证/正在验收 drift)", async () => {
    // Regression: the list once showed a StatusPill ("正在验收") next to a
    // private STATUS_LABELS copy ("正在验证") for the same status. Both now
    // come from the shared statusLabel source, and the pill is not duplicated.
    get.mockResolvedValue({ jobs: [{ id: "j1", repo_path: "/w/svc", status: "RUNNING" }], total: 1 });
    render(<Jobs />);
    await screen.findByRole("link", { name: "svc" });
    // The row's status pill (not the filter dropdown option) shows the label once.
    expect(screen.getAllByText("正在验收", { selector: ".pill" }).length).toBe(1);
    expect(screen.queryByText("正在验证")).toBeNull();
  });
});

describe("status filter offers only real statuses", () => {
  it("includes every status the state machine can name, STALE included", async () => {
    get.mockResolvedValue({ jobs: [], total: 0 });
    render(<Jobs />);
    const select = await screen.findByRole("combobox", { name: "验证状态" });

    const values = Array.from(select.querySelectorAll("option")).map(
      (o) => (o as HTMLOptionElement).value
    );
    // storage/mysql.py::ALL_STATUSES — the dropdown is built from the same set.
    for (const status of [
      "PENDING", "QUEUED", "RUNNING", "WAITING_FOR_PROVIDER",
      "VERIFIED", "BLOCKED", "FAILED", "ERROR", "CANCELLED", "STALE",
    ]) {
      expect(values).toContain(status);
    }
    // STALE is a real terminal status; it used to be missing from the dropdown
    // AND rejected with a 422 if you typed it into the URL yourself.
    expect(screen.getByRole("option", { name: "已过期" })).toBeTruthy();
  });

  it("never offers a verdict word as a status filter", async () => {
    get.mockResolvedValue({ jobs: [], total: 0 });
    render(<Jobs />);
    const select = await screen.findByRole("combobox", { name: "验证状态" });

    const values = Array.from(select.querySelectorAll("option")).map(
      (o) => (o as HTMLOptionElement).value
    );
    // UNVERIFIED/INCONCLUSIVE are matrix/verdict words: offering them sent a
    // filter that could not match anything, so the page said "没有找到".
    expect(values).not.toContain("UNVERIFIED");
    expect(values).not.toContain("INCONCLUSIVE");
    expect(screen.queryByRole("option", { name: "证据不足" })).toBeNull();
  });
});
