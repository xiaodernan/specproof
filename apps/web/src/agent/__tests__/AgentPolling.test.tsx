import { act, cleanup, render, renderHook, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { type AgentJob } from "../../api";
import { useAgentJob } from "../components";
import AgentJobDetail from "../pages/AgentJobDetail";

const job: AgentJob = {
  id: "one", task_name: "Repair", repo_path: "/repo", spec_text: "repair code", plan: null,
  status: "PLANNING", result: null, worker_id: null, events_count: 0, approvals_count: 0,
  created_at: "2026-09-18T10:00:00Z", updated_at: "2026-09-18T10:00:00Z",
  progress: { percent: 0, current_step: 0, message: "planning", updated_at: "" },
};
const reply = (value: AgentJob) => ({ ok: true, status: 200, json: async () => ({ job: value }) });
const flush = async () => { await act(async () => { await Promise.resolve(); }); };

describe("Agent polling", () => {
  beforeEach(() => { vi.useFakeTimers(); vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible"); });
  afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it("has stable reload, pauses hidden tabs, stops on terminal and aborts on unmount", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(reply(job)).mockResolvedValue(reply({ ...job, status: "COMPLETED" }));
    vi.stubGlobal("fetch", fetch);
    const hook = renderHook(() => useAgentJob("one"));
    await flush();
    const reload = hook.result.current.reload;
    hook.rerender();
    expect(hook.result.current.reload).toBe(reload);
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    await act(async () => vi.advanceTimersByTime(10000));
    expect(fetch).toHaveBeenCalledTimes(1);
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    await flush();
    await act(async () => vi.advanceTimersByTime(10000));
    expect(fetch).toHaveBeenCalledTimes(2);
    hook.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("does not overlap requests and drops stale responses after changing jobs", async () => {
    let resolveFirst!: (value: unknown) => void;
    const fetch = vi.fn().mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve; }))
      .mockResolvedValue(reply({ ...job, id: "two", status: "COMPLETED" }));
    vi.stubGlobal("fetch", fetch);
    const hook = renderHook(({ id }) => useAgentJob(id), { initialProps: { id: "one" } });
    act(() => { hook.result.current.reload(); hook.result.current.reload(); });
    await act(async () => vi.advanceTimersByTime(10000));
    expect(fetch).toHaveBeenCalledTimes(1);
    const signal = fetch.mock.calls[0][1].signal as AbortSignal;
    hook.rerender({ id: "two" });
    expect(signal.aborted).toBe(true);
    await flush();
    resolveFirst(reply(job));
    await flush();
    expect(hook.result.current.job?.id).toBe("two");
  });

  it("stops retries after authorization errors", async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: false, status: 401, headers: new Headers(), json: async () => ({ detail: "Session expired" }) });
    vi.stubGlobal("fetch", fetch);
    const hook = renderHook(() => useAgentJob("one"));
    await flush();
    await act(async () => vi.advanceTimersByTime(30000));
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(String(hook.result.current.error)).toContain("Session expired");
  });

  it("detail uses one request and shows planning failures without invented approvals", async () => {
    const fetch = vi.fn().mockResolvedValue(reply({ ...job, status: "FAILED", result: { verdict: "FAILED", reason: "Model is unavailable" } }));
    vi.stubGlobal("fetch", fetch);
    render(<AgentJobDetail jobId="one" />);
    await flush();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("alert").textContent).toContain("Model is unavailable");
    expect(screen.queryByText(/Plan approved/)).toBeNull();
    expect(screen.queryByText(/Gate decided/)).toBeNull();
    expect((screen.getByText("取消 Cancel").closest("button") as HTMLButtonElement).disabled).toBe(true);
  });

  it("makes awaiting approval actionable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply({ ...job, status: "AWAITING_APPROVAL" })));
    render(<AgentJobDetail jobId="one" />);
    await flush();
    expect(screen.getByRole("link", { name: "审阅并批准计划 →" }).getAttribute("href")).toBe("#/agent/jobs/one/plan");
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("0");
  });
});
