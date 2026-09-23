import { describe, expect, it } from "vitest";
import { stageLabel, STAGE_LABELS } from "../stages";

describe("stageLabel — translate internal node ids for humans, honestly", () => {
  it("maps known pipeline nodes to a Chinese step name", () => {
    expect(stageLabel("compile_contracts")).toBe("解析需求为验收条件");
    expect(stageLabel("run_differential")).toContain("差分");
    expect(stageLabel("publish_report")).toBe("生成验证报告");
  });

  it("passes an unknown node through verbatim rather than inventing a step", () => {
    expect(stageLabel("some_future_node")).toBe("some_future_node");
  });

  it("renders an em dash for a missing node", () => {
    expect(stageLabel(undefined)).toBe("—");
    expect(stageLabel("")).toBe("—");
  });

  it("covers every node registered in the graph", () => {
    // These ids mirror agent/graph.py add_node(...) calls.
    for (const id of ["intake", "compile_contracts", "prepare_base", "prepare_head", "collect_diff",
      "retrieve_repository_context", "run_static_checks", "generate_counterexamples", "run_differential",
      "run_deep_experiments", "review_court", "build_matrix", "create_capsule", "run_release_checks",
      "publish_report"]) {
      expect(STAGE_LABELS[id], id).toBeTruthy();
    }
  });
});
