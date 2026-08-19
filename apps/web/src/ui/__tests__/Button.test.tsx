import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Button } from "../Button";

describe("Button", () => {
  it("renders the variant and size classes", () => {
    render(
      <Button variant="primary" size="lg">
        提交
      </Button>
    );
    const btn = screen.getByRole("button", { name: "提交" });
    expect(btn.className).toContain("ui-btn-primary");
    expect(btn.className).toContain("ui-btn-lg");
    expect(btn.hasAttribute("disabled")).toBe(false);
  });

  it("fires onClick when enabled", () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>点击</Button>);
    fireEvent.click(screen.getByRole("button", { name: "点击" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("is disabled and marked busy while loading, and does not fire onClick", () => {
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        提交中
      </Button>
    );
    const btn = screen.getByRole("button", { name: "提交中" });
    expect(btn.hasAttribute("disabled")).toBe(true);
    expect(btn.getAttribute("aria-busy")).toBe("true");
    fireEvent.click(btn);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("does not fire onClick when disabled", () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        禁用
      </Button>
    );
    fireEvent.click(screen.getByRole("button", { name: "禁用" }));
    expect(onClick).not.toHaveBeenCalled();
  });
});
