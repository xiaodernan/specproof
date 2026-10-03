// Phase 3.4 stitching: the verification detail page surfaces the AI-dev jobs
// recorded for the same repository path. The honest states matter as much as
// the happy path: a failed list read must never render as "no tasks", and
// the panel states its join key (exact repo path, in-process metadata) so a
// reader cannot mistake it for a foreign-key relation.
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, cleanup } from "@testing-library/react";

import { SameRepoCraftPanel } from "../SameRepoCraftPanel";
import type { AgentJobSummary } from "../../api";

function job(overrides: Partial<AgentJobSummary> = {}): AgentJobSummary {
  return {
    id: "cj-1",
    task_name: "修复登录超时",
    repo_path: "D:/work/demo",
    status: "COMPLETED",
    plan_steps: 3,
    events_count: 12,
    approvals_count: 1,
    created_at: "2026-09-28T10:00:00Z",
    updated_at: "2026-09-28T10:05:00Z",
    ...overrides,
  };
}

const api = vi.hoisted(() => ({ listAgentJobs: vi.fn() }));

vi.mock("../../api", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../api")>();
  return { ...original, listAgentJobs: api.listAgentJobs };
});

beforeEach(() => {
  api.listAgentJobs.mockReset();
});
afterEach(cleanup);

describe("SameRepoCraftPanel — same-repo AI-dev jobs on the verify page", () => {
  it("lists matching jobs and links to the agent console", async () => {
    api.listAgentJobs.mockResolvedValue({
      jobs: [
        job(),
        job({ id: "cj-2", task_name: "别的仓库", repo_path: "D:/work/other" }),
      ],
      count: 2,
      filter: { status: null },
    });

    render(<SameRepoCraftPanel repoPath="D:/work/demo" />);

    const row = await screen.findByText("修复登录超时");
    expect(row.getAttribute("href")).toBe("#/agent/jobs/cj-1");
    // The other repo's job is filtered out client-side.
    expect(screen.queryByText("别的仓库")).toBeNull();
    // The status uses the console vocabulary, raw token in the title.
    expect(screen.getByText(/已完成/).getAttribute("title")).toBe("COMPLETED");
  });

  it("states the join key instead of implying a foreign-key relation", async () => {
    api.listAgentJobs.mockResolvedValue({ jobs: [], count: 0, filter: { status: null } });
    render(<SameRepoCraftPanel repoPath="D:/work/demo" />);
    await screen.findByText("同仓库路径下没有开发任务记录。");
    const note = screen.getByText(/按仓库路径精确匹配/);
    expect(note.textContent).toContain("没有外键");
  });

  it("renders a failed read as a failure, never as an empty result", async () => {
    api.listAgentJobs.mockRejectedValue(new Error("503"));
    render(<SameRepoCraftPanel repoPath="D:/work/demo" />);
    await screen.findByText(/暂时无法读取（请求失败）/);
    expect(screen.queryByText("同仓库路径下没有开发任务记录。")).toBeNull();
  });

  it("renders nothing when the job has no repo path to match on", () => {
    const { container } = render(<SameRepoCraftPanel repoPath={null} />);
    expect(container.querySelector(".ui-panel")).toBeNull();
    expect(api.listAgentJobs).not.toHaveBeenCalled();
  });

  it("normalizes trailing separators when matching", async () => {
    api.listAgentJobs.mockResolvedValue({
      jobs: [job({ repo_path: "D:/work/demo/" })],
      count: 1,
      filter: { status: null },
    });
    render(<SameRepoCraftPanel repoPath="D:\\work\\demo" />);
    await waitFor(() => expect(screen.getByText("修复登录超时")).toBeTruthy());
  });
});
