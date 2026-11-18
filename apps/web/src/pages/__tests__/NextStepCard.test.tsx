import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, waitFor } from "@testing-library/react";
import NextStepCard from "../NextStepCard";
import { I18nProvider, LOCALE_STORAGE_KEY } from "../../i18n";

/**
 * NextStepCard — the model reads this repo's own shipped numbers and
 * proposes the next arc; failures surface one honest line, never a verdict.
 */
function stubFetchOk(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => ({
        advice: "LIVE-READING: ledger 1,799 · worldbook 204 · library 203 — the next strike is a consistency check, not a verdict.",
        model: "gpt-6.1-terra",
        model_latency_ms: 8100,
        evidence_packet_chars: 190,
        usage: null,
        cached: false,
      }),
      headers: new Headers(),
    })),
  );
}

function stubFetchFailing(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: false,
      status: 503,
      statusText: "Service Unavailable",
      json: async () => ({ detail: "模型暂时不可用" }),
      headers: new Headers(),
    })),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.removeItem(LOCALE_STORAGE_KEY);
});

describe("NextStepCard", () => {
  it("renders the model's reading with the model + latency + packet meta", async () => {
    stubFetchOk();
    const { container } = render(
      <I18nProvider>
        <NextStepCard />
      </I18nProvider>,
    );
    await waitFor(() => expect(container.textContent).toContain("LIVE-READING"));
    expect(container.textContent).toContain("gpt-6.1-terra");
    expect(container.textContent).toContain("不是判决");
    cleanup();
  });

  it("renders one honest line when the lane fails — never a verdict, never ghost prose", async () => {
    stubFetchFailing();
    const { container } = render(
      <I18nProvider>
        <NextStepCard />
      </I18nProvider>,
    );
    await waitFor(() => expect(container.textContent).toContain("模型暂时没回答"));
    expect(container.textContent).toContain("裁决");
    expect(container.textContent).not.toContain("gpt-6.1-terra");
    cleanup();
  });

  it("English mode renders the en strings, never zh", async () => {
    stubFetchOk();
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    const { container } = render(
      <I18nProvider>
        <NextStepCard />
      </I18nProvider>,
    );
    await waitFor(() => expect(container.textContent).toContain("LIVE-READING"));
    expect(container.textContent).toContain("THE NEXT DOOR THIS BOOK MIGHT KNOCK");
    expect(container.textContent).toContain("compass, not a scythe");
    cleanup();
  });
});
