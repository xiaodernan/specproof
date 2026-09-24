import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import Guide from "./Guide";
import { apiGet, getBearerToken } from "../api";

// The onboarding checklist must never upgrade "we could not look" into "you
// have not done it". These cases pin the three answers apart: detected,
// genuinely absent, and unreadable.
vi.mock("../api", () => ({
  apiGet: vi.fn(),
  getBearerToken: vi.fn(() => "workspace-token"),
  getApiKey: vi.fn(() => ""),
}));
const get = vi.mocked(apiGet);
const bearer = vi.mocked(getBearerToken);

const KEY = "specproof_onboarding_v1";

beforeEach(() => {
  window.localStorage.clear();
  get.mockReset();
  bearer.mockReturnValue("workspace-token");
});

afterEach(() => {
  window.localStorage.clear();
});

describe("guide onboarding checklist", () => {
  it("waits on the probe instead of guessing", async () => {
    get.mockReturnValue(new Promise(() => undefined));
    render(<Guide />);
    const marks = await screen.findAllByText("无法确认");
    expect(marks.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("正在检测工作区连接…")).toBeTruthy();
    expect(screen.queryByText(/^1 \/ 4/)).toBeNull();
  });

  it("answers a logged-out reader instead of firing a doomed probe", async () => {
    bearer.mockReturnValue("");
    render(<Guide />);
    await waitFor(() => expect(screen.getAllByText("未完成").length).toBe(3));
    expect(get).not.toHaveBeenCalled();
    // Step 1 is a fact about this browser, not a failed lookup.
    expect(screen.getByText(/这个浏览器里还没有工作区凭据/)).toBeTruthy();
    expect(screen.queryByText(/工作区请求失败/)).toBeNull();
    // Step 3 still cannot be answered without a workspace.
    expect(screen.getAllByText("无法确认").length).toBe(1);
    expect(screen.getByText(/无法确认是否已经建过验证/)).toBeTruthy();
  });

  it("does not turn a failed probe into 'not done'", async () => {    get.mockRejectedValue(new Error("offline"));
    render(<Guide />);
    await waitFor(() => expect(screen.getAllByText("无法确认").length).toBe(2));
    expect(screen.getByText(/这不等于没有连接/)).toBeTruthy();
    expect(screen.getByText(/读不到验证任务列表/)).toBeTruthy();
    // Nothing may claim the first step is finished.
    expect(screen.queryByText("已完成")).toBeNull();
  });

  it("says a verification is missing only when the list really answered zero", async () => {
    get.mockResolvedValue({ jobs: [], total: 0 });
    render(<Guide />);
    await waitFor(() => expect(screen.getAllByText("已完成").length).toBe(1));
    // Three steps are honestly "not done": no verification yet, no result page
    // recorded on this browser, and the manual step nobody ticked.
    expect(screen.getAllByText("未完成").length).toBe(3);
    expect(screen.getByText(/工作区里已有 0 次验证/)).toBeTruthy();
    expect(screen.queryByText("无法确认")).toBeNull();
  });

  it("counts an existing verification without a hand tick", async () => {
    get.mockResolvedValue({ jobs: [{ id: "job-1" }], total: 3 });
    render(<Guide />);
    await waitFor(() => expect(screen.getAllByText("已完成").length).toBe(2));
    expect(screen.getByText(/工作区里已有 3 次验证/)).toBeTruthy();
  });

  it("refuses to read a corrupt local record as a fresh start", async () => {
    window.localStorage.setItem(KEY, "{corrupt");
    get.mockResolvedValue({ jobs: [], total: 0 });
    render(<Guide />);
    expect(await screen.findByText(/本机进度记录读不出来/)).toBeTruthy();
    expect(screen.getByText(/这不代表你从未开始/)).toBeTruthy();
    const box = screen.getByRole("checkbox", { name: "我已完成" });
    expect((box as HTMLInputElement).disabled).toBe(true);
    expect(screen.getAllByText("无法确认").length).toBe(2);
  });

  it("persists a manual tick, and only a manual tick, to this browser", async () => {
    get.mockResolvedValue({ jobs: [], total: 0 });
    render(<Guide />);
    const box = (await screen.findByRole("checkbox", { name: "我已完成" })) as HTMLInputElement;
    expect(box.checked).toBe(false);
    fireEvent.click(box);
    await waitFor(() => expect(box.checked).toBe(true));
    expect(JSON.parse(window.localStorage.getItem(KEY) || "{}").manual.prepare_spec).toBeTruthy();
    // The detected steps stay the system's answer, not a box the user can tick.
    expect(screen.getAllByRole("checkbox").length).toBe(1);
  });
});
