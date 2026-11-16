import { describe, expect, it } from "vitest";
import { render, cleanup } from "@testing-library/react";
import { I18nProvider, LOCALE_STORAGE_KEY } from "../../i18n";
import Engine from "../Engine";
import cacheWitness from "../cache_witness.json";

/**
 * The prefix-cache double-strike witness lives on /engine: two strikes of the
 * same fixed prompt, both reporting cached_tokens=4224. It is a reading, not a
 * certificate — and the page must print the numbers verbatim from the tracked
 * snapshot. This test welds (a) the witness panel into both locales, (b) the
 * stale wkapi-era copy (41 calls / 147,767 / 51.2%) permanently out of the
 * page — a regression gate so the numbers can never silently drift back.
 */
describe("Engine — the prefix-cache double-strike witness", () => {
  it("prints the witness verbatim in both locales (4224 ×2 · 95.3% · HIT)", () => {
    for (const locale of ["zh", "en"] as const) {
      localStorage.setItem(LOCALE_STORAGE_KEY, locale);
      const { container } = render(
        <I18nProvider>
          <Engine />
        </I18nProvider>,
      );
      const section = container.querySelector(".engine-witness") as HTMLElement;
      expect(section, `witness section missing in ${locale}`).toBeTruthy();
      expect(section.textContent).toContain(String(cacheWitness.cached_tokens_a));
      expect(section.textContent).toContain(String(cacheWitness.cached_tokens_b));
      expect(section.textContent).toContain("95.3");
      expect(section.textContent).toContain("HIT");
      expect(section.textContent).toContain("4224");
      cleanup();
    }
  });

  it("carries the strike timestamp from cache_witness.json (zh/en)", () => {
    for (const locale of ["zh", "en"] as const) {
      localStorage.setItem(LOCALE_STORAGE_KEY, locale);
      const { container } = render(
        <I18nProvider>
          <Engine />
        </I18nProvider>,
      );
      expect(container.textContent).toContain(cacheWitness.started_utc);
      cleanup();
    }
  });

  it("contains no stale wkapi-era bytes anywhere on the page", () => {
    for (const locale of ["zh", "en"] as const) {
      localStorage.setItem(LOCALE_STORAGE_KEY, locale);
      const { container } = render(
        <I18nProvider>
          <Engine />
        </I18nProvider>,
      );
      expect(container.textContent).not.toContain("wkapi.pro");
      expect(container.textContent).not.toContain("147,767");
      expect(container.textContent).not.toContain("51.2");
      expect(container.textContent).not.toContain("75,638");
      expect(container.textContent).not.toContain("direct 29");
      expect(container.textContent).not.toContain("policy 12");
      cleanup();
    }
  });
});
