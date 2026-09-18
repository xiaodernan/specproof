import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import NewVerification from "./NewVerification";
import { createVerification } from "../api";

vi.mock("../api", () => ({ createVerification: vi.fn() }));
const create = vi.mocked(createVerification);
beforeEach(() => { create.mockReset(); window.location.hash = "#/jobs/new"; });

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
});
