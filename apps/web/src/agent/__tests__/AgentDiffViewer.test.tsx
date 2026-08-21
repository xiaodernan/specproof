import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import AgentDiffViewer from "../pages/AgentDiffViewer";
import { AgentDiff, AgentJob } from "../../api";

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
  events_count: 4,
  approvals_count: 1,
};

const diff: AgentDiff = {
  job_id: "job-1",
  mode: "unified",
  stats: { files_changed: 1, insertions: 1, deletions: 1 },
  files: [
    {
      path: "src/svc.py",
      status: "modified",
      insertions: 1,
      deletions: 1,
      hunks: [
        {
          old_start: 1,
          old_count: 2,
          new_start: 1,
          new_count: 2,
          lines: [
            { type: "context", old_no: 1, new_no: 1, text: "def main():" },
            { type: "del", old_no: 2, new_no: null, text: "    old" },
            { type: "add", old_no: null, new_no: 2, text: "    new" },
          ],
        },
      ],
    },
  ],
  generated_at: "2026-08-18T00:00:00Z",
};

function stubFetch(diffOverride?: AgentDiff) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method || "GET";
    if (url.includes("/diff")) {
      return {
        ok: true,
        status: 200,
        json: async () => diffOverride ?? diff,
      };
    }
    if (method === "GET") {
      return { ok: true, status: 200, json: async () => ({ job }) };
    }
    return { ok: false, status: 405, json: async () => ({ detail: "nope" }) };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("AgentDiffViewer", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders unified diff rows with add/del markers", async () => {
    stubFetch();
    render(<AgentDiffViewer jobId="job-1" mode="unified" />);
    await waitFor(() => expect(screen.getByText("src/svc.py")).toBeTruthy());
    expect(screen.getByText("- old")).toBeTruthy();
    expect(screen.getByText("+ new")).toBeTruthy();
    expect(screen.getAllByText("+1").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("-1").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("@@ -1,2 +1,2 @@")).toBeTruthy();
  });

  it("renders split mode with two side-by-side cells", async () => {
    stubFetch({ ...diff, mode: "split" });
    render(<AgentDiffViewer jobId="job-1" mode="split" />);
    await waitFor(() => expect(screen.getByText("src/svc.py")).toBeTruthy());
    // split mode: deleted text only on the left cell, added only on the right
    const oldCells = screen.getAllByText("old");
    const newCells = screen.getAllByText("new");
    expect(oldCells.length).toBe(1);
    expect(newCells.length).toBe(1);
  });

  it("shows the honest empty state when no bundle exists", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/diff")) {
        return {
          ok: false,
          status: 404,
          json: async () => ({
            detail: "Agent job job-1 has no change bundle yet",
            error: { code: "EVIDENCE_UNVERIFIED", message: "x", request_id: "r" },
            schema_version: 1,
          }),
        };
      }
      return { ok: true, status: 200, json: async () => ({ job }) };
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentDiffViewer jobId="job-1" mode="unified" />);
    await waitFor(() =>
      expect(screen.getByText(/尚未产生 bundle/)).toBeTruthy()
    );
  });
});
