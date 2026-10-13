// Phase 3.4 stitching: the verification detail page surfaces the AI-dev jobs
// recorded for the same repository path. Since §30.2 持久化关联 the matching
// happens server-side on the durable agent_jobs.repo_path column, so the
// panel's job is narrower and its honest states matter more, not less: the
// raw path must reach the API unmodified (normalization is the store's
// semantics now), a failed list read must never render as "no tasks", and
// the note must state the join key without implying a foreign-key relation.
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";

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
  it("asks the server to filter on the raw repo path and renders the durable matches", async () => {
    api.listAgentJobs.mockResolvedValue({
      jobs: [
        job(),
        job({ id: "cj-2", task_name: "同仓库的另一个任务", created_at: "2026-09-29T09:00:00Z" }),
      ],
      count: 2,
      filter: { status: null, repo_path: "D:/work/demo" },
    });

    render(<SameRepoCraftPanel repoPath="D:\\work\\demo" />);

    // The raw JSX-attribute path reaches the API verbatim — separator
    // normalization is the store's semantics (create + list agree on it).
    expect(api.listAgentJobs).toHaveBeenCalledWith(undefined, "D:\\\\work\\\\demo");
    expect(await screen.findByText("修复登录超时")).toBeTruthy();
    expect(screen.getByText("同仓库的另一个任务")).toBeTruthy();
    const row = screen.getByText("修复登录超时");
    expect(row.getAttribute("href")).toBe("#/agent/jobs/cj-1");
    // The status uses the console vocabulary, raw token in the title. Two rows
    // render here, so the query must not assume a single status pill.
    expect(screen.getAllByText(/已完成/)[0].getAttribute("title")).toBe("COMPLETED");
  });

  it("states the join key and the durable association instead of a foreign-key relation", async () => {
    api.listAgentJobs.mockResolvedValue({
      jobs: [],
      count: 0,
      filter: { status: null, repo_path: "D:/work/demo" },
    });
    render(<SameRepoCraftPanel repoPath="D:/work/demo" />);
    await screen.findByText("同仓库路径下没有开发任务记录。");
    const note = screen.getByText(/持久化匹配/);
    expect(note.textContent).toContain("没有外键");
    // The honest caveat: pre-column rows have no durable path to match.
    expect(note.textContent).toContain("旧记录");
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

  it("renders whatever the server returned without re-filtering client-side", async () => {
    // A row the old client-side filter would have dropped (its stored path
    // differs in case) must still show: the server already decided the match.
    api.listAgentJobs.mockResolvedValue({
      jobs: [job({ repo_path: "D:/Work/Demo" })],
      count: 1,
      filter: { status: null, repo_path: "D:/work/demo" },
    });
    render(<SameRepoCraftPanel repoPath="D:/work/demo" />);
    await screen.findByText("修复登录超时");
  });
});
