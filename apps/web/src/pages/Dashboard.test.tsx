import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import Dashboard from "./Dashboard";
import { apiGet } from "../api";

// Red-line: the landing workspace must not dump raw English degrade reasons.
// Known subsystems (redis/mysql) become an actionable Chinese gloss while the
// raw string stays in the <li> title for audit; an unrecognized reason is
// passed through verbatim — we never fabricate a meaning we don't know.

vi.mock("../api", () => ({ apiGet: vi.fn() }));
const apiGetMock = vi.mocked(apiGet);

beforeEach(() => {
  apiGetMock.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

function degradedPayload(reasons: string[]) {
  return {
    jobs: { total: 0, by_status: {} },
    recent_jobs: [],
    timeline_24h: [],
    timeline_timezone: "UTC",
    degraded: true,
    degraded_reasons: reasons,
  };
}

describe("Dashboard degraded reasons", () => {
  it("glosses a known redis reason into Chinese and keeps raw in title", async () => {
    apiGetMock.mockResolvedValue(
      degradedPayload(["redis: Connection refused"]) as unknown as never
    );
    render(<Dashboard />);
    const gloss = await screen.findByText(/实时进度缓存（Redis）暂时不可用/);
    expect(gloss.getAttribute("title")).toBe("redis: Connection refused");
    // The raw English must not be the visible label anymore.
    expect(gloss.textContent).not.toMatch(/Connection refused/);
  });

  it("passes an unknown reason through verbatim (never fabricates)", async () => {
    const weird = "vectorstore: shard 7 lagging";
    apiGetMock.mockResolvedValue(degradedPayload([weird]) as unknown as never);
    render(<Dashboard />);
    const li = await screen.findByText(weird);
    expect(li.getAttribute("title")).toBe(weird);
  });
});
