import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import Eval from "./Eval";
import { apiGet, ApiError } from "../api";

// Red-line: the evaluation report must gloss the raw PASS/MISS/FALSE_POSITIVE
// verdict enum and the severity enum (keeping the English token for audit),
// and — critically — must NOT mislabel a real read failure as "the report
// doesn't exist". A 404 is an honest empty; a 5xx/network error is a failure
// with a retry affordance.

vi.mock("../api", async (orig) => {
  const actual = await orig<typeof import("../api")>();
  return { ...actual, apiGet: vi.fn() };
});
const apiGetMock = vi.mocked(apiGet);

beforeEach(() => apiGetMock.mockReset());
afterEach(() => vi.clearAllMocks());

function payload(overrides: object = {}) {
  return {
    source: "docs/eval/eval-report.results.json",
    modified_at: "2026-09-20T00:00:00Z",
    report: {
      precision: 90,
      recall: 80,
      f1: 84.6,
      total_cases: 2,
      should_detect: 1,
      false_positives: 1,
      cases: [
        { case: "att-01", verdict: "PASS", should_detect: true, expected_severity: "MAJOR", expected_contract: "AUTH-01" },
        { case: "att-08", verdict: "FALSE_POSITIVE", should_detect: false, expected_severity: "" },
      ],
    },
    ...overrides,
  };
}

describe("Eval verdict + severity gloss", () => {
  it("renders the verdict token with a Chinese gloss and keeps raw in title", async () => {
    apiGetMock.mockResolvedValue(payload() as never);
    render(<Eval />);
    const fp = await screen.findByText(/FALSE_POSITIVE/);
    expect(fp.getAttribute("title")).toBe("FALSE_POSITIVE");
    expect(fp.textContent).toContain("误报");
    const pass = screen.getByText("PASS · 判定正确");
    expect(pass.getAttribute("title")).toBe("PASS");
  });

  it("renders expected_severity as a toned pill with a hint, empty as dash", async () => {
    apiGetMock.mockResolvedValue(payload() as never);
    render(<Eval />);
    const major = await screen.findByText("MAJOR", { selector: ".pill" });
    expect(major.getAttribute("title")).toContain("重要问题");
    // The empty-severity row must not fabricate a pill.
    expect(screen.queryAllByText("MAJOR", { selector: ".pill" }).length).toBe(1);
  });

  it("passes an unrecognized verdict through verbatim (never fabricates)", async () => {
    apiGetMock.mockResolvedValue(
      payload({
        report: {
          cases: [{ case: "x", verdict: "WEIRD_STATE", should_detect: true }],
        },
      }) as never
    );
    render(<Eval />);
    const cell = await screen.findByText(/WEIRD_STATE/);
    // No gloss appended for an unknown token; the raw value stands alone.
    expect(cell.textContent).toBe("WEIRD_STATE");
  });
});

describe("Eval null metrics (no vacuous 100%)", () => {
  // #51: an eval set whose positive/negative denominator is 0 has UNDEFINED
  // recall/precision/f1. The API emits those as null; the cards must show an
  // em-dash placeholder, never a fabricated percentage.
  it("renders undefined metrics as a dash, not a fake rate", async () => {
    apiGetMock.mockResolvedValue(
      payload({
        report: {
          precision: null,
          recall: null,
          f1: null,
          total_cases: 0,
          should_detect: 0,
          negative_cases: 0,
          false_positives: 0,
          cases: [],
        },
      }) as never
    );
    render(<Eval />);
    const cards = await screen.findAllByText("—");
    expect(cards.length).toBeGreaterThanOrEqual(3);
    expect(screen.queryByText("100.0%")).toBeNull();
  });
});

describe("Eval error vs empty (no conflation)", () => {
  it("a 404 is an honest empty, not a failure, and offers no retry", async () => {
    apiGetMock.mockRejectedValueOnce(new ApiError(404, "not found"));
    render(<Eval />);
    expect(await screen.findByText(/尚无评测报告/)).toBeTruthy();
    expect(screen.queryByText("重新加载")).toBeNull();
  });

  it("a 5xx is a real failure with a retry, never '报告不存在'", async () => {
    apiGetMock.mockRejectedValueOnce(new ApiError(500, "boom"));
    render(<Eval />);
    expect(await screen.findByText("重新加载")).toBeTruthy();
    expect(screen.queryByText(/尚无评测报告/)).toBeNull();
  });
});
