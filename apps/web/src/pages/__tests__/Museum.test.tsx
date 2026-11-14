import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { I18nProvider, LOCALE_STORAGE_KEY } from "../../i18n";
import Museum from "../Museum";

describe("Evidence Museum page", () => {
  it("renders all twelve plaques in Chinese by default", async () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "zh");
    render(
      <I18nProvider>
        <Museum />
      </I18nProvider>,
    );
    expect(screen.getByText("铁证博物馆", { exact: false })).toBeTruthy();
    expect(screen.getByText("AUTH-01 · 被抓住的一次合并")).toBeTruthy();
    expect(screen.getByText("六卷盖印，「验讫」", { exact: false })).toBeTruthy();
    // the open exhibit body renders an anchor pointing at the ledger
    expect(screen.getAllByText(/#1689/, { exact: false }).length).toBeGreaterThan(0);
  });

  it("renders fully in English when the locale says so", async () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    render(
      <I18nProvider>
        <Museum />
      </I18nProvider>,
    );
    expect(screen.getAllByText("Evidence Museum", { exact: false }).length).toBeGreaterThan(0);
    expect(screen.queryByText("铁证博物馆", { exact: false })).toBeNull();
    expect(screen.getByText("AUTH-01 · the catch")).toBeTruthy();
  });
});
