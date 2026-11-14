import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { I18nProvider, LOCALE_STORAGE_KEY } from "../../i18n";
import Lexicon from "../Lexicon";

describe("Iron Lexicon page", () => {
  it("renders all fourteen entries in Chinese by default", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "zh");
    render(
      <I18nProvider>
        <Lexicon />
      </I18nProvider>,
    );
    expect(screen.getByText("铁证词典", { exact: false })).toBeTruthy();
    expect(screen.getByText("capsule")).toBeTruthy();
    expect(screen.getByText("differential execution")).toBeTruthy();
    expect(screen.getByText("wkapi.pro")).toBeTruthy();
    // 14 entries render (they are collapsed by default, labels still visible)
    expect(screen.getByText("ledger")).toBeTruthy();
  });

  it("renders fully in English when the locale says so", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    render(
      <I18nProvider>
        <Lexicon />
      </I18nProvider>,
    );
    expect(screen.getAllByText("Iron Lexicon", { exact: false }).length).toBeGreaterThan(0);
    expect(screen.queryByText("铁证词典", { exact: false })).toBeNull();
  });
});
