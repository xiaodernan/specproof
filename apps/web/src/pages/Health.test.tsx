import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import Health from "./Health";
import { apiGet, HealthData } from "../api";
import { buildHealthCategories } from "./healthCategories";

// The health page polls /api/v1/health; tests mock the api client and never
// touch the network. The five-category view must render for every payload
// shape, and missing fields must read 未知 UNKNOWN instead of a guess.

vi.mock("../api", () => ({ apiGet: vi.fn() }));
const apiGetMock = vi.mocked(apiGet);

beforeEach(() => {
  apiGetMock.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

function stateOf(id: string): string {
  return screen.getByTestId(id).getAttribute("data-state") || "";
}

describe("Health five-category rendering", () => {
  it("renders all five categories for a full healthy payload", async () => {
    apiGetMock.mockResolvedValueOnce({
      status: "ok",
      degraded: false,
      checks: {
        mysql: { ok: true, latency_ms: 1.2, error: null },
        redis: { ok: true, latency_ms: 0.8, error: null },
      },
    } as HealthData);
    render(<Health />);
    await screen.findByTestId("health-category-service");

    expect(stateOf("health-category-service")).toBe("ok");
    expect(screen.getByTestId("health-category-service").textContent).toContain("可达");
    expect(screen.getByTestId("health-category-deps").textContent).toContain("2 / 2 可达");
    expect(stateOf("health-category-deps")).toBe("ok");
    // The /health contract carries no capability inventory: honest 未知.
    expect(stateOf("health-category-capabilities")).toBe("unknown");
    expect(screen.getByTestId("health-category-capabilities").textContent).toContain("未知");
    expect(screen.getByTestId("health-category-degraded").textContent).toContain("正常");
    expect(stateOf("health-category-degraded")).toBe("ok");
    expect(screen.getByTestId("health-category-data").textContent).toContain("可查询");
    expect(stateOf("health-category-data")).toBe("ok");
  });

  it("shows partial dependencies and degradation honestly", async () => {
    apiGetMock.mockResolvedValueOnce({
      status: "degraded",
      degraded: true,
      degraded_reasons: ["redis: connection refused"],
      checks: {
        mysql: { ok: true, latency_ms: 1.1, error: null },
        redis: { ok: false, latency_ms: 2.0, error: "conn refused" },
      },
    } as HealthData);
    render(<Health />);
    await screen.findByTestId("health-category-service");

    expect(stateOf("health-category-deps")).toBe("warn");
    expect(screen.getByTestId("health-category-deps").textContent).toContain("1 / 2 可达");
    expect(screen.getByTestId("health-category-deps").textContent).toContain("redis");
    expect(screen.getByTestId("health-category-degraded").textContent).toContain("降级中");
    expect(screen.getByTestId("health-category-degraded").textContent).toContain(
      "redis: connection refused"
    );
    expect(screen.getByTestId("health-category-data").textContent).toContain("可查询");
  });

  it("renders 未知 for every absent field (missing-fields payload)", async () => {
    apiGetMock.mockResolvedValueOnce({ status: "ok" } as HealthData);
    render(<Health />);
    await screen.findByTestId("health-category-service");

    // Only service reachability is knowable from this payload.
    expect(stateOf("health-category-service")).toBe("ok");
    for (const key of ["deps", "capabilities", "degraded", "data"]) {
      expect(stateOf("health-category-" + key)).toBe("unknown");
      expect(screen.getByTestId("health-category-" + key).textContent).toContain("未知");
    }
  });

  it("reports the capability inventory when the payload carries one", async () => {
    apiGetMock.mockResolvedValueOnce({
      status: "ok",
      degraded: false,
      capabilities: ["chat", "json_output", "streaming"],
      checks: { mysql: { ok: true, latency_ms: 1.0, error: null } },
    } as HealthData);
    render(<Health />);
    await screen.findByTestId("health-category-service");

    expect(screen.getByTestId("health-category-capabilities").textContent).toContain(
      "3 项已上报"
    );
    expect(stateOf("health-category-capabilities")).toBe("ok");
  });

  it("marks the service unreachable and the rest unknown when the probe fails", async () => {
    apiGetMock.mockRejectedValueOnce(new Error("ECONNREFUSED"));
    render(<Health />);
    await screen.findByTestId("errorbox");

    expect(stateOf("health-category-service")).toBe("bad");
    expect(screen.getByTestId("health-category-service").textContent).toContain("不可达");
    expect(screen.getByTestId("health-category-service").textContent).toContain(
      "ECONNREFUSED"
    );
    for (const key of ["deps", "capabilities", "degraded", "data"]) {
      expect(stateOf("health-category-" + key)).toBe("unknown");
    }
  });

  it("marks the data store not queryable when the mysql probe is down", async () => {
    apiGetMock.mockResolvedValueOnce({
      status: "degraded",
      degraded: true,
      checks: { mysql: { ok: false, latency_ms: 9.9, error: "connect timeout" } },
    } as HealthData);
    render(<Health />);
    await screen.findByTestId("health-category-service");

    expect(stateOf("health-category-data")).toBe("bad");
    expect(screen.getByTestId("health-category-data").textContent).toContain(
      "不可查询"
    );
    expect(screen.getByTestId("health-category-data").textContent).toContain(
      "connect timeout"
    );
  });
});

describe("buildHealthCategories", () => {
  it("always returns exactly the five categories in order", () => {
    const rows = buildHealthCategories(null, null);
    expect(rows.map((r) => r.key)).toEqual([
      "service",
      "deps",
      "capabilities",
      "degraded",
      "data",
    ]);
    expect(rows[0].state).toBe("unknown");
  });

  it("derives service from the error when no payload arrived", () => {
    const rows = buildHealthCategories(null, "boom");
    expect(rows[0].state).toBe("bad");
    expect(rows[0].detail).toBe("boom");
  });

  it("treats an empty checks map as unknown, not healthy", () => {
    const rows = buildHealthCategories({ status: "ok", checks: {} }, null);
    expect(rows[1].state).toBe("unknown");
    expect(rows[4].state).toBe("unknown");
  });
});
