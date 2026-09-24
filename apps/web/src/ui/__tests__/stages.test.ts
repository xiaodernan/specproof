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
    // Kept as a readable list; the authoritative two-way reconciliation is
    // tests/unit/test_progress_event_labels.py, which parses agent/graph.py
    // and agent/worker.py so this list cannot silently fall behind.
    for (const id of ["intake", "preflight", "compile_contracts", "prepare_base", "prepare_head", "collect_diff",
      "retrieve_repository_context", "run_static_checks", "generate_counterexamples", "run_differential",
      "run_deep_experiments", "review_court", "build_matrix", "create_capsule", "run_release_checks",
      "publish_report"]) {
      expect(STAGE_LABELS[id], id).toBeTruthy();
    }
  });

  it("glosses the worker's own events, which are not pipeline stages", () => {
    // The worker writes these names directly into the progress stream. Before
    // this, a failed job's timeline row was labelled with the raw job id,
    // because the worker passed job_id as the node name.
    expect(stageLabel("terminal")).toContain("终止处理");
    expect(stageLabel("cancel_checkpoint")).toContain("取消");
    expect(stageLabel("lease")).toContain("租约");
    // A gloss must not pretend these are a step of the pipeline.
    for (const id of ["terminal", "cancel_checkpoint", "lease"]) {
      expect(STAGE_LABELS[id], id).toContain("不是某个执行阶段");
    }
  });
});
