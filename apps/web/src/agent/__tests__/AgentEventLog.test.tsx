import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { type AgentEvent, type AgentJob, openAgentEventStream } from "../../api";
import AgentEventLog from "../pages/AgentEventLog";

vi.mock("../../api", async (original) => ({
  ...(await original<typeof import("../../api")>()), openAgentEventStream: vi.fn(),
}));

const job: AgentJob = {
  id: "job-1", task_name: "pagination", repo_path: "D:/repos/svc", spec_text: "add pagination",
  status: "EXECUTING", plan: null, result: null, worker_id: "w1", events_count: 1,
  approvals_count: 0, created_at: "2026-08-18T00:00:00Z", updated_at: "2026-08-18T00:00:00Z",
  progress: { percent: 42, current_step: 0, message: "working", updated_at: "2026-08-18T00:00:00Z" },
};

describe("AgentEventLog", () => {
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

  it("renders events delivered through the shared realtime channel", async () => {
    render(<AgentEventLog jobId="job-1" />);
    await waitFor(() => expect(sessions.length).toBeGreaterThan(0));
    act(() => {
      sessions[0].event({ seq: 1, type: "tool_call", at: job.created_at, data: { name: "read_file" } });
    });
    expect(screen.getByText("#1")).toBeTruthy();
    expect(screen.getByText(/read_file/)).toBeTruthy();
    // Not yet terminal — the panel keeps showing the live indicator.
    expect(screen.getByText(/实时更新中/)).toBeTruthy();
  });

  it("switches to the synced label once the server signals done", async () => {
    render(<AgentEventLog jobId="job-1" />);
    await waitFor(() => expect(sessions.length).toBeGreaterThan(0));
    await act(async () => { sessions[0].done(); });
    expect(screen.getByText(/已同步/)).toBeTruthy();
  });

  it("never opens its own fetch-based event stream (no API key in the URL)", async () => {
    render(<AgentEventLog jobId="job-1" />);
    await waitFor(() => expect(sessions.length).toBeGreaterThan(0));
    const fetchMock = vi.mocked(fetch);
    const calls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(calls.some((u) => u.includes("/events"))).toBe(false);
  });
});
