import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import AgentWizard from "../pages/AgentWizard";

// The wizard persists drafts to sessionStorage; tests use a clean slate and
// never talk to the network (the submit step is not exercised here).

function mockStorage() {
  const store = new Map<string, string>();
  const get = vi.fn((k: string) => store.get(k) ?? null);
  const set = vi.fn((k: string, v: string) => void store.set(k, v));
  const remove = vi.fn((k: string) => void store.delete(k));
  return { get, set, remove, store };
}

describe("AgentWizard", () => {
  beforeEach(() => {
    const storage = mockStorage();
    vi.stubGlobal("sessionStorage", {
      getItem: storage.get,
      setItem: storage.set,
      removeItem: storage.remove,
      key: vi.fn(() => null),
      clear: vi.fn(),
      length: 0,
    });
    vi.stubGlobal("location", { hash: "#/agent/new" });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the repo step and validates before advancing", () => {
    render(<AgentWizard step="repo" />);
    expect(screen.getByText("步骤 1/4 — 目标仓库")).toBeTruthy();
    const input = screen.getByPlaceholderText("D:\\repos\\my-service");
    fireEvent.change(input, { target: { value: "D:/repos/svc" } });
    const next = screen.getByText("下一步 Next");
    expect(next.getAttribute("href")).toBe("#/agent/new/spec");
  });

  it("keeps the next link disabled until the repo is filled", () => {
    render(<AgentWizard step="repo" />);
    const next = screen.getByText("下一步 Next");
    expect(next.getAttribute("href")).toBe("#/agent/new");
    expect(next.className).toContain("btn-disabled");
  });

  it("renders the spec step and validates the spec text", () => {
    render(<AgentWizard step="spec" />);
    const area = screen.getByPlaceholderText(/分页参数/);
    fireEvent.change(area, { target: { value: "add pagination" } });
    const next = screen.getByText("下一步 Next");
    expect(next.getAttribute("href")).toBe("#/agent/new/gates");
  });

  it("renders the gates step with all four gate checkboxes", () => {
    render(<AgentWizard step="gates" />);
    expect(screen.getByText("运行测试 run_tests")).toBeTruthy();
    expect(screen.getByText("运行 Lint run_lint")).toBeTruthy();
    expect(screen.getByText("运行类型检查 run_typecheck")).toBeTruthy();
    expect(screen.getByText("最终门禁需人工审批 require_gate")).toBeTruthy();
  });

  it("renders the review step showing the composed spec", () => {
    render(<AgentWizard step="review" />);
    expect(screen.getByText("步骤 4/4 — 审阅并提交")).toBeTruthy();
    expect(screen.getByText(/SPECPROOF WIZARD CONSTRAINTS/)).toBeTruthy();
  });
});
