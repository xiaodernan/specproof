import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import NewVerification from "./NewVerification";
import { createVerification, prepareDemoRepo, type ApiError } from "../api";

vi.mock("../api", () => ({ createVerification: vi.fn(), prepareDemoRepo: vi.fn() }));
const create = vi.mocked(createVerification);
const prepare = vi.mocked(prepareDemoRepo);
beforeEach(() => { create.mockReset(); prepare.mockReset(); window.location.hash = "#/jobs/new"; });

function fillProject() {
  fireEvent.change(screen.getByLabelText(/Git 仓库路径/), { target: { value: "  /workspace/orders  " } });
  fireEvent.change(screen.getByLabelText(/需求文件路径/), { target: { value: " /workspace/orders/spec.md " } });
}

describe("new verification", () => {
  it("explains missing input without sending an invalid job", () => {
    render(<NewVerification />);
    fireEvent.click(screen.getByRole("button", { name: "开始验证 →" }));
    expect(screen.getByText("请填写执行服务可访问的 Git 仓库路径。")).toBeTruthy();
    expect(create).not.toHaveBeenCalled();
  });

  it("submits the documented payload and opens the accepted job", async () => {
    create.mockResolvedValue({ job_id: "job-123", status: "QUEUED" });
    render(<NewVerification />);
    fillProject();
    fireEvent.click(screen.getByRole("button", { name: "开始验证 →" }));
    await waitFor(() => expect(window.location.hash).toBe("#/jobs/job-123"));
    expect(create).toHaveBeenCalledWith({ repo_path: "/workspace/orders", spec_path: "/workspace/orders/spec.md", base_ref: "main", head_ref: "HEAD", depth: "FAST" });
  });

  it("preserves input and supports retry after a rejected submission", async () => {
    create.mockRejectedValueOnce(new Error("执行服务暂不可用"));
    create.mockResolvedValueOnce({ job_id: "retry-1", status: "QUEUED" });
    render(<NewVerification />);
    fillProject();
    fireEvent.click(screen.getByRole("button", { name: "开始验证 →" }));
    await screen.findByText(/执行服务暂不可用/);
    expect((screen.getByLabelText(/Git 仓库路径/) as HTMLInputElement).value).toContain("/workspace/orders");
    fireEvent.click(screen.getByRole("button", { name: "开始验证 →" }));
    await waitFor(() => expect(window.location.hash).toBe("#/jobs/retry-1"));
  });

  it("prefills the repo path from the ?repo= query (dev→verify hand-off)", () => {
    // The Craft result page links here with ?repo=<absolute path> so the user
    // does not have to retype it after an AI development run.
    window.location.hash = "#/jobs/new?repo=" + encodeURIComponent("/srv/repos/orders");
    render(<NewVerification />);
    expect((screen.getByLabelText(/Git 仓库路径/) as HTMLInputElement).value).toBe("/srv/repos/orders");
    // spec/base/head are not known from the craft flow; leave them for the user
    expect((screen.getByLabelText(/需求文件路径/) as HTMLInputElement).value).toBe("");
  });

  it("translates a light-mode 503 into actionable Chinese guidance", async () => {
    const err = Object.assign(new Error("Job NOT accepted — the verification job store is unavailable."), {
      status: 503, code: "PROVIDER_UNAVAILABLE",
    });
    create.mockRejectedValueOnce(err);
    render(<NewVerification />);
    fillProject();
    fireEvent.click(screen.getByRole("button", { name: "开始验证 →" }));
    await screen.findByText(/免 Docker 的轻量模式/);
    expect(screen.queryByText(/Job NOT accepted/)).toBeNull();
  });

  it("turns a raw transport failure (Failed to fetch) into a Chinese hint, not English", async () => {
    // fetch rejects with a TypeError and no status/code when the backend is
    // unreachable — the browser's English message must not leak to the user.
    create.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    render(<NewVerification />);
    fillProject();
    fireEvent.click(screen.getByRole("button", { name: "开始验证 →" }));
    await screen.findByText(/无法连接到验证服务/);
    expect(screen.queryByText(/Failed to fetch/)).toBeNull();
  });
});

// #241b: the one-click "create demo repo" button must call the backend and, on
// success, continue into the demo-fill flow without the user touching the CLI.
describe("NewVerification demo-repo creation (#241b)", () => {
  function repoInput(): HTMLInputElement {
    return screen.getByLabelText(/Git 仓库路径/) as HTMLInputElement;
  }

  it("offers a one-click create button", () => {
    render(<NewVerification />);
    expect(screen.getByRole("button", { name: "一键创建演示仓库" })).toBeTruthy();
  });

  it("creates the repo then auto-fills the demo form on success", async () => {
    prepare.mockResolvedValue({ created: true, refs: ["base", "head-v1"], message: "ok" });
    render(<NewVerification />);
    expect(repoInput().value).toBe("");
    fireEvent.click(screen.getByRole("button", { name: "一键创建演示仓库" }));
    await waitFor(() => expect(repoInput().value).toBe("demo/spring-backend"));
    expect(screen.getByText(/已创建演示仓库/)).toBeTruthy();
    expect(prepare).toHaveBeenCalledTimes(1);
  });

  it("still fills the form when the refs already existed (idempotent backend)", async () => {
    prepare.mockResolvedValue({ created: false, refs: ["base", "head-v1"], message: "已存在" });
    render(<NewVerification />);
    fireEvent.click(screen.getByRole("button", { name: "一键创建演示仓库" }));
    await waitFor(() => expect(repoInput().value).toBe("demo/spring-backend"));
    expect(screen.getByText(/演示仓库已存在/)).toBeTruthy();
  });

  it("tells the user to configure an API key on 401 instead of crashing", async () => {
    const err = Object.assign(new Error("missing key"), { status: 401, detail: "" }) as ApiError;
    prepare.mockRejectedValue(err);
    render(<NewVerification />);
    fireEvent.click(screen.getByRole("button", { name: "一键创建演示仓库" }));
    const alert = await screen.findByText(/API 密钥/);
    expect(alert.textContent).toContain("需要先配置 API 密钥");
    expect(repoInput().value).toBe("");
  });

  it("surfaces a genuine setup error verbatim rather than a fake success", async () => {
    const err = Object.assign(new Error("boom"), {
      status: 422,
      detail: "演示仓库目录未找到: demo/spring-backend",
    }) as ApiError;
    prepare.mockRejectedValue(err);
    render(<NewVerification />);
    fireEvent.click(screen.getByRole("button", { name: "一键创建演示仓库" }));
    const alert = await screen.findByText(/演示仓库目录未找到/);
    expect(alert.textContent).toContain("演示仓库目录未找到");
  });
});
