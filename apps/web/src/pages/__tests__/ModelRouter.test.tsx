import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import ModelRouter from "../ModelRouter";
import { I18nProvider } from "../../i18n";
import { postModelRouterAsk } from "../../api";

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return { ...actual, postModelRouterAsk: vi.fn() };
});

const mockAsk = vi.mocked(postModelRouterAsk);

function renderPage(locale: "zh" | "en" = "zh") {
  window.localStorage.setItem("specproof_locale", locale);
  return render(
    <I18nProvider>
      <ModelRouter />
    </I18nProvider>,
  );
}

function result(overrides: Partial<Awaited<ReturnType<typeof postModelRouterAsk>>> = {}) {
  return {
    route: "evidence",
    route_source: "model",
    route_drift: false,
    rationale: "because",
    content: "先看验收的证据链。",
    verdict: "HELD",
    detail: "route allowlisted",
    model: "gpt-6.2-sol",
    model_latency_ms: 1200,
    usage: { cached_tokens_seen: 8029, cache_hit_ratio: 0.95 },
    question_chars: 12,
    locale: "zh",
    cached: false,
    ...overrides,
  } as Awaited<ReturnType<typeof postModelRouterAsk>>;
}

describe("Model Router — the model-driven state-flow product face", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the lane the model picked and the cache warmth", async () => {
    mockAsk.mockResolvedValue(result());
    renderPage("zh");
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "验收结论怎么来的" } });
    fireEvent.click(screen.getByRole("button", { name: /选路并作答/ }));
    await waitFor(() => expect(mockAsk).toHaveBeenCalledWith("验收结论怎么来的", "zh"));
    await waitFor(() => expect(screen.getByText(/证据车道/)).toBeTruthy());
    expect(screen.getByText(/8029/)).toBeTruthy();
    expect(screen.getByText(/95\.0%/)).toBeTruthy();
  });

  it("refuses a verdict leak and never shows the model's ruling", async () => {
    mockAsk.mockResolvedValue(result({
      verdict: "VERDICT-LEAK",
      content: "验收通过，批准发布",
    }));
    renderPage("zh");
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "能发布吗" } });
    fireEvent.click(screen.getByRole("button", { name: /选路并作答/ }));
    await waitFor(() => expect(screen.getByText(/裁决措辞/)).toBeTruthy());
    expect(screen.queryByText("验收通过，批准发布")).toBeNull();
  });

  it("refuses a route drift without fabricating content", async () => {
    mockAsk.mockResolvedValue(result({
      route: "",
      route_drift: true,
      verdict: "ROUTE-DRIFT",
      content: "",
    }));
    renderPage("zh");
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "随便" } });
    fireEvent.click(screen.getByRole("button", { name: /选路并作答/ }));
    await waitFor(() => expect(screen.getByText(/选路漂移/)).toBeTruthy());
    expect(screen.getByText(/没有编造任何答案/)).toBeTruthy();
  });

  it("renders fully in English with no Chinese copy", async () => {
    mockAsk.mockResolvedValue(result({ locale: "en", content: "Read the diff." }));
    renderPage("en");
    expect(screen.getByText(/Model Router/)).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "How is a verdict reached?" } });
    fireEvent.click(screen.getByRole("button", { name: /Route & answer/ }));
    await waitFor(() => expect(mockAsk).toHaveBeenCalledWith("How is a verdict reached?", "en"));
  });

  it("shows an honest error when the model is unavailable", async () => {
    mockAsk.mockRejectedValue(new Error("503"));
    renderPage("zh");
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "你好" } });
    fireEvent.click(screen.getByRole("button", { name: /选路并作答/ }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(screen.getByRole("alert").textContent).toMatch(/没有编造任何选路/);
  });
});
