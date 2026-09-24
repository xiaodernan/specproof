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

function matrixPayload(payload: Record<string, unknown>) {
  apiGetMock.mockImplementation(((path: string) => {
    if (path === "/jobs?limit=200") {
      return Promise.resolve({
        jobs: [{ id: "job-1", base_ref: "base", head_ref: "head", status: "BLOCKED" }],
      });
    }
    return Promise.resolve({
      job_id: "job-1",
      degraded: false,
      degraded_reason: null,
      ...payload,
    });
  }) as unknown as typeof apiGet);
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

  it("renders through the design-system Table with the quality density class", async () => {
    apiGetMock.mockImplementation(((path: string) => {
      if (path === "/jobs?limit=200") {
        return Promise.resolve({
          jobs: [{ id: "job-1", base_ref: "base", head_ref: "head", status: "VERIFIED" }],
        });
      }
      return Promise.resolve({
        job_id: "job-1",
        rows: [row("AUTH-01", "PASS", "ev/pass.json")],
        counts: { total: 1, passed: 1, failed: 0, unverified: 0 },
        degraded: false,
        degraded_reason: null,
      });
    }) as unknown as typeof apiGet);

    await mountAndSelect();
    await screen.findByText("AUTH-01");

    // Phase 1.9: the table must be the shared component (window class contract),
    // not a hand-written .data table — the quality page keeps its own density.
    document.querySelectorAll("table.data").forEach(() => {
      throw new Error("Matrix still renders a hand-written table.data");
    });
    const wrap = document.querySelector(".ui-table-wrap.quality-table");
    expect(wrap).toBeTruthy();
    expect(document.querySelectorAll(".ui-table-wrap").length).toBe(1);
  });
});

describe("Matrix 改前/改后 differential column", () => {
  it("shows base PASS -> head FAIL with the Chinese attribution, token kept", async () => {
    matrixPayload({
      rows: [
        {
          ...row("AUTH-01", "FAIL", "sha256:abc"),
          base_result: "PASS",
          head_result: "FAIL",
          attribution: "head",
        },
      ],
      counts: { total: 1, passed: 0, failed: 1, unverified: 0 },
    });

    await mountAndSelect();
    const cell = (await screen.findByText("AUTH-01")).closest("tr") as HTMLElement;
    expect(screen.getByText("改前 / 改后对照")).toBeTruthy();

    // DOM order: the 检查结果 pill first, then the two differential sides.
    // Each keeps its own tone class — the base PASS must not tint the row.
    const pills = within(cell).getAllByText(/^(PASS|FAIL)$/, { selector: ".pill" });
    expect(pills.map((p) => p.textContent)).toEqual(["FAIL", "PASS", "FAIL"]);
    expect(pills[0].className).toBe("pill pill-bad");
    expect(pills[1].className).toBe("pill pill-ok");
    expect(pills[2].className).toBe("pill pill-bad");
    expect(within(cell).getByText("本次变更引入 · head")).toBeTruthy();
  });

  it("never invents a side: a row without a differential says so plainly", async () => {
    matrixPayload({
      rows: [row("AUTH-02", "UNVERIFIED", "ev/unv.json")],
      counts: { total: 1, passed: 0, failed: 0, unverified: 1 },
    });

    await mountAndSelect();
    const cell = (await screen.findByText("AUTH-02")).closest("tr") as HTMLElement;

    expect(within(cell).getByText("未做改前/改后差分实验")).toBeTruthy();
    // Exactly one tone pill on the row — the 检查结果 pill — no green side.
    expect(within(cell).queryAllByText(/^(PASS|FAIL)$/, { selector: ".pill" })).toHaveLength(0);
  });

  it("an unrecognized attribution passes through instead of being renamed", async () => {
    matrixPayload({
      rows: [
        {
          ...row("AUTH-03", "FAIL", "ev/x"),
          base_result: "FAIL",
          head_result: "FAIL",
          attribution: "pre_existing",
        },
      ],
      counts: { total: 1, passed: 0, failed: 1, unverified: 0 },
    });

    await mountAndSelect();
    const cell = (await screen.findByText("AUTH-03")).closest("tr") as HTMLElement;
    expect(within(cell).getByText("pre_existing")).toBeTruthy();
  });

  it("a truncated row list states the cap and keeps the pipeline totals", async () => {
    matrixPayload({
      rows: [{ ...row("AUTH-01", "PASS", "ev/1"), base_result: "PASS", head_result: "PASS" }],
      counts: { total: 20, passed: 20, failed: 0, unverified: 0 },
      counts_source: "pipeline_summary",
      rows_total: 20,
      rows_truncated: true,
    });

    await mountAndSelect();
    expect(await screen.findByText(/仅展示前 1 条（共 20 条）/)).toBeTruthy();
  });

  it("counts-without-rows is surfaced as a contradiction, not as an empty matrix", async () => {
    matrixPayload({
      rows: [],
      counts: { total: 3, passed: 3, failed: 0, unverified: 0 },
    });

    await mountAndSelect();
    expect(await screen.findByText("有统计数字，但读不到逐条结果")).toBeTruthy();
    expect(screen.queryByText("这次验证尚无逐条结果")).toBeNull();
  });

  it("shows the pipeline's own next step, and stays silent when it has none", async () => {
    matrixPayload({
      rows: [
        {
          ...row("AUTH-01", "FAIL", "ev/1"),
          base_result: "PASS",
          head_result: "FAIL",
          attribution: "head",
          next_action: "阻断合并: 依据证据修复 Head 并重跑差分实验",
        },
        { ...row("AUTH-02", "UNVERIFIED", "ev/2") },
      ],
      counts: { total: 2, passed: 0, failed: 1, unverified: 1 },
    });

    await mountAndSelect();
    const withAction = (await screen.findByText("AUTH-01")).closest("tr") as HTMLElement;
    expect(within(withAction).getByText(/^下一步：阻断合并/)).toBeTruthy();

    const withoutAction = screen.getByText("AUTH-02").closest("tr") as HTMLElement;
    expect(within(withoutAction).queryByText(/^下一步：/)).toBeNull();
  });
});

