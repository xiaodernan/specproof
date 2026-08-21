import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import AgentToolStream from "../pages/AgentToolStream";
import { AgentEvent, AgentJob } from "../../api";

const job: AgentJob = {
  id: "job-1",
  task_name: "pagination",
  repo_path: "D:/repos/svc",
  spec_text: "add pagination",
  status: "EXECUTING",
  plan: null,
  progress: { percent: 42, current_step: 0, message: "working", updated_at: "2026-08-18T00:00:00Z" },
  result: null,
  worker_id: "w1",
  created_at: "2026-08-18T00:00:00Z",
  updated_at: "2026-08-18T00:00:00Z",
  events_count: 2,
  approvals_count: 0,
};

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  listeners: Record<string, ((ev: { data: string }) => void)[]> = {};
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, cb: (ev: { data: string }) => void) {
    (this.listeners[type] ||= []).push(cb);
  }

  close() {
    this.closed = true;
  }
}

function stubFetch() {
  const fetchMock = vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => ({ job }),
  }));
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("EventSource", FakeEventSource);
  return fetchMock;
}

describe("AgentToolStream", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("opens the SSE stream and renders tool events as they arrive", async () => {
    stubFetch();
    render(<AgentToolStream jobId="job-1" />);
    await waitFor(() => expect(FakeEventSource.instances.length).toBe(1));
    const es = FakeEventSource.instances[0];
    expect(es.url).toContain("/agent/jobs/job-1/events?key=");

    const toolCall: AgentEvent = {
      seq: 2,
      type: "tool_call",
      at: "2026-08-18T00:00:00Z",
      data: { tool: "read_file", call_id: "c1", arguments: { path: "src/svc.py" } },
    };
    const result: AgentEvent = {
      seq: 3,
      type: "tool_result",
      at: "2026-08-18T00:00:01Z",
      data: { call_id: "c1", ok: true },
    };
    es.onopen?.();
    es.onmessage?.({ data: JSON.stringify(toolCall) });
    es.onmessage?.({ data: JSON.stringify(result) });

    await waitFor(() => {
      const consoleEl = screen.getByLabelText("agent-tool-stream");
      expect(consoleEl.textContent).toContain('#2 [工具调用 Tool call] → {"tool":"read_file"');
      expect(consoleEl.textContent).toContain("#3 [工具结果 Tool result]");
    });
  });

  it("closes the stream when the done event fires", async () => {
    stubFetch();
    render(<AgentToolStream jobId="job-1" />);
    await waitFor(() => expect(FakeEventSource.instances.length).toBe(1));
    const es = FakeEventSource.instances[0];
    (es.listeners["done"] || [])[0]?.({ data: JSON.stringify({ job_id: "job-1" }) });
    await waitFor(() => expect(es.closed).toBe(true));
    expect(screen.getByText(/· 已结束 closed/)).toBeTruthy();
  });
});
