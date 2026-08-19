import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ThemeProvider } from "../../theme/ThemeProvider";
import { CommandPalette } from "../CommandPalette";

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

let hashValue = "#/dashboard";

beforeEach(() => {
  hashValue = "#/dashboard";
  vi.stubGlobal("localStorage", mockStorage());
  vi.stubGlobal("sessionStorage", mockStorage());
  vi.stubGlobal("matchMedia", vi.fn(() => ({
    matches: false,
    media: "(prefers-color-scheme: light)",
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })));
  vi.stubGlobal("location", {
    get hash() {
      return hashValue;
    },
    set hash(v: string) {
      hashValue = v;
    },
  });
});

afterEach(() => {
  document.documentElement.removeAttribute("data-theme");
  vi.unstubAllGlobals();
});

function renderPalette(): void {
  render(
    <ThemeProvider>
      <CommandPalette />
    </ThemeProvider>
  );
}

describe("CommandPalette", () => {
  it("opens with Ctrl+K and closes with Escape", () => {
    renderPalette();
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByPlaceholderText(/搜索/)).toBeTruthy();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("filters entries and navigates with Enter", () => {
    renderPalette();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const input = screen.getByPlaceholderText(/搜索/);
    fireEvent.change(input, { target: { value: "ui-kit" } });
    expect(screen.queryByText("总览")).toBeNull();
    fireEvent.keyDown(input, { key: "Enter" });
    expect(hashValue).toBe("#/ui-kit");
  });

  it("lists every agent route", () => {
    renderPalette();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const input = screen.getByPlaceholderText(/搜索/);
    fireEvent.change(input, { target: { value: "#/agent" } });
    for (const label of ["Agent 总览", "新建任务 · 仓库", "审批收件箱", "Agent 设置"]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
  });

  it("toggles the theme through the actions entry", () => {
    renderPalette();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const input = screen.getByPlaceholderText(/搜索/);
    fireEvent.change(input, { target: { value: "主题" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });
});
