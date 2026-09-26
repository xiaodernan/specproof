import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import FindingDetail from "./FindingDetail";
import {
  ApiError,
  apiGet,
  createFindingFeedback,
  getJobFeedback,
  type FeedbackData,
  type FeedbackReceipt,
  type FeedbackRow,
  type FindingsData,
} from "../api";

// Red-line test: the finding severity pill uses the shared severity vocabulary
// in ui/toneMap.ts and can never fall into a result tone — a value outside
// that vocabulary (including the retired INFO badge) renders 未知, never green.
//
// Only the network functions are mocked. ApiError, NETWORK_UNREACHABLE,
// getReviewer and setReviewer must stay the real ones: the component's error
// branch does `e instanceof ApiError`, and a stubbed class would make every
// instanceof false — the error path would then look "handled" while nothing
// was actually being classified.
vi.mock("../api", async (orig) => {
  const actual = await orig<typeof import("../api")>();
  return {
    ...actual,
    apiGet: vi.fn(),
    downloadCapsule: vi.fn(),
    getJobFeedback: vi.fn(),
    createFindingFeedback: vi.fn(),
  };
});

const get = vi.mocked(apiGet);
const loadFeedback = vi.mocked(getJobFeedback);
const postFeedback = vi.mocked(createFindingFeedback);

beforeEach(() => {
  get.mockReset();
  loadFeedback.mockReset();
  postFeedback.mockReset();
  localStorage.clear();
  // Default: a job nobody has reviewed yet, in the exact shape the route
  // returns ({job_id, rows, stats}).
  loadFeedback.mockResolvedValue(feedbackData([], null));
});

afterEach(() => {
  vi.clearAllMocks();
});

