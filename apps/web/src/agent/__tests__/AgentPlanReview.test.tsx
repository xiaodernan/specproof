import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import AgentPlanReview from "../pages/AgentPlanReview";
import { AgentJob } from "../../api";

const job: AgentJob = {
  id: "job-1",
  task_name: "pagination",
  repo_path: "D:/repos/svc",
  spec_text: "add pagination",
  status: "AWAITING_APPROVAL",
  plan: {
    version: 1,
    created_at: "2026-08-18T00:00:00Z",
    steps: [
      { index: 0, title: "Locate handler", summary: "grep", status: "pending" },
      { index: 1, title: "Apply change", summary: "edit", status: "pending" },
    ],
  },
  progress: { percent: 0, current_step: 0, message: "plan drafted", updated_at: "2026-08-18T00:00:00Z" },
  result: null,
  worker_id: null,
  created_at: "2026-08-18T00:00:00Z",
  updated_at: "2026-08-18T00:00:00Z",
  events_count: 2,
  approvals_count: 0,
};

function stubFetch() {
  const calls: { url: string; body: unknown }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
    if (url.endsWith("/approve")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          approval: {
            id: "approval-1",
            job_id: "job-1",
            target: "plan",
            step_index: null,
            decision: "approve",
            note: null,
            actor: "console",
            created_at: "2026-08-18T00:00:00Z",
          },
          job: { id: "job-1", status: "EXECUTING" },
        }),
      };
    }
    return { ok: true, status: 200, json: async () => ({ job }) };
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

describe("AgentPlanReview", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the plan steps with pending status", async () => {
    stubFetch();
    render(<AgentPlanReview jobId="job-1" />);
    await waitFor(() => expect(screen.getByText("Locate handler")).toBeTruthy());
    expect(screen.getByText("Apply change")).toBeTruthy();
    expect(screen.getAllByText("待审 Pending").length).toBe(2);
  });

  it("posts a whole-plan approve decision", async () => {
    const { calls } = stubFetch();
    render(<AgentPlanReview jobId="job-1" />);
    await waitFor(() => expect(screen.getByText("批准整个计划 Approve plan")).toBeTruthy());
    fireEvent.click(screen.getByText("批准整个计划 Approve plan"));
    await waitFor(() => {
      const approveCalls = calls.filter((c) => c.url.endsWith("/approve"));
      expect(approveCalls.length).toBe(1);
      expect(approveCalls[0].body).toEqual({ decision: "approve", target: "plan", note: null });
    });
  });

  it("posts a whole-plan reject decision with a note", async () => {
    vi.stubGlobal("prompt", vi.fn(() => "rollback missing"));
    const { calls } = stubFetch();
    render(<AgentPlanReview jobId="job-1" />);
    await waitFor(() => expect(screen.getByText("拒绝计划 Reject plan")).toBeTruthy());
    fireEvent.click(screen.getByText("拒绝计划 Reject plan"));
    await waitFor(() => {
      const rejectCalls = calls.filter((c) => c.url.endsWith("/approve"));
      expect(rejectCalls.length).toBe(1);
      expect(rejectCalls[0].body).toEqual({
        decision: "reject",
        target: "plan",
        note: "rollback missing",
      });
    });
  });
});
