import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import FindingDetail from "./FindingDetail";
import { apiGet, FindingsData } from "../api";

// Red-line test: the finding severity pill uses the severity tone map
// (BLOCKER red / MAJOR orange / MINOR yellow / INFO neutral) and can never
// fall into a result tone — absent severity renders 未知, never green.

vi.mock("../api", () => ({ apiGet: vi.fn(), downloadCapsule: vi.fn() }));
const apiGetMock = vi.mocked(apiGet);

beforeEach(() => {
  apiGetMock.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

function payload(severity?: string): FindingsData {
  return {
    job_id: "job-1",
    findings: [
      {
        id: "f-1",
        severity,
        contract_id: "AUTH-01",
        confidence: 0.92,
        evidence_type: "runtime_test",
        type: "regression",
        location: "SecurityConfig.java",
        description: "授权检查被移除",
      },
    ],
    count: 1,
    degraded: false,
    degraded_reason: null,
  } as FindingsData;
}

describe("FindingDetail severity pill — severity has its own tone map", () => {
  it.each([
    ["BLOCKER", "pill-bad"],
    ["MAJOR", "pill-major"],
    ["MINOR", "pill-minor"],
    ["INFO", "pill-mute"],
  ] as const)("renders %s with %s — never a green result tone", async (severity, cls) => {
    apiGetMock.mockResolvedValueOnce(payload(severity));
    render(<FindingDetail jobId="job-1" findingId="f-1" />);
    const pill = await screen.findByText(severity, { selector: ".pill" });
    expect(pill.className).toBe("pill " + cls);
    expect(pill.className).not.toMatch(/pill-ok|pill-pass/);
  });

  it("renders 未知 for a missing severity — neutral, never green", async () => {
    apiGetMock.mockResolvedValueOnce(payload(undefined));
    render(<FindingDetail jobId="job-1" findingId="f-1" />);
    const pill = await screen.findByText(/未知/, { selector: ".pill" });
    expect(pill.className).toBe("pill pill-mute");
    expect(pill.className).not.toMatch(/pill-ok|pill-pass/);
  });
});
