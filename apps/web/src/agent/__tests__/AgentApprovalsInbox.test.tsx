import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import AgentApprovalsInbox from "../pages/AgentApprovalsInbox";
import { AgentApproval, AgentJobSummary } from "../../api";

const jobs: AgentJobSummary[] = [
  {
    id: "j1",
    task_name: "task-one",
    repo_path: "D:/r1",
    status: "EXECUTING",
    plan_steps: 2,
    events_count: 3,
    approvals_count: 1,
    created_at: "2026-08-18T00:00:00Z",
    updated_at: "2026-08-18T00:00:00Z",
  },
  {
    id: "j2",
    task_name: "task-two",
    repo_path: "D:/r2",
    status: "COMPLETED",
    plan_steps: 1,
    events_count: 5,
    approvals_count: 2,
    created_at: "2026-08-18T00:00:00Z",
    updated_at: "2026-08-18T00:00:00Z",
  },
];

const a1: AgentApproval = {
  id: "a1",
  job_id: "j1",
  target: "plan",
  step_index: null,
  decision: "approve",
  note: "LGTM",
  actor: "console",
  created_at: "2026-08-18T10:00:00+00:00",
};
const a2: AgentApproval = {
  id: "a2",
  job_id: "j2",
  target: "gate",
  step_index: null,
  decision: "reject",
  note: "tests red",
  actor: "console",
  created_at: "2026-08-18T11:00:00+00:00",
};

function stubFetch() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/agent/jobs")) {
      return { ok: true, status: 200, json: async () => ({ jobs, count: 2 }) };
    }
    if (url.includes("/agent/jobs/j1/approvals")) {
      return { ok: true, status: 200, json: async () => ({ approvals: [a1], count: 1 }) };
    }
    if (url.includes("/agent/jobs/j2/approvals")) {
      return { ok: true, status: 200, json: async () => ({ approvals: [a2], count: 1 }) };
    }
    return { ok: false, status: 404, json: async () => ({ detail: "nope" }) };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("AgentApprovalsInbox", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("aggregates approvals across jobs", async () => {
    stubFetch();
    render(<AgentApprovalsInbox />);
    await waitFor(() => expect(screen.getByText("审批 (2 / 2)")).toBeTruthy());
    expect(screen.getByText("APPROVE 批准")).toBeTruthy();
    expect(screen.getByText("REJECT 拒绝")).toBeTruthy();
    expect(screen.getByText("tests red")).toBeTruthy();
    expect(screen.getByText("LGTM")).toBeTruthy();
  });

  it("filters by decision", async () => {
    stubFetch();
    render(<AgentApprovalsInbox />);
    await waitFor(() => expect(screen.getByText("审批 (2 / 2)")).toBeTruthy());
    const select = screen.getByRole("combobox");
    (select as HTMLSelectElement).value = "reject";
    select.dispatchEvent(new Event("change", { bubbles: true }));
    await waitFor(() => expect(screen.getByText("审批 (1 / 2)")).toBeTruthy());
    expect(screen.getByText("REJECT 拒绝")).toBeTruthy();
    expect(screen.queryByText("APPROVE 批准")).toBeNull();
  });
});
