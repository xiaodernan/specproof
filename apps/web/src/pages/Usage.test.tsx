import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import Usage from "./Usage";
import { getLlmUsageSummary, type LlmUsageSummary } from "../api";

// The 缓存健康 page polls /api/v1/llm/usage/summary; tests mock the api
// client and never touch the network. The page must render every honest
// shape: a healthy window with numbers, a window whose gateway never
// reported cache data (null hit rate), an empty ledger, and a dead
// endpoint — without inventing a single figure.

vi.mock("../api", () => ({ getLlmUsageSummary: vi.fn() }));
const summaryMock = vi.mocked(getLlmUsageSummary);

const SUMMARY: LlmUsageSummary = {
  window_hours: 24,
  generated_at: "2026-11-14T04:10:00+00:00",
  calls: 27,
  errors: 1,
  error_rate: 0.037,
  streamed_ratio: 0.963,
  prompt_tokens: 118_000,
  completion_tokens: 24_000,
  total_tokens: 142_000,
  cached_tokens: 96_000,
  hit_rate: 0.8136,
  hit_basis_calls: 22,
  latency_p50_ms: 7_300,
  latency_p95_ms: 41_000,
  by_kind: [
    { kind: "draft", calls: 14, prompt_tokens: 70_000, cached_tokens: 60_000, hit_rate: 0.8571 },
    { kind: "diagnose", calls: 9, prompt_tokens: 39_000, cached_tokens: 36_000, hit_rate: 0.9231 },
    { kind: "(untyped)", calls: 4, prompt_tokens: 9_000, cached_tokens: 0, hit_rate: null },
  ],
  trend: [
    { bucket_start: "2026-11-14T00:00:00+00:00", calls: 2, prompt_tokens: 10_000, cached_tokens: 8_000, hit_rate: 0.8 },
    { bucket_start: "2026-11-14T01:00:00+00:00", calls: 4, prompt_tokens: 20_000, cached_tokens: 17_000, hit_rate: 0.85 },
    { bucket_start: "2026-11-14T02:00:00+00:00", calls: 6, prompt_tokens: 30_000, cached_tokens: 22_000, hit_rate: null },
    { bucket_start: "2026-11-14T03:00:00+00:00", calls: 15, prompt_tokens: 58_000, cached_tokens: 49_000, hit_rate: 0.8448 },
  ],
};

const EMPTY: LlmUsageSummary = {
  ...SUMMARY,
  calls: 0,
  errors: 0,
  error_rate: null,
  streamed_ratio: null,
  prompt_tokens: 0,
  completion_tokens: 0,
  total_tokens: 0,
  cached_tokens: 0,
  hit_rate: null,
  hit_basis_calls: 0,
  latency_p50_ms: null,
  latency_p95_ms: null,
  by_kind: [],
  trend: [],
};

beforeEach(() => {
  summaryMock.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("Usage / 缓存健康", () => {
  it("renders the honest stat row for a healthy window", async () => {
    summaryMock.mockResolvedValueOnce(SUMMARY);
    render(<Usage />);

    expect(await screen.findByText("81.4%")).not.toBeNull();
    expect(screen.getByText("96.0k")).not.toBeNull();
    expect(screen.getByText("142.0k")).not.toBeNull();
    expect(screen.getByText("27")).not.toBeNull();
    expect(screen.getByText("7.3 s")).not.toBeNull();
    expect(screen.getByText("41.0 s")).not.toBeNull();
    // 诚实口径：命中率只覆盖上报 cached 的 22/27 次调用
    const note = screen.getByText(/命中率只统计/);
    expect(note.textContent).toContain("22");
    expect(note.textContent).toContain("27");
    expect(screen.getByText(/stream=true/).textContent).toContain("96.3%");
  });

  it("switches the ledger window when a chip is pressed", async () => {
    summaryMock.mockResolvedValue(SUMMARY);
    render(<Usage />);
    await screen.findByText("81.4%");
    summaryMock.mockClear();

    fireEvent.click(screen.getByRole("button", { name: "7 天" }));
    expect(summaryMock).toHaveBeenCalledWith(168);

    fireEvent.click(screen.getByRole("button", { name: "30 天" }));
    expect(summaryMock).toHaveBeenCalledWith(720);
  });

  it("renders the by-kind table and keeps unreported-cache rows honest", async () => {
    summaryMock.mockResolvedValueOnce(SUMMARY);
    render(<Usage />);

    expect(await screen.findByText("draft")).not.toBeNull();
    expect(screen.getByText("85.7%")).not.toBeNull();
    expect(screen.getByText("92.3%")).not.toBeNull();
    // hit_rate null 渲染为「—」，不是 0.0%
    expect(screen.getByText("(untyped)")).not.toBeNull();
  });

  it("draws one trend bar per bucket and breaks the hit-rate line at null points", async () => {
    summaryMock.mockResolvedValueOnce(SUMMARY);
    const { container } = render(<Usage />);

    expect(await screen.findByText("81.4%")).not.toBeNull();
    const bars = container.querySelectorAll(".usage-trend-bar");
    expect(bars.length).toBe(4);
    const dots = container.querySelectorAll(".usage-trend-dot");
    expect(dots.length).toBe(3); // 一个 null 命中点 → 折线断档、不画假点
  });

  it("renders an honest empty ledger without fabricating numbers", async () => {
    summaryMock.mockResolvedValueOnce(EMPTY);
    render(<Usage />);

    expect(await screen.findByText(/账本尚无记录/)).not.toBeNull();
    expect(screen.queryByText("81.4%")).toBeNull();
  });

  it("shows a Degraded panel and no invented stats when the ledger endpoint is down", async () => {
    summaryMock.mockRejectedValueOnce(new Error("boom"));
    render(<Usage />);

    expect(await screen.findByText(/不伪造任何数据/)).not.toBeNull();
    expect(screen.queryByText("81.4%")).toBeNull();
  });
});
