import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import Insight from "../Insight";

/**
 * Insight Deck · AI 解读 panel. Fail-closed parity with every other admin
 * panel on the deck (visible to admin/operator only). The panel shows the
 * model's interpretation with explicit "never a verdict" framing, an honest
 * error path (no fabricated advice on failure), and a cache-aware footer.
 */

const access = { checked: true, canManage: true };
vi.mock("../../identity/useIdentityAccess", () => ({
  useIdentityAccess: () => access,
}));

const advice = vi.fn();
vi.mock("../../api", async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    postInsightAdvice: (...args: unknown[]) => advice(...args),
  };
});

describe("insight deck · AI advice panel", () => {
  beforeEach(() => {
    window.localStorage.clear();
    access.checked = true;
    access.canManage = true;
    advice.mockReset();
  });

  it("renders for admins and shows the AI interpretation with verdict framing", async () => {
    advice.mockResolvedValue({
      advice: "洞察一：漏斗②掉得最狠，先修引导第一跳的文案。",
      model: "gpt-6.1-terra",
      model_latency_ms: 812,
      evidence_packet_chars: 640,
      usage: { prompt_tokens: 900, completion_tokens: 120 },
      cached: false,
    });
    const { container } = render(<Insight />);
    expect(container.querySelector(".insight-ai-panel")).not.toBeNull();
    const btn = screen.getByRole("button", { name: /让模型读一遍这块面板|Ask the model to read/i });
    fireEvent.click(btn);
    await waitFor(() => expect(container.textContent).toContain("洞察一"));
    expect(container.textContent).toContain("812");
    expect(container.textContent).toMatch(/不是判决|never a verdict/);
  });

  it("shows an honest error when the model is unavailable, never fabricated advice", async () => {
    advice.mockRejectedValue(new Error("模型暂时不可用，无法生成 AI 解读。"));
    const { container } = render(<Insight />);
    fireEvent.click(screen.getByRole("button", { name: /让模型读一遍这块面板|Ask the model to read/i }));
    await waitFor(() =>
      expect(container.querySelector(".insight-ai-error")?.textContent ?? "").toContain("模型暂时不可用"),
    );
    expect(container.querySelector(".insight-ai-text")).toBeNull();
  });

  it("does not render the panel for non-admins (fail-closed parity)", () => {
    access.canManage = false;
    const { container } = render(<Insight />);
    expect(container.querySelector(".insight-ai-panel")).toBeNull();
  });
});
