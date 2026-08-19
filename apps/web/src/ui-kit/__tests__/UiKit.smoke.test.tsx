import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ThemeProvider } from "../../theme/ThemeProvider";
import { ToastProvider } from "../../ui/Toast";
import UiKit from "../UiKit";

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

describe("UiKit style guide (smoke)", () => {
  it("renders the full style guide in the dark theme without crashing", () => {
    render(
      <ThemeProvider>
        <ToastProvider>
          <UiKit />
        </ToastProvider>
      </ThemeProvider>
    );
    expect(screen.getByText("SpecProof 设计系统 ·", { exact: false })).toBeTruthy();
    expect(screen.getAllByText(/Aurora/).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: /色彩 Colors/ })).toBeTruthy();
    expect(screen.getByRole("heading", { name: /按钮 Buttons/ })).toBeTruthy();
    expect(screen.getByRole("heading", { name: /数据展示 Data display/ })).toBeTruthy();
    expect(screen.getByRole("heading", { name: /反馈 Feedback/ })).toBeTruthy();
    // The preview dashboard is mounted and shows its data.
    expect(screen.getAllByText(/差分验证 ·/).length).toBeGreaterThan(0);
    expect(screen.getByText("SP-2481")).toBeTruthy();
  });

  it("switches to the light theme and keeps rendering", () => {
    render(
      <ThemeProvider>
        <ToastProvider>
          <UiKit />
        </ToastProvider>
      </ThemeProvider>
    );
    fireEvent.click(screen.getByRole("button", { name: /浅色/ }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(screen.getByRole("heading", { name: /色彩 Colors/ })).toBeTruthy();
    // Fire a toast to prove the provider + viewport are wired up.
    fireEvent.click(screen.getByRole("button", { name: "成功" }));
    expect(screen.getByText("验证通过")).toBeTruthy();
  });
});
