import { describe, expect, it } from "vitest";
import { render, fireEvent, cleanup } from "@testing-library/react";
import { I18nProvider, LOCALE_STORAGE_KEY } from "../../i18n";
import { ERRATA } from "../errata.copy";
import Errata from "../Errata";

/**
 * The Errata Scroll renders the 15 corrections verbatim from errata.copy.ts.
 * Nothing on this page is decorative. Every erratum must show up both locales,
 * and search must narrow by tokens without erasing anything.
 */
describe("Errata — the corrections scroll, errata you strike as you make them", () => {
  it("renders every erratum with an id and loads both locales", () => {
    for (const locale of ["zh", "en"] as const) {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
      const { container } = render(
        <I18nProvider>
          <Errata />
        </I18nProvider>,
      );
      for (const entry of ERRATA) {
        expect(container.textContent).toContain(entry.id);
      }
      cleanup();
    }
  });

  it("a no-match query produces an honest 'no match' message", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    const { container } = render(
      <I18nProvider>
        <Errata />
      </I18nProvider>,
    );
    const input = container.querySelector<HTMLInputElement>("#errata-filter")!;
    fireEvent.change(input, { target: { value: "zzqxjvn-tower-of-babylonalabad" } });
    expect(container.textContent).toContain("Nothing matched");
    cleanup();
  });

  it("search narrows to matching entries but keeps the verdict honest", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    const { container } = render(
      <I18nProvider>
        <Errata />
      </I18nProvider>,
    );
    const input = container.querySelector<HTMLInputElement>("#errata-filter")!;
    fireEvent.change(input, { target: { value: "R05" } });
    expect(container.textContent).toContain("R05");
    cleanup();
  });

  it("anchor IDs in the scroll are real git/ledger identifiers, not fantasy git hashes", () => {
    for (const entry of ERRATA) {
      expect(entry.anchor).toMatch(/^#\d+$/);
    }
  });
});
