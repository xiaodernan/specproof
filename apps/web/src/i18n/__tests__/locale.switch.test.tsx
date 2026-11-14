import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { I18nProvider, LOCALE_STORAGE_KEY } from "../index";
import Tour from "../../pages/Tour";
import Explorer from "../../pages/Explorer";

// The promise this module makes to a user: switching the language switches
// EVERYTHING. A screen that still shows Chinese prose after the switch is
// exactly the "中英夹杂" the product promised never to ship.
describe("locale switch", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  it("renders the tour in Chinese when the stored locale says so", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "zh");
    render(
      <I18nProvider>
        <Tour />
      </I18nProvider>,
    );
    expect(screen.getAllByText("巡览").length).toBeGreaterThan(0);
    expect(screen.getByText(/六卷：连接/)).toBeTruthy();
    expect(screen.getAllByText("盖上此卷").length).toBe(6);
  });

  it("follows the browser language when nothing is stored", () => {
    // No stored preference: the module asks the browser. jsdom reports en-US,
    // so the screen is English — and it is ALL English.
    render(
      <I18nProvider>
        <Tour />
      </I18nProvider>,
    );
    expect(screen.getAllByText("Grand Tour").length).toBeGreaterThan(0);
    expect(screen.queryByText(/六卷：连接/)).toBeNull();
  });

  it("renders the tour in English when the stored locale says so", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    render(
      <I18nProvider>
        <Tour />
      </I18nProvider>,
    );
    expect(screen.getAllByText("Grand Tour").length).toBeGreaterThan(0);
    expect(screen.getByText(/Six stations/)).toBeTruthy();
    expect(screen.getAllByText("Seal this station").length).toBe(6);
    // No Chinese prose may survive in the English edition.
    expect(screen.queryByText(/六卷：连接/)).toBeNull();
    expect(screen.queryByText("盖上此卷")).toBeNull();
  });

  it("renders the case file in English too", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    render(
      <I18nProvider>
        <Explorer />
      </I18nProvider>,
    );
    expect(screen.getAllByText("Case File", { exact: false }).length).toBeGreaterThan(0);
    // Whatever branch the page lands in (the api is not mocked here, so it
    // takes the error branch), no Chinese prose may survive an English locale.
    expect(screen.queryByText(/一份装订机与印章构成的案卷/)).toBeNull();
    expect(document.body.textContent || "").not.toMatch(/案件档案/);
  });

  it("declares the document language for the active locale", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    render(
      <I18nProvider>
        <Tour />
      </I18nProvider>,
    );
    expect(document.documentElement.getAttribute("lang")).toBe("en");
  });
});
