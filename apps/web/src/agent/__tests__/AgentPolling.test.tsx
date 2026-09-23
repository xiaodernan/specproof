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
// Minimal fetch Response stand-in: only the fields the API client reads.
type StubResponse = { ok: boolean; status: number; json: () => Promise<unknown> };
const reply = (value: AgentJob): StubResponse => ({
  ok: true, status: 200, json: async () => ({ job: value }),
});
const flush = async () => { await act(async () => { await Promise.resolve(); }); };

// useAgentJob now also opens the SSE event stream (same real-time channel as
// the verification detail page), and that stream goes through `fetch` too.
// These tests count *detail reads*, so the stream request must be answered
// without being counted — otherwise the counters measure transport noise.
const isEventStream = (url: string) => url.includes("/events");
function stubFetch(handler: (call: number) => StubResponse | Promise<StubResponse>): {
  fetch: ReturnType<typeof vi.fn>;
  detailCalls: () => number;
} {
  let details = 0;
  const fetch = vi.fn(async (input: unknown): Promise<unknown> => {
    const url = String(input);
    if (isEventStream(url)) {
      return {
        ok: true, status: 200,
        body: { getReader: () => ({ read: () => new Promise(() => undefined) }) },
        headers: new Headers({ "Content-Type": "text/event-stream" }),
        json: async () => ({}),
      } as unknown as Response;
    }
    details += 1;
    return handler(details);
  });
  vi.stubGlobal("fetch", fetch);
  return { fetch, detailCalls: () => details };
}

describe("Agent polling", () => {
  beforeEach(() => { vi.useFakeTimers(); vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible"); });
  afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it("has stable reload, pauses hidden tabs, stops on terminal and aborts on unmount", async () => {
    const { detailCalls } = stubFetch((n) =>
      n === 1 ? reply(job) : reply({ ...job, status: "COMPLETED" }));
    const hook = renderHook(() => useAgentJob("one"));
    await flush();
    const reload = hook.result.current.reload;
    hook.rerender();
    expect(hook.result.current.reload).toBe(reload);
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    await act(async () => vi.advanceTimersByTime(10000));
    expect(detailCalls()).toBe(1);
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    await flush();
    await act(async () => vi.advanceTimersByTime(10000));
    expect(detailCalls()).toBe(2);
    hook.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("does not overlap requests and drops stale responses after changing jobs", async () => {
    const pending: Array<{ url: string; resolve: (value: StubResponse) => void }> = [];
    const { fetch } = stubFetch(() => reply(job));
    // Hold every detail response open so we can prove two things: a second
    // reload does not start a parallel read, and the in-flight read for job
    // "one" is aborted (and its response discarded) when we switch to "two".
    fetch.mockImplementation(async (input: unknown) => {
      const url = String(input);
      if (isEventStream(url)) {
        return {
          ok: true, status: 200,
          body: { getReader: () => ({ read: () => new Promise(() => undefined) }) },
          headers: new Headers({ "Content-Type": "text/event-stream" }),
          json: async () => ({}),
        } as unknown as Response;
      }
      return new Promise<StubResponse>((resolve) => { pending.push({ url, resolve }); });
    });

    const hook = renderHook(({ id }) => useAgentJob(id), { initialProps: { id: "one" } });
    await flush();
    act(() => { hook.result.current.reload(); hook.result.current.reload(); });
    await flush();
    expect(pending.filter((p) => p.url.includes("/one")).length).toBe(1);
    const first = pending.find((p) => p.url.includes("/one"))!;
    const signal = (fetch.mock.calls.find(([i]) => String(i) === first.url)?.[1] as RequestInit)?.signal as AbortSignal;

    hook.rerender({ id: "two" });
    expect(signal.aborted).toBe(true);
    await flush();
    // resolve the abandoned read AFTER switching jobs — it must be dropped
    first.resolve(reply(job));
    await flush();
    const second = pending.find((p) => p.url.includes("/two"))!;
    second.resolve(reply({ ...job, id: "two", status: "COMPLETED" }));
    await flush();
    expect(hook.result.current.job?.id).toBe("two");
  });

  it("stops retries after authorization errors", async () => {
    const { detailCalls } = stubFetch(() => ({
      ok: false, status: 401, headers: new Headers(),
      json: async () => ({ detail: "Session expired" }),
    }) as unknown as Response);
    const hook = renderHook(() => useAgentJob("one"));
    await flush();
    await act(async () => vi.advanceTimersByTime(30000));
    expect(detailCalls()).toBe(1);
    expect(String(hook.result.current.error)).toContain("Session expired");
  });

  it("detail uses one request and shows planning failures without invented approvals", async () => {
    const { detailCalls } = stubFetch(() =>
      reply({ ...job, status: "FAILED", result: { verdict: "FAILED", reason: "Model is unavailable" } }));
    render(<AgentJobDetail jobId="one" />);
    await flush();
    expect(detailCalls()).toBe(1);
    expect(screen.getByRole("alert").textContent).toContain("Model is unavailable");
    expect(screen.queryByText(/Plan approved/)).toBeNull();
    expect(screen.queryByText(/Gate decided/)).toBeNull();
    expect((screen.getByText("取消 Cancel").closest("button") as HTMLButtonElement).disabled).toBe(true);
  });

  it("surfaces the live event stream state on the detail page", async () => {
    stubFetch(() => reply({ ...job, status: "EXECUTING" }));
    render(<AgentJobDetail jobId="one" />);
    await flush();
    // 开发助手此前只有轮询；现在与验证详情页共用同一套实时通道。
    expect(screen.getByText(/实时连接：/)).toBeTruthy();
  });

  it("makes awaiting approval actionable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply({ ...job, status: "AWAITING_APPROVAL" })));
    render(<AgentJobDetail jobId="one" />);
    await flush();
    expect(screen.getByRole("link", { name: "审阅并批准计划 →" }).getAttribute("href")).toBe("#/agent/jobs/one/plan");
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("0");
  });
});
