import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ShortcutHelp } from "../ShortcutHelp";
import { SHORTCUT_GROUPS } from "../shortcuts";

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

beforeEach(() => {
  vi.stubGlobal("localStorage", mockStorage());
  vi.stubGlobal("sessionStorage", mockStorage());
  vi.stubGlobal("matchMedia", vi.fn(() => ({
    matches: false,
    media: "(prefers-color-scheme: light)",
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })));
});

afterEach(() => {
  document.documentElement.removeAttribute("data-theme");
  vi.unstubAllGlobals();
});

function expectNoDialog(): void {
  expect(screen.queryByRole("dialog")).toBeNull();
}

describe("ShortcutHelp", () => {
  it("opens with ?, lists every wired group, and closes with Esc", () => {
    render(<ShortcutHelp />);
    expectNoDialog();

    fireEvent.keyDown(window, { key: "?" });
    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeTruthy();
    for (const group of SHORTCUT_GROUPS) {
      expect(screen.getAllByText(group.title).length).toBeGreaterThan(0);
    }
    // The focus contract: the panel takes focus so keyboard users land inside.
    expect(document.activeElement).toBe(dialog.querySelector(".ui-shortcuts-panel"));

    fireEvent.keyDown(window, { key: "Escape" });
    expectNoDialog();
  });

  it("toggles closed with the same ? that opened it", () => {
    render(<ShortcutHelp />);
    fireEvent.keyDown(window, { key: "?" });
    expect(screen.getByRole("dialog")).toBeTruthy();
    fireEvent.keyDown(window, { key: "?" });
    expectNoDialog();
  });

  it("never hijacks a ? typed into an editable target", () => {
    render(
      <>
        <input aria-label="search" />
        <ShortcutHelp />
      </>
    );
    fireEvent.keyDown(screen.getByLabelText("search"), { key: "?" });
    expectNoDialog();
  });

  it("closes when the backdrop is pressed, not when the panel is", () => {
    render(<ShortcutHelp />);
    fireEvent.keyDown(window, { key: "?" });
    const backdrop = document.querySelector(".ui-shortcuts-backdrop") as HTMLElement;
    expect(backdrop).toBeTruthy();
    fireEvent.mouseDown(backdrop);
    expectNoDialog();

    fireEvent.keyDown(window, { key: "?" });
    const panel = document.querySelector(".ui-shortcuts-panel") as HTMLElement;
    fireEvent.mouseDown(panel);
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("gives focus back to whatever was focused before it opened", () => {
    render(
      <>
        <button type="button">fallback anchor</button>
        <ShortcutHelp />
      </>
    );
    const anchor = screen.getByText("fallback anchor");
    anchor.focus();
    expect(document.activeElement).toBe(anchor);

    fireEvent.keyDown(window, { key: "?" });
    expect(document.activeElement).not.toBe(anchor);

    fireEvent.keyDown(window, { key: "Escape" });
    expect(document.activeElement).toBe(anchor);
  });

  it("every shortcut row names a key combination", () => {
    render(<ShortcutHelp />);
    fireEvent.keyDown(window, { key: "?" });
    const count = SHORTCUT_GROUPS.reduce((n, group) => n + group.items.length, 0);
    expect(document.querySelectorAll(".ui-shortcuts-row").length).toBe(count);
    expect(document.querySelectorAll(".ui-shortcuts-row .ui-kbd").length).toBeGreaterThan(count);
  });
});
