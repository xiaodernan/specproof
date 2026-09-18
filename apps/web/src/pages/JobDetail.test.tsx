import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import JobDetail from "./JobDetail";
import { apiGet, openProgressStream } from "../api";

vi.mock("../api", () => ({ apiGet: vi.fn(), openProgressStream: vi.fn(), downloadCapsule: vi.fn() }));
const get = vi.mocked(apiGet);
const open = vi.mocked(openProgressStream);
const close = vi.fn();
beforeEach(() => { get.mockReset(); open.mockReset(); close.mockReset(); open.mockReturnValue(close); });
afterEach(() => { vi.useRealTimers(); });

describe("verification lifecycle", () => {
  it("keeps the job and actionable errors visible if result services fail", async () => {
    get.mockImplementation((async (path: string) => {
      if (path === "/jobs/failed-job") return { job: { id: "failed-job", status: "ERROR", last_error: "Repository not found", repo_path: "/missing" } };
      throw new Error("Artifacts unavailable");
    }) as typeof apiGet);
    render(<JobDetail jobId="failed-job" />);
    await screen.findByText("执行遇到错误");
    expect(screen.getByText(/Repository not found/)).toBeTruthy();
    expect(screen.getByText(/部分验证结果暂时无法读取/)).toBeTruthy();
    expect(open).not.toHaveBeenCalled();
    expect(get.mock.calls.some(([path]) => path.endsWith("/certificate"))).toBe(false);
  });

  it("refreshes final results and closes live progress after completion", async () => {
    vi.useFakeTimers();
    let status = "RUNNING";
    get.mockImplementation((async (path: string) => {
      if (path === "/jobs/job-1") return { job: { id: "job-1", status, repo_path: "/project" } };
      if (path.endsWith("/summary")) return { summary: status === "VERIFIED" ? { verdict: "VERIFIED", contracts_total: 3, matrix_passed: 3 } : {} };
      if (path.endsWith("/stages")) return { job_id: "job-1", stages: [], event_count: 0, degraded: false };
      return { job_id: "job-1", findings: [], count: 0, degraded: false };
    }) as typeof apiGet);
    render(<JobDetail jobId="job-1" />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByText("正在检查代码与需求")).toBeTruthy();
    status = "VERIFIED";
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(screen.getByText("本次验证通过")).toBeTruthy();
    expect(close).toHaveBeenCalledOnce();
    const calls = get.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(20000); });
    expect(get).toHaveBeenCalledTimes(calls);
  });

  it("loads the report only when requested", async () => {
    get.mockImplementation((async (path: string) => {
      if (path === "/jobs/job-1") return { job: { id: "job-1", status: "VERIFIED" } };
      if (path.endsWith("/summary")) return { summary: {} };
      if (path.endsWith("/stages")) return { job_id: "job-1", stages: [], event_count: 0, degraded: false };
      if (path.endsWith("/certificate")) return { path: "report.json", document: { verdict: "VERIFIED" } };
      return { job_id: "job-1", findings: [], count: 0, degraded: false };
    }) as typeof apiGet);
    render(<JobDetail jobId="job-1" />);
    await screen.findByText("本次验证通过");
    expect(get.mock.calls.some(([path]) => path.endsWith("/certificate"))).toBe(false);
    fireEvent.click(screen.getByRole("tab", { name: "验证报告" }));
    await waitFor(() => expect(get.mock.calls.some(([path]) => path.endsWith("/certificate"))).toBe(true));
  });
});
