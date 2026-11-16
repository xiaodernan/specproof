import { describe, expect, it } from "vitest";
import { render, screen, fireEvent, cleanup, within } from "@testing-library/react";
import { I18nProvider, LOCALE_STORAGE_KEY } from "../../i18n";
import Recall from "../Recall";

/**
 * The recall page is the repo's honest retrieval lane: BM25 over
 * git-tracked JSON, no model call, no network. The tests prove the
 * contract: it renders in both locales, it ranks something useful for
 * a real query, and it never dresses results as certainty.
 */
describe("Recall — ask the iron, the iron answers", () => {
  it("renders 问铁证 in Chinese with suggestion chips and zero results at first", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "zh");
    const { container } = render(
      <I18nProvider>
        <Recall />
      </I18nProvider>,
    );
    expect(container.textContent).toContain("问铁证");
    const bannerLink = container.querySelector(".chain-banner-link") as HTMLAnchorElement;
    expect(bannerLink.getAttribute("href")).toBe("#/archive");
    expect(container.querySelectorAll(".recall-hit").length).toBe(0);
    expect(screen.getByText("court 永不缓存")).toBeTruthy();
    // the chain roll-call strip must ride along, exactly as on /chronicle
    expect(container.querySelector(".chain-banner")).toBeTruthy();
    cleanup();
  });

  it("ranks the court-cache query in Chinese: results appear, badges name the source, scores stay raw", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "zh");
    const { container } = render(
      <I18nProvider>
        <Recall />
      </I18nProvider>,
    );
    const input = container.querySelector<HTMLInputElement>("#recall-filter")!;
    fireEvent.change(input, { target: { value: "court" } });
    const hits = container.querySelectorAll(".recall-hit");
    expect(hits.length).toBeGreaterThan(0);
    expect(hits.length).toBeLessThanOrEqual(10);
    const first = hits[0] as HTMLElement;
    expect(within(first).getByText(/账本 #|更正 R/)).toBeTruthy();
    expect(within(first).getByText(/^\d+\.\d{2}$/)).toBeTruthy(); // raw BM25, two decimals
    cleanup();
  });

  it("ranks the '密码' query: the #1799 rejection of \"密码 123 全员进管理员页\" surfaces", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "zh");
    const { container } = render(
      <I18nProvider>
        <Recall />
      </I18nProvider>,
    );
    const input = container.querySelector<HTMLInputElement>("#recall-filter")!;
    fireEvent.change(input, { target: { value: "密码 123" } });
    const hits = container.querySelectorAll(".recall-hit");
    expect(hits.length).toBeGreaterThan(0);
    const texts = Array.from(hits).map((h) => h.textContent ?? "");
    expect(texts.some((t) => t.includes("1799") || t.includes("洞察"))).toBe(true);
    cleanup();
  });

  it("a section title beats a body match: 'court 永不缓存' hits the ledger with the phrase in a headline", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "zh");
    const { container } = render(
      <I18nProvider>
        <Recall />
      </I18nProvider>,
    );
    const input = container.querySelector<HTMLInputElement>("#recall-filter")!;
    fireEvent.change(input, { target: { value: "court 永不缓存" } });
    const hits = container.querySelectorAll(".recall-hit");
    expect(hits.length).toBeGreaterThan(0);
    expect(hits[0].textContent).toContain("court");
    cleanup();
  });

  it("renders fully in English — no Chinese leaks into the en lane", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    const { container } = render(
      <I18nProvider>
        <Recall />
      </I18nProvider>,
    );
    expect(container.textContent).toContain("Ask the Iron");
    expect(container.textContent).not.toContain("问铁证");
    const bannerLink = container.querySelector(".chain-banner-link") as HTMLAnchorElement;
    expect(bannerLink.getAttribute("href")).toBe("#/archive");
    cleanup();
  });

  it("a query that bites nothing shows the honest empty state — no invented hits", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    const { container } = render(
      <I18nProvider>
        <Recall />
      </I18nProvider>,
    );
    const input = container.querySelector<HTMLInputElement>("#recall-filter")!;
    fireEvent.change(input, { target: { value: "🎉🎉🎉" } });
    expect(container.querySelectorAll(".recall-hit").length).toBe(0);
    expect(container.textContent).toContain("Not one ledger line");
    cleanup();
  });
});
