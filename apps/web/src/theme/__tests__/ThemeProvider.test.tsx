import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { ThemeProvider, THEME_STORAGE_KEY, useTheme } from "../ThemeProvider";

function mockStorage() {
  const store = new Map<string, string>();
  return {
    getItem: vi.fn((k: string) => store.get(k) ?? null),
    setItem: vi.fn((k: string, v: string) => void store.set(k, v)),
    removeItem: vi.fn((k: string) => void store.delete(k)),
    key: vi.fn(() => null),
    clear: vi.fn(() => void store.clear()),
    length: 0,
  };
}

function mockMatchMedia(initial: boolean) {
  let matches = initial;
  const listeners = new Set<(e: { matches: boolean }) => void>();
  const mql = {
    get matches() {
      return matches;
    },
    media: "(prefers-color-scheme: light)",
    addEventListener: vi.fn(
      (_type: string, cb: (e: { matches: boolean }) => void) => {
        listeners.add(cb);
      }
    ),
    removeEventListener: vi.fn(
      (_type: string, cb: (e: { matches: boolean }) => void) => {
        listeners.delete(cb);
      }
    ),
  };
  return {
    set: (v: boolean) => {
      matches = v;
      listeners.forEach((cb) => cb({ matches: v }));
    },
    mql,
  };
}

function Probe(): JSX.Element {
  const { resolved, theme, toggle, setTheme } = useTheme();
  return (
    <div>
      <span data-testid="resolved">{resolved}</span>
      <span data-testid="theme">{theme}</span>
      <button onClick={toggle}>toggle</button>
      <button onClick={() => setTheme("system")}>system</button>
    </div>
  );
}

beforeEach(() => {
  vi.stubGlobal("localStorage", mockStorage());
  vi.stubGlobal("sessionStorage", mockStorage());
});

afterEach(() => {
  document.documentElement.removeAttribute("data-theme");
  vi.unstubAllGlobals();
});

describe("ThemeProvider", () => {
  it("resolves the OS preference when nothing is stored", () => {
    const mm = mockMatchMedia(false); // OS prefers dark
    vi.stubGlobal("matchMedia", vi.fn(() => mm.mql));
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>
    );
    expect(screen.getByTestId("theme").textContent).toBe("system");
    expect(screen.getByTestId("resolved").textContent).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("follows OS changes while the preference is system", () => {
    const mm = mockMatchMedia(false);
    vi.stubGlobal("matchMedia", vi.fn(() => mm.mql));
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>
    );
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    act(() => {
      mm.set(true); // OS switches to light
    });
    expect(screen.getByTestId("resolved").textContent).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("persists an explicit toggle and restores it on remount", () => {
    const mm = mockMatchMedia(false);
    vi.stubGlobal("matchMedia", vi.fn(() => mm.mql));
    const storage = window.localStorage;

    const first = render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>
    );
    fireEvent.click(screen.getByText("toggle"));
    expect(screen.getByTestId("resolved").textContent).toBe("light");
    expect(storage.getItem(THEME_STORAGE_KEY)).toBe("light");

    first.unmount();
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>
    );
    expect(screen.getByTestId("theme").textContent).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("stores the system preference explicitly and keeps following the OS", () => {
    const mm = mockMatchMedia(false);
    vi.stubGlobal("matchMedia", vi.fn(() => mm.mql));
    const storage = window.localStorage;

    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>
    );
    fireEvent.click(screen.getByRole("button", { name: "system" }));
    expect(storage.getItem(THEME_STORAGE_KEY)).toBe("system");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    act(() => {
      mm.set(true);
    });
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });
});
