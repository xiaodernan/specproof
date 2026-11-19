import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { I18nProvider, LOCALE_STORAGE_KEY } from "../../i18n";
import RecentKnocks from "../RecentKnocks";
import chronicle from "../chronicle.json";

const entries = chronicle as unknown as Array<{ n: number; t: string; s: string }>;

describe("RecentKnocks", () => {
  it("shows exactly the ten freshest ledger volumes, newest first", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    render(
      <I18nProvider>
        <RecentKnocks />
      </I18nProvider>,
    );
    const expected = [...entries].sort((a, b) => b.n - a.n).slice(0, 10);
    expect(screen.getAllByRole("heading", { level: 2 }).length).toBe(10);
    // The freshest entry must be rendered and first.
    expect(document.querySelector(".recent-knock-title")?.textContent).toBe(expected[0].t);
    // Each card renders its own #n marker.
    expect(screen.getByText(`#${expected[0].n}`)).toBeTruthy();
  });

  it("renders Chinese heading under zh locale", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "zh");
    render(
      <I18nProvider>
        <RecentKnocks />
      </I18nProvider>,
    );
    expect(screen.getByText("最近敲门")).toBeTruthy();
  });

  it("links to the full chronicle", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    render(
      <I18nProvider>
        <RecentKnocks />
      </I18nProvider>,
    );
    const link = screen.getByRole("link", { name: /read the whole book/i });
    expect(link.getAttribute("href")).toBe("#/chronicle");
  });

  it("prints the ledger total from data, never an invented count", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    const { container } = render(
      <I18nProvider>
        <RecentKnocks />
      </I18nProvider>,
    );
    expect(container.textContent).toContain(String(entries.length));
  });
});
