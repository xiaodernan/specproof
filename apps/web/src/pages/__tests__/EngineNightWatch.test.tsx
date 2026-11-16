import { describe, expect, it } from "vitest";
import { render, cleanup } from "@testing-library/react";
import { I18nProvider, LOCALE_STORAGE_KEY } from "../../i18n";
import Engine from "../Engine";
import nightWatch from "../night_watch.json";

/**
 * The night-watch panel on /engine renders the composed StateGraph's own
 * verdict. The chain is honest by construction —
 * whatever was struck (CLEAR or CRACKED, evidence REGRESSION and nothing
 * else) must render verbatim; nothing is dressed.
 */
describe("Engine — the night watch's composite verdict panel", () => {
  it("renders the same verdict + lanes as docs/evidence/night-watch.json (zh and en)", () => {
    for (const locale of ["zh", "en"] as const) {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
      const { container } = render(
        <I18nProvider>
          <Engine />
        </I18nProvider>,
      );
      const section = container.querySelector(".engine-nightwatch") as HTMLElement;
      expect(section).toBeTruthy();
      expect(section.textContent).toContain((nightWatch as { verdict: string }).verdict);
      for (const [lane, verdict] of Object.entries((nightWatch as { lanes: Record<string, string> }).lanes)) {
        expect(section.textContent).toContain(lane);
        expect(section.textContent).toContain(verdict);
      }
      expect(container.querySelector(".engine-nightwatch-lanes")).toBeTruthy();
      cleanup();
    }
  });

  it("carries the strike timestamp from night-watch.json verbatim", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    const { container } = render(
      <I18nProvider>
        <Engine />
      </I18nProvider>,
    );
    expect(container.textContent).toContain((nightWatch as { generated_utc: string }).generated_utc);
    cleanup();
  });
});
