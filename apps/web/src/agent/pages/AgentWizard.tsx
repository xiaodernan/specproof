import { useState } from "react";
import { createAgentJob } from "../../api";
import { ErrorBox, Panel } from "../../components";
import {
  WizardDraft,
  buildSpecText,
  clearWizardDraft,
  loadWizardDraft,
  saveWizardDraft,
  validateRepoStep,
  validateSpecStep,
} from "../util";

export type WizardStep = "repo" | "spec" | "gates" | "review";

const STEPS: { key: WizardStep; label: string; href: string }[] = [
  { key: "repo", label: "1 仓库 Repo", href: "#/agent/new" },
  { key: "spec", label: "2 需求 Spec", href: "#/agent/new/spec" },
  { key: "gates", label: "3 门禁 Gates", href: "#/agent/new/gates" },
  { key: "review", label: "4 提交 Review", href: "#/agent/new/review" },
];

export default function AgentWizard(props: { step: WizardStep }) {
  const [draft, setDraft] = useState<WizardDraft>(() => loadWizardDraft());
  const [error, setError] = useState<Error | string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const set = (patch: Partial<WizardDraft>) => {
    const next = { ...draft, ...patch };
    setDraft(next);
    saveWizardDraft(next);
  };

  const submit = async () => {
    setError(null);
    setSubmitting(true);
    try {
      const created = await createAgentJob(
        draft.repo_path.trim(),
        buildSpecText(draft),
        draft.task_name.trim()
      );
      clearWizardDraft();
      window.location.hash = "#/agent/jobs/" + created.job_id;
    } catch (e) {
      setError(e as Error);
      setSubmitting(false);
    }
  };

  const stepIndex = STEPS.findIndex((s) => s.key === props.step);

  return (
    <div>
      <div className="page-head">
        <h1>新建 Agent 任务</h1>
        <div className="page-sub">TASK WIZARD — 4 步: 仓库 → 需求 → 门禁 → 提交</div>
      </div>
      <div className="wizard-steps">
        {STEPS.map((s, i) => (
          <a
            key={s.key}
            href={s.href}
            className={
              "wizard-step" +
              (i === stepIndex ? " wizard-step-active" : "") +
              (i < stepIndex ? " wizard-step-done" : "")
            }
          >
            {s.label}
          </a>
        ))}
      </div>
      <ErrorBox error={error} />

      {props.step === "repo" ? (
        <Panel title="步骤 1/4 — 目标仓库">
          <label className="field">仓库路径 Repo path</label>
          <input
            type="text"
            data-testid="wizard-repo"
            value={draft.repo_path}
            placeholder="D:\repos\my-service"
            onChange={(e) => set({ repo_path: e.target.value })}
          />
          <label className="field">任务名称 Task name (可选)</label>
          <input
            type="text"
            data-testid="wizard-task"
            value={draft.task_name}
            placeholder="为服务端增加分页"
            onChange={(e) => set({ task_name: e.target.value })}
          />
          {validateRepoStep(draft) ? (
            <div className="errorbox">{validateRepoStep(draft)}</div>
          ) : null}
          <div style={{ marginTop: 14 }}>
            <a
              className={"btn" + (validateRepoStep(draft) ? " btn-disabled" : "")}
              href={validateRepoStep(draft) ? "#/agent/new" : "#/agent/new/spec"}
            >
              下一步 Next
            </a>
          </div>
        </Panel>
      ) : null}

      {props.step === "spec" ? (
        <Panel title="步骤 2/4 — 需求规格">
          <label className="field">需求规格 Spec text</label>
          <textarea
            rows={12}
            data-testid="wizard-spec"
            value={draft.spec_text}
            placeholder={"为 /users 列表接口增加分页参数 (page, page_size)，默认 page_size=20，" +
              "上限 100；补充分页相关的单元测试。"}
            onChange={(e) => set({ spec_text: e.target.value })}
          />
          {validateSpecStep(draft) ? (
            <div className="errorbox">{validateSpecStep(draft)}</div>
          ) : null}
          <div style={{ marginTop: 14, display: "flex", gap: 8 }}>
            <a className="btn btn-ghost" href="#/agent/new">
              上一步 Back
            </a>
            <a
              className={"btn" + (validateSpecStep(draft) ? " btn-disabled" : "")}
              href={validateSpecStep(draft) ? "#/agent/new/spec" : "#/agent/new/gates"}
            >
              下一步 Next
            </a>
          </div>
        </Panel>
      ) : null}

      {props.step === "gates" ? (
        <Panel title="步骤 3/4 — 执行门禁">
          {(
            [
              ["run_tests", "运行测试 run_tests", "改动后运行项目测试"],
              ["run_lint", "运行 Lint run_lint", "静态检查"],
              ["run_typecheck", "运行类型检查 run_typecheck", "类型系统检查"],
              ["require_gate", "最终门禁需人工审批 require_gate", "完成后等待门禁审批"],
            ] as [keyof WizardDraft["gates"], string, string][]
          ).map(([key, label, sub]) => (
            <label className="check-row" key={key}>
              <input
                type="checkbox"
                checked={draft.gates[key]}
                onChange={(e) =>
                  set({ gates: { ...draft.gates, [key]: e.target.checked } })
                }
              />
              <span>
                <strong>{label}</strong>
                <span className="muted"> — {sub}</span>
              </span>
            </label>
          ))}
          <label className="field">预算 Budget (分钟)</label>
          <input
            type="number"
            min={1}
            max={600}
            value={draft.budget_minutes}
            onChange={(e) => set({ budget_minutes: Number(e.target.value) || 60 })}
          />
          <label className="field">最大步骤数 Max steps (≤12)</label>
          <input
            type="number"
            min={1}
            max={12}
            value={draft.max_steps}
            onChange={(e) => set({ max_steps: Number(e.target.value) || 12 })}
          />
          <div style={{ marginTop: 14, display: "flex", gap: 8 }}>
            <a className="btn btn-ghost" href="#/agent/new/spec">
              上一步 Back
            </a>
            <a className="btn" href="#/agent/new/review">
              下一步 Next
            </a>
          </div>
        </Panel>
      ) : null}

      {props.step === "review" ? (
        <Panel title="步骤 4/4 — 审阅并提交">
          <div className="kv">
            <span className="kv-label">Repo</span>
            <span className="kv-value mono">{draft.repo_path || "—"}</span>
          </div>
          <div className="kv">
            <span className="kv-label">Task</span>
            <span className="kv-value mono">{draft.task_name || "—"}</span>
          </div>
          <div className="kv-label" style={{ margin: "10px 0 4px" }}>
            将提交的 spec (含门禁约束)
          </div>
          <pre className="json">{buildSpecText(draft)}</pre>
          <div style={{ marginTop: 14, display: "flex", gap: 8 }}>
            <a className="btn btn-ghost" href="#/agent/new/gates">
              上一步 Back
            </a>
            <button
              className="btn"
              data-testid="wizard-submit"
              disabled={submitting}
              onClick={() => void submit()}
            >
              {submitting ? "提交中 SUBMITTING…" : "创建任务 Create job"}
            </button>
          </div>
        </Panel>
      ) : null}
    </div>
  );
}
