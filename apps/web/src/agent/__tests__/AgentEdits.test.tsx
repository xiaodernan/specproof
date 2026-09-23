import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { type AgentEvent, type AgentJob, openAgentEventStream } from "../../api";
import AgentEdits from "../pages/AgentEdits";

vi.mock("../../api", async (original) => ({
  ...(await original<typeof import("../../api")>()), openAgentEventStream: vi.fn(),
}));

const job: AgentJob = {
  id: "job-1", task_name: "pagination", repo_path: "D:/repos/svc", spec_text: "add pagination",
  status: "EXECUTING", plan: null, result: null, worker_id: "w1", events_count: 1,
  approvals_count: 0, created_at: "2026-08-18T00:00:00Z", updated_at: "2026-08-18T00:00:00Z",
  progress: { percent: 42, current_step: 0, message: "working", updated_at: "2026-08-18T00:00:00Z" },
};

describe("AgentEdits", () => {
  const sessions: { event: (e: AgentEvent) => void; done: () => void }[] = [];
  beforeEach(() => {
    sessions.length = 0;
    vi.mocked(openAgentEventStream).mockImplementation((_id, event, _state, done) => {
      sessions.push({ event, done: done! });
      return vi.fn();
    });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, status: 200, json: async () => ({ job }),
    })));
  });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

  it("renders edit frames from the shared channel and ignores non-edit events", async () => {
    render(<AgentEdits jobId="job-1" />);
    await waitFor(() => expect(sessions.length).toBeGreaterThan(0));
    act(() => {
      sessions[0].event({ seq: 2, type: "tool_call", at: job.created_at, data: {} });
      sessions[0].event({ seq: 3, type: "edit", at: job.created_at, data: { bundle: { files_changed: 2 } } });
    });
    expect(screen.getByText("#3")).toBeTruthy();
    expect(screen.getByText(/2 个文件/)).toBeTruthy();
    // The non-edit event (seq 2) must never leak into the edits list.
    expect(screen.queryByText("#2")).toBeNull();
  });

  it("never opens its own fetch-based event stream (no API key in the URL)", async () => {
    render(<AgentEdits jobId="job-1" />);
    await waitFor(() => expect(sessions.length).toBeGreaterThan(0));
    const calls = vi.mocked(fetch).mock.calls.map((c) => String(c[0]));
    expect(calls.some((u) => u.includes("/events"))).toBe(false);
    expect(calls.some((u) => u.includes("key="))).toBe(false);
  });
});
