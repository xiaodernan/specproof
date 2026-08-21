import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "specproof_theme";
export const THEME_ATTRIBUTE = "data-theme";

export interface ThemeContextValue {
  theme: ThemePreference;
  resolved: ResolvedTheme;
  setTheme: (theme: ThemePreference) => void;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function systemTheme(): ResolvedTheme {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return "dark";
  }
  return window.matchMedia("(prefers-color-scheme: light)").matches
    ? "light"
    : "dark";
}

function readStored(): ThemePreference {
  try {
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (raw === "light" || raw === "dark" || raw === "system") return raw;
  } catch {
    // storage unavailable; fall through to system preference
  }
  return "system";
}

/** Applies a resolved theme to <html data-theme>. Exported for tests and
 *  for the no-flash inline bootstrap in index.html (which mirrors this). */
export function applyTheme(resolved: ResolvedTheme): void {
  document.documentElement.setAttribute(THEME_ATTRIBUTE, resolved);
}

export function ThemeProvider(props: { children?: ReactNode }): JSX.Element {
  const [theme, setThemeState] = useState<ThemePreference>(readStored);
  const [system, setSystem] = useState<ResolvedTheme>(systemTheme);

  // Follow OS-level changes while the preference is "system".
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mql = window.matchMedia("(prefers-color-scheme: light)");
    if (typeof mql.addEventListener !== "function") return;
    const onChange = (e: MediaQueryListEvent) =>
      setSystem(e.matches ? "light" : "dark");
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  const resolved: ResolvedTheme = theme === "system" ? system : theme;

  useEffect(() => {
    applyTheme(resolved);
  }, [resolved]);

  const setTheme = useCallback((next: ThemePreference) => {
    setThemeState(next);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // storage unavailable; preference lives for the session only
    }
  }, []);

  const toggle = useCallback(() => {
    setTheme(resolved === "dark" ? "light" : "dark");
  }, [resolved, setTheme]);

  const value = useMemo(
    () => ({ theme, resolved, setTheme, toggle }),
    [theme, resolved, setTheme, toggle]
  );

  return <ThemeContext.Provider value={value}>{props.children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme must be used inside <ThemeProvider>");
  }
  return ctx;
}
