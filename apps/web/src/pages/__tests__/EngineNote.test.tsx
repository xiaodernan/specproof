import { describe, expect, it } from "vitest";
import { render, cleanup, within } from "@testing-library/react";
import { I18nProvider, LOCALE_STORAGE_KEY } from "../../i18n";
import Engine from "../Engine";

/**
 * The engine page's footer carries a closing note telling the reader that a
 * second LLM lane (aizzz/gpt-6.1-terra) exists and that the wkapi-era tally
 * on the page never folds it in. The two lanes must never be mixed; this
 * test welds that note to the page — both locales — so a future copy edit
 * cannot silently drop it or merge the accounts.
 */
describe("Engine — the awizzz note under the honesty footer", () => {
  it("keeps the weekly account wkapi-era and points the aizzz lane elsewhere (zh/en)", () => {
    for (const locale of ["zh", "en"] as const) {
      localStorage.setItem(LOCALE_STORAGE_KEY, locale);
      const { container } = render(
        <I18nProvider>
          <Engine />
        </I18nProvider>,
      );
      const note = container.querySelector(".engine-honesty-note") as HTMLElement;
      expect(note, `note missing in ${locale}`).toBeTruthy();
      expect(note.textContent).toContain("aizzz");
      expect(note.textContent).toContain("provider_smoke 7/7");
      if (locale === "zh") {
        expect(note.textContent).toContain("不混账");
      } else {
        expect(note.textContent).toContain("never folded");
      }
      cleanup();
    }
  });
});
