import { describe, expect, it } from "vitest";

import { STRINGS } from "../strings";
import { LOCALE_STORAGE_KEY, applyLocale, translate } from "../index";

// The promise of this module: a screen is never a mix of Chinese and English.
// That only holds if every key exists in BOTH locales — so the parity check
// is a build gate, not a nicety.
describe("i18n string tables", () => {
  it("every zh key exists in en and vice versa", () => {
    const zhKeys = Object.keys(STRINGS.zh).sort();
    const enKeys = Object.keys(STRINGS.en).sort();
    const missingInEn = zhKeys.filter((k) => !enKeys.includes(k));
    const missingInZh = enKeys.filter((k) => !zhKeys.includes(k));
    expect(missingInEn).toEqual([]);
    expect(missingInZh).toEqual([]);
  });

  it("no locale leaves a value empty", () => {
    for (const locale of ["zh", "en"] as const) {
      for (const [key, value] of Object.entries(STRINGS[locale])) {
        expect(value.length, `${locale}:${key}`).toBeGreaterThan(0);
      }
    }
  });

  it("the two locales really differ (a copy-paste is a bug)", () => {
    const identical = Object.keys(STRINGS.zh).filter(
      (k) => STRINGS.zh[k as keyof typeof STRINGS.zh] === STRINGS.en[k as keyof typeof STRINGS.en],
    );
    // A handful of strings legitimately match (product names like CRAFT).
    expect(identical.length).toBeLessThan(Object.keys(STRINGS.zh).length / 4);
  });

  it("an unknown key returns the key itself, never the other language", () => {
    expect(translate("no.such.key", "zh")).toBe("no.such.key");
    expect(translate("no.such.key", "en")).toBe("no.such.key");
  });

  it("applyLocale declares the document language", () => {
    applyLocale("zh");
    expect(document.documentElement.getAttribute("lang")).toBe("zh-CN");
    applyLocale("en");
    expect(document.documentElement.getAttribute("lang")).toBe("en");
  });

  it("the storage key is stable across releases", () => {
    expect(LOCALE_STORAGE_KEY).toBe("specproof_locale");
  });
});
