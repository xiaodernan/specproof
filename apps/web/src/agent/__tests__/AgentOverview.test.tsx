import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import AgentOverview from "../pages/AgentOverview";

describe("AgentOverview", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("does not claim there are no tasks when the list failed to load", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 500,
        headers: new Headers(),
        json: async () => ({ detail: "boom" }),
      })),
    );
    render(<AgentOverview />);
    await waitFor(() =>
      expect(screen.getByText(/任务列表暂时无法加载/)).toBeTruthy(),
    );
    expect(screen.queryByText(/暂无 Agent 任务/)).toBeNull();
  });

  it("shows the honest empty state when the list loads clean but is empty", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        headers: new Headers(),
        json: async () => ({ jobs: [], count: 0 }),
      })),
    );
    render(<AgentOverview />);
    await waitFor(() =>
      expect(screen.getByText(/暂无 Agent 任务/)).toBeTruthy(),
    );
    expect(screen.queryByText(/任务列表暂时无法加载/)).toBeNull();
  });
});
