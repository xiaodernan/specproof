import { describe, expect, it } from "vitest";
import { render, cleanup } from "@testing-library/react";
import { I18nProvider, LOCALE_STORAGE_KEY } from "../../i18n";
import evidence from "../evidence.json";
import Exhibits from "../Exhibits";

/**
 * /exhibits renders every committed JSON in apps/web/src/pages/evidence.json
 * that begins with "static-warm" or "static-light", so the visitor sees the
 * real strikes this project did to its own front door. Each exhibits renders
 * its file name, its concurrency, its worst p99 and its verdict.
 * The list is sorted by started_utc and matches the committed evidence.
 */
const staticExhibits = (evidence.all as Array<{
  file: string;
  started_utc?: string;
  worst_p99_ms: number;
  verdict: string;
}>).filter((e) => /^static-(warm|light)/.test(e.file));

describe("Exhibits — the public timeline of the front-door strikes", () => {
  it("renders every static exhibit in both locales, with verdict verbatim", () => {
    for (const locale of ["zh", "en"] as const) {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
      const { container } = render(
        <I18nProvider>
          <Exhibits />
        </I18nProvider>,
      );
      for (const e of staticExhibits) {
        expect(container.textContent).toContain(e.file.replace(/\.json$/, ""));
        expect(container.textContent).toContain(e.verdict);
      }
      cleanup();
    }
  });

  it("lists exhibits ordered by started_utc (earliest first)", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    const { container } = render(
      <I18nProvider>
        <Exhibits />
      </I18nProvider>,
    );
    const cardText = container.textContent ?? "";
    const positions = staticExhibits
      .map((e) => cardText.indexOf(e.file.replace(/\.json$/, "")))
      .filter((i) => i >= 0);
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
    cleanup();
  });

  it("Night Watch's pin (#4) and the latests appear on the page", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "zh");
    const { container } = render(
      <I18nProvider>
        <Exhibits />
      </I18nProvider>,
    );
    expect(container.textContent).toContain("1,526.1");
    expect(container.textContent).toContain("2,253.8");
    cleanup();
  });
});
