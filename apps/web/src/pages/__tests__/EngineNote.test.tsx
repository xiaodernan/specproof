import { describe, expect, it } from "vitest";
import { render, cleanup } from "@testing-library/react";
import { I18nProvider, LOCALE_STORAGE_KEY } from "../../i18n";
import Engine from "../Engine";

/**
 * The engine page's footer carries the honesty note. Before 2026-11-16 it
 * claimed the wkapi-era tally on this page never folded in the new
 * aizzz/gpt-6.1-terra lane — which stopped being true when the new lane's
 * rows were appended to the same .local/llm_usage.jsonl. The account was
 * rebuilt the same day: 63 rows = 46 gpt-6-sol-era + 17 aizzz. The note must
 * say the two eras are ONE ledger now, and must keep pointing the reader at
 * the untracked local file; this test welds the new claim to the page.
 */
describe("Engine — the aizzz note under the honesty footer", () => {
  it("tells the truth about the two eras sharing one ledger (zh/en)", () => {
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
      expect(note.textContent).toContain("63");
      expect(note.textContent).toContain("17");
      if (locale === "zh") {
        expect(note.textContent).toContain("两个车道的和");
      } else {
        expect(note.textContent).toContain("two eras folded");
      }
      cleanup();
    }
  });
});