describe("Matrix execution-surface disclosure", () => {
  it("says where the change's own tests ran, and warns when there was no sandbox", async () => {
    matrixPayload({
      rows: [
        {
          ...row("AUTH-01", "FAIL", "sha256:abc"),
          base_result: "PASS",
          head_result: "FAIL",
          attribution: "head",
          execution_surface: "local_host_no_sandbox",
        },
      ],
      counts: { total: 1, passed: 0, failed: 1, unverified: 0 },
    });

    await mountAndSelect();
    const cell = (await screen.findByText("AUTH-01")).closest("tr") as HTMLElement;

    // Visible text (not colour alone) plus the raw token for audit.
    const badge = within(cell).getByText(/本机执行 · 无沙箱/);
    expect(badge.className).toContain("tone-warn");
    expect(badge.getAttribute("title")).toBe("local_host_no_sandbox");
  });

  it("marks a container run as ok, and an unattributable run as a warning", async () => {
    matrixPayload({
      rows: [
        {
          ...row("AUTH-01", "PASS", "ev/1"),
          base_result: "PASS",
          head_result: "PASS",
          attribution: "none",
          execution_surface: "docker_sandbox",
        },
        {
          ...row("AUTH-02", "FAIL", "ev/2"),
          base_result: "PASS",
          head_result: "FAIL",
          attribution: "head",
          execution_surface: "unconfirmed",
        },
      ],
      counts: { total: 2, passed: 1, failed: 1, unverified: 0 },
    });

    await mountAndSelect();
    const sandboxed = (await screen.findByText("AUTH-01")).closest("tr") as HTMLElement;
    expect(within(sandboxed).getByText(/容器沙箱执行/).className).toContain("tone-ok");

    // "We could not tell" fails closed to a warning — never to a safe label.
    const unknown = screen.getByText("AUTH-02").closest("tr") as HTMLElement;
    const badge = within(unknown).getByText(/执行面未确认/);
    expect(badge.className).toContain("tone-warn");
  });

  it("renders no surface badge when the pipeline reported none", async () => {
    matrixPayload({
      rows: [
        {
          ...row("AUTH-01", "PASS", "ev/1"),
          base_result: "PASS",
          head_result: "PASS",
          attribution: "none",
        },
      ],
      counts: { total: 1, passed: 1, failed: 0, unverified: 0 },
    });

    await mountAndSelect();
    const cell = (await screen.findByText("AUTH-01")).closest("tr") as HTMLElement;
    // An absent surface must stay absent — no reassuring default.
    expect(cell.querySelectorAll(".quality-execution-surface")).toHaveLength(0);
  });
});

describe("Matrix: 'no differential ran' vs 'differential was inconclusive'", () => {
  it("renders the empty pair as 'not run', never as an UNVERIFIED comparison", async () => {
    // The pipeline now leaves both sides empty when nothing was compared.
    // UNVERIFIED -> UNVERIFIED would claim a comparison happened.
    matrixPayload({
      rows: [
        {
          ...row("PLAIN-01", "UNVERIFIED", ""),
          base_result: "",
          head_result: "",
          attribution: "unknown",
        },
      ],
      counts: { total: 1, passed: 0, failed: 0, unverified: 1 },
    });

    await mountAndSelect();
    const cell = (await screen.findByText("PLAIN-01")).closest("tr") as HTMLElement;
    expect(within(cell).getByText("未做改前/改后差分实验")).toBeTruthy();
    expect(within(cell).queryAllByText(/^UNVERIFIED$/, { selector: ".pill" })).toHaveLength(1);
  });

  it("still shows a genuine inconclusive comparison as two UNVERIFIED sides", async () => {
    matrixPayload({
      rows: [
        {
          ...row("FLAKY-01", "UNVERIFIED", "ev/1"),
          base_result: "UNVERIFIED",
          head_result: "UNVERIFIED",
          attribution: "unknown",
        },
      ],
      counts: { total: 1, passed: 0, failed: 0, unverified: 1 },
    });

    await mountAndSelect();
    const cell = (await screen.findByText("FLAKY-01")).closest("tr") as HTMLElement;
    expect(within(cell).queryByText("未做改前/改后差分实验")).toBeNull();
    // 检查结果 pill + the two comparison sides.
    expect(within(cell).getAllByText(/^UNVERIFIED$/, { selector: ".pill" })).toHaveLength(3);
  });

  it("keeps the observed side of a one-sided comparison and marks the other 无观测", async () => {
    matrixPayload({
      rows: [
        {
          ...row("HALF-01", "UNVERIFIED", "ev/1"),
          base_result: "PASS",
          head_result: "",
          attribution: "unknown",
        },
      ],
      counts: { total: 1, passed: 0, failed: 0, unverified: 1 },
    });

    await mountAndSelect();
    const cell = (await screen.findByText("HALF-01")).closest("tr") as HTMLElement;
    expect(within(cell).getByText("无观测")).toBeTruthy();
    expect(within(cell).getByText("PASS", { selector: ".pill" })).toBeTruthy();
  });
});
