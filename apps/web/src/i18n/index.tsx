/**
 * i18n — the language layer.
 *
 * SpecProof is bilingual: every surface renders in Chinese (zh) or English
 * (en), never a mix. The rule this module enforces:
 *
 *   - a string that appears in the UI comes from ONE table (`strings.ts`);
 *   - a table has BOTH locales; a key missing in one locale is a build-time
 *     error (the parity test in `__tests__/i18n.parity.test.ts` fails), not a
 *     silent fallback to the other language — a mixed screen is the bug this
 *     module exists to prevent;
 *   - the choice persists per browser (`specproof_locale`) and the document
 *     declares `lang` accordingly, so screen readers and the browser's own
 *     hyphenation stop guessing.
 *
 * Prose that belongs to a single page (the Epic scrolls, the Tour chapters)
 * lives in that page's own locale files, not here — this table holds only
 * the strings shared by more than one surface.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type { Locale } from "./strings";

export const LOCALE_STORAGE_KEY = "specproof_locale";
export const LOCALE_ATTRIBUTE = "lang";

export interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  toggleLocale: () => void;
  t: (key: string) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function readStored(): Locale {
  try {
    const raw = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    if (raw === "zh" || raw === "en") return raw;
  } catch {
    // storage unavailable; fall through to the browser default
  }
  // The browser's own language wins when it is one we speak; otherwise zh.
  try {
    const nav = window.navigator?.language ?? "";
    if (nav.toLowerCase().startsWith("zh")) return "zh";
    if (nav.toLowerCase().startsWith("en")) return "en";
  } catch {
    // no navigator (SSR/test env)
  }
  return "zh";
}

export function applyLocale(locale: Locale): void {
  document.documentElement.setAttribute(LOCALE_ATTRIBUTE, locale === "zh" ? "zh-CN" : "en");
}

export function I18nProvider(props: { children?: ReactNode }): JSX.Element {
  const [locale, setLocaleState] = useState<Locale>(readStored);

  useEffect(() => {
    applyLocale(locale);
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, next);
    } catch {
      // storage unavailable; preference lives for the session only
    }
  }, []);

  const toggleLocale = useCallback(() => {
    setLocale(locale === "zh" ? "en" : "zh");
  }, [locale, setLocale]);

  const value = useMemo(
    () => ({ locale, setLocale, toggleLocale, t: (key: string) => translate(key, locale) }),
    [locale, setLocale, toggleLocale],
  );

  return <I18nContext.Provider value={value}>{props.children}</I18nContext.Provider>;
}

// A component rendered outside the provider (a unit test that mounts one
// page in isolation) still has to show a whole screen in ONE language —
// falling back to the default locale keeps that promise instead of
// throwing mid-render.
const FALLBACK: I18nContextValue = {
  locale: "zh",
  setLocale: () => {},
  toggleLocale: () => {},
  t: (key: string) => translate(key, "zh"),
};

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  return ctx ?? FALLBACK;
}

// Imported lazily-ish to keep this module free of a cycle: `strings.ts` has no
// imports of its own beyond the Locale type.
import { STRINGS, type Locale } from "./strings";

/**
 * Fill `{name}` placeholders in a translated sentence.
 *
 * Numbers that must appear IN a sentence (a denominator, a count) belong in
 * the template, not next to it — otherwise switching locale silently drops
 * them, which is exactly the kind of quiet data loss this module forbids.
 */
export function interp(template: string, vars: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (whole, name: string) => {
    const value = vars[name];
    return value === undefined ? whole : String(value);
  });
}

export function translate(key: string, locale: Locale): string {
  const table = STRINGS[locale] as Record<string, string>;
  const value = table[key];
  if (value === undefined) {
    // A missing key is a bug in the tables, not a runtime condition to paper
    // over: return the key itself so the screen shows what is missing.
    return key;
  }
  return value;
}
