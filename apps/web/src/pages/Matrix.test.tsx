import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import Matrix from "./Matrix";
import { apiGet } from "../api";

// Red-line test: result and evidence status render separately with their own
// tone map (PASS green / FAIL red / UNVERIFIED amber / DEGRADED neutral;
// unknown -> 未知, never green). The .pill class contract (W39 e2e) is kept.

vi.mock("../api", () => ({ apiGet: vi.fn() }));
const apiGetMock = vi.mocked(apiGet);

beforeEach(() => {
  apiGetMock.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

function row(id: string, result: string, evidence_ref: string) {
  return {
    contract_id_str: id,
    requirement_text: "需求 " + id,
    checker_type: "junit",
    expected_behavior: "401",
    result,
    evidence_ref,
  };
}

async function mountAndSelect() {
  render(<Matrix />);
  await screen.findByRole("option", { name: /job-1/ });
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "job-1" } });
}

describe("Matrix result/evidence pills — status has its own tone map", () => {
  it("renders PASS green, FAIL red, UNVERIFIED amber, DEGRADED neutral, unknown 未知", async () => {
    apiGetMock.mockImplementation(((path: string) => {
      if (path === "/jobs?limit=200") {
        return Promise.resolve({
          jobs: [{ id: "job-1", base_ref: "base", head_ref: "head", status: "VERIFIED" }],
        });
      }
      return Promise.resolve({
        job_id: "job-1",
        rows: [
          row("AUTH-01", "PASS", "ev/pass.json"),
          row("AUTH-02", "FAIL", ""),
          row("AUTH-03", "UNVERIFIED", "ev/unv.json"),
          row("AUTH-04", "DEGRADED", ""),
          row("AUTH-05", "", ""),
        ],
        counts: { total: 5, passed: 1, failed: 1, unverified: 1 },
        degraded: false,
        degraded_reason: null,
      });
    }) as unknown as typeof apiGet);

    await mountAndSelect();

    // W39 contract: every status pill keeps the base .pill class.
    const passPill = await screen.findByText("PASS", { selector: ".pill" });
    expect(passPill.className).toBe("pill pill-ok");
    expect(screen.getByText("FAIL", { selector: ".pill" }).className).toBe("pill pill-bad");
    expect(screen.getByText("UNVERIFIED", { selector: ".pill" }).className).toBe(
      "pill pill-unverified"
    );
    expect(screen.getByText("DEGRADED", { selector: ".pill" }).className).toBe(
      "pill pill-mute"
    );

    const unknownPill = screen.getByText("未知 UNKNOWN", { selector: ".pill" });
    expect(unknownPill.className).toBe("pill pill-mute");
    expect(unknownPill.className).not.toMatch(/pill-ok|pill-pass/);
  });

  it("renders evidence status separately: missing refs are honest 未知, never green", async () => {
    apiGetMock.mockImplementation(((path: string) => {
      if (path === "/jobs?limit=200") {
        return Promise.resolve({
          jobs: [{ id: "job-1", base_ref: "base", head_ref: "head", status: "VERIFIED" }],
        });
      }
      return Promise.resolve({
        job_id: "job-1",
        rows: [row("AUTH-01", "PASS", "ev/pass.json"), row("AUTH-02", "FAIL", "")],
        counts: { total: 2, passed: 1, failed: 1, unverified: 0 },
        degraded: false,
        degraded_reason: null,
      });
    }) as unknown as typeof apiGet);

    await mountAndSelect();

    const a01 = (await screen.findByText("AUTH-01")).closest("tr") as HTMLElement;
    expect(within(a01).getByText("ev/pass.json")).toBeTruthy();

    const a02 = screen.getByText("AUTH-02").closest("tr") as HTMLElement;
    const missing = within(a02).getByText("未知");
    expect(missing.className).toBe("mono muted");
    expect(missing.className).not.toMatch(/pill-ok|pill-pass/);
  });
});
