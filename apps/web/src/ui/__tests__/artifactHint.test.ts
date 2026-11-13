import { describe, expect, it } from "vitest";

import { artifactHint } from "../util";

// §3.1 收尾：阶段行的产物 chip 悬停时必须给出"这是什么"的一句白话，
// 而不是让评审者对着 counterexample_test:FooTest.java 猜。
describe("artifactHint", () => {
  it("explains the capsule file reference", () => {
    expect(artifactHint("capsule:file=capsule-123.zip")).toContain("复现包");
  });

  it("explains object-store capsule addresses", () => {
    expect(artifactHint("s3://bucket/capsules/abc.zip")).toContain("对象存储");
    expect(artifactHint("https://oss.example.com/capsule.zip")).toContain("对象存储");
  });

  it("explains the counterexample test reference", () => {
    const hint = artifactHint("counterexample_test:UnauthenticatedRequestTest.java");
    expect(hint).toContain("反例测试");
    expect(hint).toContain("head");
    expect(hint).toContain("base");
  });

  it("explains the report reference", () => {
    expect(artifactHint("report:verification-report.html")).toContain("验收报告");
  });

  it("claims nothing it does not know — unknown refs stay honest", () => {
    const hint = artifactHint("mystery:blob-999");
    expect(hint).toContain("未知");
    expect(hint).not.toContain("复现包");
    expect(hint).not.toContain("反例");
  });

  it("handles empty input without inventing facts", () => {
    expect(artifactHint("")).toContain("未知");
    expect(artifactHint("   ")).toContain("未知");
  });
});
