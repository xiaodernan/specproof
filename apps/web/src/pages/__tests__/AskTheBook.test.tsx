import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { I18nProvider, LOCALE_STORAGE_KEY } from "../../i18n";
import AskTheBook from "../AskTheBook";

/**
 * 问问书 · Ask the Book — the bible answers through the model. The tests
 * pin the honest floor: it renders in both locales, the model's answer is
 * labelled model-written and never a verdict, and a broken lane surfaces
 * one honest error line — never ghosted prose.
 */
function stubFetchOk(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => ({
        answer: "LIVE-ANSWER: 世界书第零卷写着创世。不是 verdict。",
        model: "gpt-6.1-terra",
        model_latency_ms: 9817,
        usage: null,
        question_chars: 14,
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

describe("问问书 · ask the world book", () => {
  beforeEach(() => {
    cleanup();
    window.localStorage.clear();
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "zh");
    stubFetchOk();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it("renders in Chinese with the knock chips and the honest gates", () => {
    const { container } = render(
      <I18nProvider>
        <AskTheBook />
      </I18nProvider>,
    );
    expect(container.textContent).toContain("问问书");
    expect(container.textContent).toContain("问之有答");
    expect(container.querySelector(".chain-banner")).toBeTruthy(); // chain roll-call rides along
    expect(container.querySelector("#ask-the-book-input")).toBeTruthy();
    cleanup();
  });

  it("renders in English with the same two gates", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    const { container } = render(
      <I18nProvider>
        <AskTheBook />
      </I18nProvider>,
    );
    expect(container.textContent).toContain("Ask the Book");
    expect(container.textContent).toContain("an answer is not a verdict");
    expect(container.querySelector(".chain-banner")).toBeTruthy();
    cleanup();
  });

  it("answers a typed question, labels it model-written, shows the latency and model", async () => {
    const { container } = render(
      <I18nProvider>
        <AskTheBook />
      </I18nProvider>,
    );
    const input = container.querySelector<HTMLTextAreaElement>("#ask-the-book-input")!;
    fireEvent.change(input, { target: { value: "世界书从哪里开始？" } });
    fireEvent.click(screen.getByRole("button", { name: /问！|^Ask$/i }));
    await waitFor(() => expect(container.textContent).toContain("LIVE-ANSWER"));
    expect(container.textContent).toContain("gpt-6.1-terra");
    expect(container.textContent).toContain("9.8s");
    // model may never paint anything green — the footnote must travel with it
    expect(container.textContent).toContain("模型打印的话不附带裁决");
    cleanup();
  });

  it("makes the book answer instead — never a fabricated paragraph, never a model verdict", async () => {
    stubFetchFailing();
    const { container } = render(
      <I18nProvider>
        <AskTheBook />
      </I18nProvider>,
    );
    const input = container.querySelector<HTMLTextAreaElement>("#ask-the-book-input")!;
    fireEvent.change(input, { target: { value: "世界书从哪里开始？" } });
    fireEvent.click(screen.getByRole("button", { name: /问！|^Ask$/i }));
    // the lane failed → the local fallback serves the book's own text
    await waitFor(() => expect(container.textContent).toContain("书里原文"));
    expect(container.textContent).toContain("卷零 · 创世之炉");
    expect(container.textContent).toContain("离线本地");
    // the answer may never impersonate the model
    expect(container.textContent).not.toContain("模型打印的话不附带裁决");
    expect(container.textContent).not.toContain("gpt-6.1-terra");
    expect(container.querySelector(".askthebook-answer")).not.toBeNull();
    cleanup();
  });

  it("surfaces one honest error line when the lane fails AND the book has no match — no ghost paragraph", async () => {
    stubFetchFailing();
    const { container } = render(
      <I18nProvider>
        <AskTheBook />
      </I18nProvider>,
    );
    const input = container.querySelector<HTMLTextAreaElement>("#ask-the-book-input")!;
    // gibberish with no keyword overlap anywhere in the snapshot
    fireEvent.change(input, { target: { value: "zzqxy vwx qrv wvu xyz" } });
    fireEvent.click(screen.getByRole("button", { name: /问！|^Ask$/i }));
    await waitFor(() => expect(container.textContent).toContain("模型暂时没回答出来"));
    // the answer box must not be filled with fiction
    expect(container.querySelector(".askthebook-answer")).toBeNull();
    cleanup();
  });
});
