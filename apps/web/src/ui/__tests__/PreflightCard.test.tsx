import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PreflightCard } from "../PreflightCard";
import type { PreflightResult } from "../preflight";

const RESULT: PreflightResult = {
  passed: false,
  language: "java",
  checks: [
    { check: "maven_wrapper", status: "PASS", detail: "OK" },
    { check: "rust_cargo", status: "WARN", detail: "" },
  ],
  errors: ["Preflight: Java not found. Install Eclipse Temurin JDK 21."],
};

describe("PreflightCard", () => {
  it("renders the design-system Table with Chinese headers and localized cells", () => {
    render(<PreflightCard preflight={RESULT} />);
    expect(screen.queryByText("检查项")).not.toBeNull();
    expect(screen.queryByText("结果")).not.toBeNull();
    expect(screen.queryByText("详情")).not.toBeNull();
    expect(screen.queryByText("Maven 构建器")).not.toBeNull();
    expect(screen.queryByText("正常")).not.toBeNull();
    expect(screen.queryByText("提醒")).not.toBeNull();
  });

  it("passes an unknown check id through verbatim instead of inventing a meaning", () => {
    render(<PreflightCard preflight={RESULT} />);
    expect(screen.queryByText("rust_cargo")).not.toBeNull();
  });

  it("keeps the raw check id available for audit via the cell title", () => {
    const { container } = render(<PreflightCard preflight={RESULT} />);
    const titled = [...container.querySelectorAll('[title="maven_wrapper"]')];
    expect(titled.length).toBeGreaterThan(0);
  });

  it("shows a blocking action card, not raw English stderr", () => {
    render(<PreflightCard preflight={RESULT} />);
    expect(screen.queryByText("环境不满足")).not.toBeNull();
    expect(screen.queryByText(/安装 Eclipse Temurin JDK 21/)).not.toBeNull();
    expect(screen.queryByText(/^Preflight: Java not found/)).toBeNull();
  });

  it("renders nothing when there is nothing to report", () => {
    const { container } = render(<PreflightCard preflight={{ passed: true }} />);
    expect(container.firstChild).toBeNull();
  });
});
