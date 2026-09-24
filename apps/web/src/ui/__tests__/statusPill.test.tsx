import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusPill, statusLabel, STATUS_LABELS } from "../StatusPill";

// The 执行阶段 timeline puts a StatusPill on every stage row, so the two
// strings the worker writes there ("completed", "failed", plus
// "waiting_for_provider" for a parked job) are user-visible copy — not
// internal tokens someone may leave untranslated.

describe("StatusPill — stage-row statuses", () => {
  it("glosses a completed stage instead of printing the raw token", () => {
    expect(statusLabel("completed")).toBe("已完成");
    expect(STATUS_LABELS.COMPLETED).toBeTruthy();
  });

  it("keeps the canonical token visible in the title while showing Chinese", () => {
    render(<StatusPill status="waiting_for_provider" />);
    const pill = screen.getByText("等待模型服务");
    expect(pill.getAttribute("title")).toBe("WAITING_FOR_PROVIDER");
  });

  it("tones a parked job as still running, not as finished", () => {
    render(<StatusPill status="waiting_for_provider" />);
    expect(screen.getByText("等待模型服务").className).toContain("pill-run");
    render(<StatusPill status="failed" />);
    expect(screen.getByText("执行失败").className).toContain("pill-bad");
  });

  it("passes an unknown status through verbatim", () => {
    expect(statusLabel("some_future_status")).toBe("SOME_FUTURE_STATUS");
  });
});
