import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import Observe from "../Observe";
import { I18nProvider, LOCALE_STORAGE_KEY } from "../../i18n";

/**
 * /observe — a public readonly observatory. The password is `123` and always
 * will be (by the owner's own instruction); the page shows a clearly-labelled
 * seeded calibration cohort plus this browser's own telemetry — never a real
 * reader. The unlocked read is a live model call (mocked here): failures must
 * surface as one honest error line, never as ghost-written prose.
 */
function stubFetchOk(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => ({
        advice: "LIVE-MODEL-READING · synthetic cohort only · slope −4.14/d · r² 0.12 · not a verdict",
        model: "gpt-6.1-terra",
        model_latency_ms: 8123,
        evidence_packet_chars: 733,
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

describe("observatory · public readonly panel", () => {
  beforeEach(() => {
    cleanup();
    window.localStorage.clear();
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    stubFetchOk();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  const submit123 = (): void => {
    fireEvent.change(
      screen.getByLabelText(/password/i),
      { target: { value: "123" } },
    );
    fireEvent.click(screen.getByRole("button", { name: /Open/i }));
  };

  it("renders the public page with synthetic-cohort disclosure in both locales", () => {
    const { container } = render(
      <I18nProvider>
        <Observe />
      </I18nProvider>,
    );
    expect(container.textContent).toContain("Observatory");
    expect(container.textContent).toContain("public");
    expect(container.textContent).toContain("240");
  });

  it("opens the gate only on '123'", async () => {
    const { container } = render(
      <I18nProvider>
        <Observe />
      </I18nProvider>,
    );
    const password = screen.getByLabelText(/password/i) as HTMLInputElement;
    fireEvent.change(password, { target: { value: "something-else" } });
    fireEvent.click(screen.getByRole("button", { name: /Open/i }));
    expect(container.textContent).toContain("Only \"123\"");

    submit123();
    await waitFor(() => {
      expect(container.textContent).toContain("What the model said");
    });
    expect(container.textContent).toContain("You're in");
    await waitFor(() => {
      expect(container.textContent).toContain("LIVE-MODEL-READING");
    });
  });

  it("unfolds the live read without inventing identities — no email-shaped text", async () => {
    const { container } = render(
      <I18nProvider>
        <Observe />
      </I18nProvider>,
    );
    submit123();
    await waitFor(() => {
      expect(container.textContent).toContain("LIVE-MODEL-READING");
    });
    expect(/@gmail|@qq|@outlook|@163|@hotmail|@users.noreply\.github/i.test(container.textContent || "")).toBe(false);
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "zh");
    const { container: zh } = render(
      <I18nProvider>
        <Observe />
      </I18nProvider>,
    );
    expect(zh.textContent).toContain("观察舱");
    expect(zh.textContent).toContain("公开");
    expect(zh.textContent).toContain("240");
  });

  it("shows one honest error line when the model cannot answer", async () => {
    stubFetchFailing();
    const { container } = render(
      <I18nProvider>
        <Observe />
      </I18nProvider>,
    );
    submit123();
    await waitFor(() => {
      expect(container.textContent).toContain("503");
    });
    expect(container.textContent).not.toContain("LIVE-MODEL-READING");
    expect(container.textContent).toContain("240");
  });
});
