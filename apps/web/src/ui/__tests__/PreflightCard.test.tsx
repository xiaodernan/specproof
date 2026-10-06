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
    // blocked is a verdict about a probe that RAN — never conflated with 未验证
    expect(screen.queryByText("环境未验证")).toBeNull();
  });

  // #190 semantics on the UI plane: the backend's passed=true covers four of
  // five outcomes (clean / upstream_errors / disabled / probe_error) and only
  // not_run says the probe was skipped. A two-state pill therefore calls every
  // skipped probe 环境正常.
  describe("the pill may only claim 环境正常 when the probe actually ran (#191)", () => {
    it.each([
      ["probe_error", "环境探测自身异常，已跳过预检并继续验证。"],
      ["disabled_by_SPECPROOF_PREFLIGHT", "已通过环境变量关闭环境预检。"],
      ["upstream_errors", "输入校验未通过，环境预检已跳过。"],
    ])("not_run=%s renders 环境未验证, never 环境正常", (notRun, reason) => {
      render(<PreflightCard preflight={{ passed: true, not_run: notRun }} />);
      expect(screen.queryByText("环境未验证")).not.toBeNull();
      expect(screen.queryByText("环境正常")).toBeNull();
      expect(screen.queryByText(reason)).not.toBeNull();
    });

    it("an unknown not_run reason still reads 环境未验证, token verbatim", () => {
      render(<PreflightCard preflight={{ passed: true, not_run: "future_reason" }} />);
      expect(screen.queryByText("环境未验证")).not.toBeNull();
      expect(screen.queryByText("环境正常")).toBeNull();
      expect(screen.queryByText(/future_reason/)).not.toBeNull();
    });

    it("a real clean probe still reads 环境正常", () => {
      render(
        <PreflightCard
          preflight={{
            passed: true,
            language: "node",
            checks: [{ check: "node", status: "PASS", detail: "v20.11.0" }],
          }}
        />,
      );
      expect(screen.queryByText("环境正常")).not.toBeNull();
      expect(screen.queryByText("环境未验证")).toBeNull();
    });
  });

  it("renders nothing when there is nothing to report", () => {
    const { container } = render(<PreflightCard preflight={{ passed: true }} />);
    expect(container.firstChild).toBeNull();
  });
});