function payload(severity?: string, id = "f-1"): FindingsData {
  return {
    job_id: "job-1",
    findings: [
      {
        id,
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

function feedbackRow(partial: Partial<FeedbackRow> & { id: string }): FeedbackRow {
  return {
    job_id: "job-1",
    tenant_id: "t-1",
    finding_id: "f-1",
    contract_id: "AUTH-01",
    severity: "MAJOR",
    verdict: "accept",
    reason: null,
    created_by: "ana",
    created_at: "2026-09-26T02:00:00",
    ...partial,
  };
}

// acceptance_rate_pct is passed in rather than computed here, because the
// number under test is the one MySQLStore.feedback_stats returned: round(100
// * accepted / total, 1), or null when nobody voted. A helper that recomputed
// it would pass even if the page misread the field.
function feedbackData(rows: FeedbackRow[], rate: number | null): FeedbackData {
  return {
    job_id: "job-1",
    rows,
    stats: {
      job_id: "job-1",
      accepted: rows.filter((r) => r.verdict === "accept").length,
      rejected: rows.filter((r) => r.verdict === "reject").length,
      no_feedback_not_counted: true,
      acceptance_rate_pct: rate,
    },
  };
}

function receipt(state: FeedbackReceipt["state"]): FeedbackReceipt {
  return { id: "row-1", job_id: "job-1", finding_id: "f-1", verdict: "accept", state };
}

describe("FindingDetail severity pill — severity has its own tone map", () => {
  it.each([
    ["BLOCKER", "pill-bad"],
    ["MAJOR", "pill-major"],
    ["MINOR", "pill-minor"],
    ["NEEDS_CONFIRMATION", "pill-unverified"],
  ] as const)("renders %s with %s — never a green result tone", async (severity, cls) => {
    get.mockResolvedValueOnce(payload(severity));
    render(<FindingDetail jobId="job-1" findingId="f-1" />);
    const pill = await screen.findByText(severity, { selector: ".pill" });
    expect(pill.className).toBe("pill " + cls);
    expect(pill.className).not.toMatch(/pill-ok|pill-pass/);
  });

  it("renders 未知 for a severity the vocabulary does not contain", async () => {
    // INFO had its own badge until #81 proved nothing can produce it: the
    // findings ENUM has no INFO, so the badge was decoration nobody would see.
    for (const severity of ["INFO", undefined]) {
      get.mockResolvedValueOnce(payload(severity));
      const { unmount } = render(<FindingDetail jobId="job-1" findingId="f-1" />);
      const pill = await screen.findByText(/未知/, { selector: ".pill" });
      expect(pill.className).toBe("pill pill-mute");
      expect(pill.className).not.toMatch(/pill-ok|pill-pass/);
      unmount();
    }
  });

  it("explains severity in plain Chinese and localizes the metadata labels", async () => {
    const p = payload("BLOCKER");
    p.findings[0].evidence_type = "runtime_test";
    get.mockResolvedValueOnce(p);
    render(<FindingDetail jobId="job-1" findingId="f-1" />);
    // canonical token preserved, plus an actionable Chinese gloss a reviewer can act on
    expect(await screen.findByText(/阻塞问题——必须修复/)).toBeTruthy();
    expect(screen.getByText("严重程度")).toBeTruthy();
    expect(screen.getAllByText(/运行时测试/).length).toBeGreaterThan(0);
    expect(screen.getByText("问题描述")).toBeTruthy();
    // the raw English jargon headers are gone
    expect(screen.queryByText("元数据 Metadata")).toBeNull();
    expect(screen.queryByText("Evidence Type")).toBeNull();
  });
});

describe("FindingDetail 验收反馈入口 (#84) — Go/No-Go #13 needs a UI", () => {
  it("renders the acceptance rate as a percentage, not a percent of a percent", async () => {
    loadFeedback.mockResolvedValue(
      feedbackData(
        [feedbackRow({ id: "b1" }), feedbackRow({ id: "b2", verdict: "reject", created_by: "bob" })],
        50.0
      )
    );
    get.mockResolvedValueOnce(payload("MAJOR"));
    render(<FindingDetail jobId="job-1" findingId="f-1" />);

    // acceptance_rate_pct arrives ALREADY scaled (50.0 means 50%). fmtPct()
    // multiplies by 100, so routing it through fmtPct printed "5000.0%".
    expect((await screen.findByText("50.0%")).textContent).toBe("50.0%");
    const tally = await screen.findByText(/本任务计票/);
    expect(tally.textContent).toContain("接受率 50.0%");
    expect(tally.textContent).not.toMatch(/5000/);
  });

  it("answers 无法计算 — never 0% — when nobody has reviewed yet", async () => {
    loadFeedback.mockResolvedValue(feedbackData([], null));
    get.mockResolvedValueOnce(payload("MAJOR"));
    render(<FindingDetail jobId="job-1" findingId="f-1" />);

    expect((await screen.findAllByText(/无法计算/)).length).toBeGreaterThan(0);
    expect(screen.queryByText("0.0%")).toBeNull();
    expect(screen.queryByText(/0\.0%/)).toBeNull();
    // {selector: ".empty"} because the glossary tooltip carries the same
    // sentence — the empty state itself is what must not say "0%".
    expect(screen.getByText(/没有反馈不等于已接受/, { selector: ".empty" })).toBeTruthy();
    expect(screen.getByText("验收反馈", { selector: ".ui-term-label" })).toBeTruthy();
  });

  it("shows a failed feedback load as a failure, not as an empty ledger", async () => {
    loadFeedback.mockRejectedValue(
      new ApiError(503, "feedback storage unavailable", "PROVIDER_UNAVAILABLE")
    );
    get.mockResolvedValueOnce(payload("MAJOR"));
    render(<FindingDetail jobId="job-1" findingId="f-1" />);

    const box = await screen.findByText(/反馈记录加载失败/);
    expect(box.textContent).toContain("HTTP 503 · PROVIDER_UNAVAILABLE");
    // The lie this guards: "nobody voted" is what an unreadable ledger looks
    // like when the error branch is missing.
    expect(screen.queryByText(/还没有人提交过反馈/)).toBeNull();
    expect(screen.getByRole("button", { name: "重试" })).toBeTruthy();
  });

  it("tells the reviewer that a repeated verdict was not counted twice", async () => {
    localStorage.setItem("specproof_reviewer", "ana");
    postFeedback.mockResolvedValue(receipt("unchanged"));
    get.mockResolvedValueOnce(payload("MAJOR"));
    render(<FindingDetail jobId="job-1" findingId="f-1" />);

    fireEvent.click(await screen.findByRole("button", { name: "接受这条判定" }));

    expect(await screen.findByText(/本次没有重复计数/)).toBeTruthy();
    // The vote must carry the four fields the backend requires, verbatim.
    expect(postFeedback).toHaveBeenCalledWith("job-1", {
      finding_id: "f-1",
      contract_id: "AUTH-01",
      severity: "MAJOR",
      verdict: "accept",
      reason: null,
      created_by: "ana",
    });
  });

  it("shows which verdict the reviewer already has on record", async () => {
    localStorage.setItem("specproof_reviewer", "ana");
    loadFeedback.mockResolvedValue(
      feedbackData([feedbackRow({ id: "b1", verdict: "reject", reason: "证据不足" })], 0.0)
    );
    get.mockResolvedValueOnce(payload("MAJOR"));
    render(<FindingDetail jobId="job-1" findingId="f-1" />);

    const mine = await screen.findByText(/你当前的一票/);
    expect(mine.textContent).toContain("打回");
    expect(mine.textContent).toContain("证据不足");
  });

  it("refuses a rejection without a reason instead of burning a request", async () => {
    localStorage.setItem("specproof_reviewer", "ana");
    get.mockResolvedValueOnce(payload("MAJOR"));
    render(<FindingDetail jobId="job-1" findingId="f-1" />);

    fireEvent.click(await screen.findByRole("button", { name: "打回（误报/证据不足）" }));

    expect(await screen.findByText(/打回必须写理由/)).toBeTruthy();
    expect(postFeedback).not.toHaveBeenCalled();
  });

  it("does not offer buttons the backend can never record a row for", async () => {
    // findings.severity / finding_feedback.severity are one MySQL ENUM and the
    // request pattern accepts exactly those values. A severity outside them
    // (INFO, or the NONE a crashed checker carries) has nowhere to be stored,
    // so an enabled button would only buy the reviewer a 422.
    get.mockResolvedValueOnce(payload("INFO"));
    render(<FindingDetail jobId="job-1" findingId="f-1" />);

    expect((await screen.findAllByText(/不在后端可记录的值/)).length).toBeGreaterThan(0);
    const accept = (await screen.findByRole("button", {
      name: "接受这条判定",
    })) as HTMLButtonElement;
    expect(accept.disabled).toBe(true);
    fireEvent.click(accept);
    expect(postFeedback).not.toHaveBeenCalled();
  });

  it("renders no feedback form for a finding the URL did not name", async () => {
    // A fuzzy id match used to fall back to "the first finding without an id",
    // which could record a verdict against a different finding than shown.
    get.mockResolvedValueOnce(payload("MAJOR", "f-2"));
    render(<FindingDetail jobId="job-1" findingId="f-1" />);

    expect(await screen.findByText(/不存在于任务/)).toBeTruthy();
    expect(screen.queryByText("评审人标识")).toBeNull();
  });

  it("does not substitute an id-less row for the finding the URL asked for", async () => {
    // The discriminating case for that fallback: /jobs/{job}/findings can
    // return a summary-only row whose id is absent, and the old lookup handed
    // it to ANY unknown findingId — an unrelated finding rendered under
    // f-1's URL, with f-1 in the heading.
    const p = payload("MAJOR", "f-1");
    p.findings = [{ contract_id: "OTHER-01", severity: "MAJOR", description: "另一条风险" }];
    get.mockResolvedValueOnce(p);
    render(<FindingDetail jobId="job-1" findingId="f-1" />);

    expect(await screen.findByText(/不存在于任务/)).toBeTruthy();
    expect(screen.queryByText("另一条风险")).toBeNull();
    expect(screen.queryByText("评审人标识")).toBeNull();
  });
});
