import { describe, expect, it } from "vitest";
import {
  describePreflightError, preflightCheckLabel, preflightLanguageLabel,
  preflightNotRunReason, preflightStatusLabel,
} from "../preflight";
import { describePipelineError } from "../errorHints";

describe("preflightCheckLabel", () => {
  it("translates known check ids", () => {
    expect(preflightCheckLabel("maven_wrapper")).toBe("Maven 构建器");
    expect(preflightCheckLabel("node_test_script")).toBe("测试脚本");
    expect(preflightCheckLabel("JAVA_HOME")).toBe("JAVA_HOME 环境变量");
  });

  it("passes unknown ids through verbatim instead of inventing a meaning", () => {
    expect(preflightCheckLabel("rust_cargo")).toBe("rust_cargo");
  });

  it("renders a dash for empty input", () => {
    expect(preflightCheckLabel("")).toBe("—");
    expect(preflightCheckLabel(null)).toBe("—");
  });
});

describe("preflightStatusLabel", () => {
  it("translates the three statuses", () => {
    expect(preflightStatusLabel("PASS")).toBe("正常");
    expect(preflightStatusLabel("FAIL")).toBe("不满足");
    expect(preflightStatusLabel("WARN")).toBe("提醒");
  });

  it("passes unknown statuses through", () => {
    expect(preflightStatusLabel("SKIPPED")).toBe("SKIPPED");
  });
});

describe("preflightLanguageLabel", () => {
  it("names the detected stack", () => {
    expect(preflightLanguageLabel("java")).toBe("Java / Maven");
    expect(preflightLanguageLabel("node")).toBe("JavaScript / TypeScript");
  });

  it("says 未识别 rather than pretending it is universal", () => {
    expect(preflightLanguageLabel("unknown")).toBe("未识别");
  });
});

describe("preflightNotRunReason", () => {
  it("explains each skip reason", () => {
    expect(preflightNotRunReason({ not_run: "upstream_errors" })).toMatch(/输入校验未通过/);
    expect(preflightNotRunReason({ not_run: "probe_error" })).toMatch(/跳过预检/);
    expect(preflightNotRunReason({ not_run: "disabled_by_SPECPROOF_PREFLIGHT" })).toMatch(/环境变量关闭/);
  });

  it("returns empty when preflight did run", () => {
    expect(preflightNotRunReason({ passed: true })).toBe("");
    expect(preflightNotRunReason(null)).toBe("");
  });
});

describe("describePreflightError", () => {
  it("turns a missing JDK into an actionable next step", () => {
    const hint = describePreflightError("Preflight: Java not found. Install Eclipse Temurin JDK 21.");
    expect(hint).toMatch(/安装 Eclipse Temurin JDK 21/);
    expect(hint).not.toMatch(/^Preflight:/);
    expect(hint).not.toMatch(/Java not found/);
  });

  it("turns a missing Maven wrapper into an actionable next step", () => {
    const hint = describePreflightError(
      "Preflight: No Maven Wrapper (mvnw.cmd/mvnw) found in /repo and no 'mvn' executable on PATH.",
    );
    expect(hint).toMatch(/Maven Wrapper|安装 Maven/);
  });

  it("passes unrecognised messages through verbatim", () => {
    const raw = "Preflight: something entirely new happened";
    expect(describePreflightError(raw)).toBe("something entirely new happened");
  });
});

describe("describePipelineError delegates preflight entries", () => {
  it("routes the Preflight: prefix to the preflight mapper", () => {
    expect(describePipelineError("Preflight: Java not found.")).toMatch(/JDK 21/);
  });

  it("still handles ordinary pipeline errors", () => {
    expect(describePipelineError("git diff failed")).toMatch(/无法比较两个版本/);
  });
});
