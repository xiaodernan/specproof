import { describe, expect, it } from "vitest";
import { describeDegradedReason, describePipelineError } from "../errorHints";

// Shared by the VERIFY JobDetail panel and the CRAFT agent console. The whole
// point is honesty: recognised infra/git/model signatures become actionable
// Chinese guidance, everything else is returned verbatim (never fabricated).
describe("describePipelineError", () => {
  it("maps a known git ref failure to Chinese next-step guidance", () => {
    const out = describePipelineError(
      "Repository safety check failed for base prepare (ref_in_repo: ref 'x' does not belong to the repository: fatal: unknown revision)"
    );
    expect(out).toContain("版本引用无法解析");
    expect(out).not.toMatch(/unknown revision/);
  });

  it("maps a provider/model failure to Chinese guidance", () => {
    expect(describePipelineError("LLM generation failed: no api key")).toContain("模型服务");
  });

  it("maps a missing-path failure to Chinese guidance", () => {
    expect(describePipelineError("path /repo/missing does not exist")).toContain("路径不存在");
  });

  it("maps a missing head workspace to Chinese guidance", () => {
    expect(describePipelineError("No head workspace - cannot generate tests")).toContain("工作区准备失败");
  });

  it("maps a base/head workspace prep error to Chinese guidance", () => {
    expect(describePipelineError("Error preparing head workspace: permission denied")).toContain("工作区准备失败");
  });

  it("maps a compile/build failure neutrally (does not assert a verdict)", () => {
    const out = describePipelineError(
      "Fallback template failed to compile on Head: [ERROR] COMPILATION ERROR"
    );
    expect(out).toContain("编译");
    // stays honest: surfaces both "genuine mismatch" and "environment" readings
    expect(out).toContain("环境问题");
  });

  it("broadens the git-diff signature to per-file failures", () => {
    expect(describePipelineError("git diff for src/App.java failed: exit 128")).toContain("无法比较两个版本");
  });

  it("treats an LLM contract compilation failure as a model-service gap", () => {
    expect(describePipelineError("LLM contract compilation failed: 429 rate limited")).toContain("模型服务");
  });

  it("returns unrecognised messages verbatim (never fabricates a meaning)", () => {
    const raw = "some brand new failure wording nobody has seen";
    expect(describePipelineError(raw)).toBe(raw);
  });

  it("passes empty strings through unchanged", () => {
    expect(describePipelineError("")).toBe("");
  });
});

describe("describeDegradedReason", () => {
  it("glosses a Redis cache degradation into actionable Chinese", () => {
    expect(describeDegradedReason("redis: Connection refused")).toContain("Redis");
    expect(describeDegradedReason("redis: Connection refused")).toContain("进度");
  });

  it("glosses a MySQL database degradation", () => {
    expect(describeDegradedReason("mysql: too many connections")).toContain("主数据库");
  });

  it("glosses a persistence-failure / job-not-accepted reason", () => {
    expect(describeDegradedReason("job NOT accepted - persistence failed: db down")).toContain("未能写入存储");
  });

  it("returns unknown subsystems verbatim (never fabricates a meaning)", () => {
    const raw = "clickhouse: some unfamiliar outage";
    expect(describeDegradedReason(raw)).toBe(raw);
  });
});
