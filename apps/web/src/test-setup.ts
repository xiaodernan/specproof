import { beforeEach } from "vitest";

// Default every test to the zh locale.
//
// The glosses in `ui/toneMap.ts` and `ui/errorHints.ts` resolve through the
// i18n table, and jsdom's navigator.language is en-US by default — most
// legacy assertions were written against the Chinese copy. A test that needs
// the English locale can set `window.localStorage.setItem("specproof_locale",
// "en")` inside itself; anything else gets zh.
beforeEach(() => {
  window.localStorage.setItem("specproof_locale", "zh");
});
