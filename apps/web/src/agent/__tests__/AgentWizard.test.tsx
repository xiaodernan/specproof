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
    expect(screen.getByText("步骤 1/3 — 目标仓库")).toBeTruthy();
    const input = screen.getByPlaceholderText("D:\\repos\\my-service");
    fireEvent.change(input, { target: { value: "D:/repos/svc" } });
    const next = screen.getByText("下一步 Next");
    expect(next.getAttribute("href")).toBe("#/agent/new/spec");
  });

  it("advertises a consistent 3-step flow with no phantom 门禁 step", () => {
    // The 门禁 step was removed (it only had a no-op 下一步), but the
    // header/panel titles still claimed "4 步 / 1-4 / 2-4". Every step
    // reference must agree on 3 steps and no "x/4" may remain. (门禁 is
    // still a legitimate pipeline concept referenced in prose — only the
    // *wizard step* was removed.)
    render(<AgentWizard step="repo" />);
    expect(screen.getByText("TASK WIZARD — 3 步: 仓库 → 需求 → 提交")).toBeTruthy();
    expect(screen.queryByText(/步骤 \d\/4/)).toBeNull();
    expect(screen.getByText("步骤 1/3 — 目标仓库")).toBeTruthy();
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
    expect(next.getAttribute("href")).toBe("#/agent/new/review");
  });

  it("renders the review step showing the composed spec", () => {
    render(<AgentWizard step="review" />);
    expect(screen.getByText("步骤 3/3 — 审阅并提交")).toBeTruthy();
    expect(screen.getByText("生成计划，审阅后执行")).toBeTruthy();
    // 预算/步数只由服务端配置决定，页面不应给出不生效的开关。
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.getByText(/你批准前不会改动仓库/)).toBeTruthy();
  });

  it("keeps the legacy gates route working by landing on review", () => {
    render(<AgentWizard step="review" />);
    expect(screen.getByText("步骤 3/3 — 审阅并提交")).toBeTruthy();
  });

  it("programmatically associates every repo-step label with its control", () => {
    // a11y: labels must be linked via htmlFor/id (not just visual adjacency)
    // so screen readers announce the field and clicking the label focuses it.
    render(<AgentWizard step="repo" />);
    expect(screen.getByLabelText("仓库路径 Repo path")).toBe(screen.getByTestId("wizard-repo"));
    expect(screen.getByLabelText("任务名称 Task name (可选)")).toBe(screen.getByTestId("wizard-task"));
    expect(screen.getByLabelText(/基线 Base ref/)).toBe(screen.getByTestId("wizard-base"));
    expect(screen.getByLabelText(/目标 Head ref/)).toBe(screen.getByTestId("wizard-head"));
    expect(screen.getByLabelText("执行模式 Execution mode")).toBe(screen.getByTestId("wizard-mode"));
  });

  it("associates the spec textarea with its label", () => {
    render(<AgentWizard step="spec" />);
    expect(screen.getByLabelText("需求规格 Spec text")).toBe(screen.getByTestId("wizard-spec"));
  });
});

describe("AgentWizard step 1 info (§14.4)", () => {
  it("shows repo/base/head/spec summary/duration/mode/permission hint", () => {
    render(<AgentWizard step="repo" />);
    expect(screen.getByTestId("wizard-repo")).toBeTruthy();
    expect(screen.getByTestId("wizard-base")).toBeTruthy();
    expect(screen.getByTestId("wizard-head")).toBeTruthy();
    expect(screen.getByTestId("wizard-spec-summary").textContent).toContain("未填写");
    expect(screen.getByTestId("wizard-duration-hint").textContent).toContain("未知");
    expect(screen.getByTestId("wizard-mode")).toBeTruthy();
    expect(screen.getByTestId("wizard-permission-hint").textContent).toContain(
      "fail-closed"
    );
  });

  it("never fabricates a duration number (honest text only)", () => {
    render(<AgentWizard step="repo" />);
    const hint = screen.getByTestId("wizard-duration-hint");
    expect(hint.textContent).not.toMatch(/\d/);
    expect(hint.textContent).toContain("无伪造数字");
  });

  it("defaults to AI execution and keeps base/head reference notes", () => {
    render(<AgentWizard step="repo" />);
    const mode = screen.getByTestId("wizard-mode") as HTMLSelectElement;
    expect(mode.value).toBe("llm");
    fireEvent.change(screen.getByTestId("wizard-base"), {
      target: { value: "main" },
    });
    fireEvent.change(screen.getByTestId("wizard-head"), {
      target: { value: "feat/x" },
    });
    expect((screen.getByTestId("wizard-base") as HTMLInputElement).value).toBe(
      "main"
    );
    expect((screen.getByTestId("wizard-head") as HTMLInputElement).value).toBe(
      "feat/x"
    );
    fireEvent.change(mode, { target: { value: "llm" } });
    expect((screen.getByTestId("wizard-mode") as HTMLSelectElement).value).toBe(
      "llm"
    );
  });
});
