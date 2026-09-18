import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { type AgentEvent, type AgentJob, openAgentEventStream } from "../../api";
import AgentToolStream from "../pages/AgentToolStream";

vi.mock("../../api", async (original) => ({
  ...(await original<typeof import("../../api")>()), openAgentEventStream: vi.fn(),
}));

const job: AgentJob = {
  id: "job-1", task_name: "pagination", repo_path: "D:/repos/svc", spec_text: "add pagination",
  status: "EXECUTING", plan: null, result: null, worker_id: "w1", events_count: 2,
  approvals_count: 0, created_at: "2026-08-18T00:00:00Z", updated_at: "2026-08-18T00:00:00Z",
  progress: { percent: 42, current_step: 0, message: "working", updated_at: "2026-08-18T00:00:00Z" },
};

describe("AgentToolStream", () => {
  const sessions: { id: string; event: (e: AgentEvent) => void; done: () => void; close: ReturnType<typeof vi.fn> }[] = [];
  beforeEach(() => {
    sessions.length = 0;
    vi.mocked(openAgentEventStream).mockImplementation((id, event, _state, done) => {
      const close = vi.fn(); sessions.push({ id, event, done: done!, close }); return close;
    });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => ({
      ok: true, status: 200, json: async () => ({ job: { ...job, id: String(url).split("/").pop() } }),
    })));
  });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

  it("renders actual model content and deduplicates replayed events", async () => {
    render(<AgentToolStream jobId="job-1" />);
    await waitFor(() => expect(screen.getByRole("log")).toBeTruthy());
    const event: AgentEvent = { seq: 1, type: "model_output", at: job.created_at, data: { text: "Reading the repository" } };
    act(() => { sessions[0].event(event); sessions[0].event(event); });
    expect(screen.getByRole("log").textContent).toContain("Reading the repository");
    expect(screen.getByRole("log").textContent?.match(/Reading the repository/g)).toHaveLength(1);
    expect(screen.getByText("Reading the repository")).toBeTruthy();
  });

  it("clears old events and disconnects when navigating to another job", async () => {
    const view = render(<AgentToolStream jobId="job-1" />);
    await waitFor(() => expect(screen.getByRole("log")).toBeTruthy());
    act(() => sessions[0].event({ seq: 20, type: "model_output", at: job.created_at, data: { text: "old output" } }));
    view.rerender(<AgentToolStream jobId="job-2" />);
    await waitFor(() => expect(sessions).toHaveLength(2));
    await waitFor(() => expect(screen.getByRole("log")).toBeTruthy());
    expect(sessions[0].close).toHaveBeenCalledOnce();
    expect(screen.queryByText("old output")).toBeNull();
    act(() => sessions[1].event({ seq: 1, type: "model_output", at: job.created_at, data: { text: "new output" } }));
    expect(screen.getByRole("log").textContent).toContain("new output");
    act(() => sessions[1].done());
    expect(screen.getByText(/已结束 closed/)).toBeTruthy();
  });
});
