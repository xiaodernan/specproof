import { Panel } from "./Panel";
import { Table, type Column } from "./Table";
import {
  describePreflightError, preflightCheckLabel, preflightLanguageLabel,
  preflightNotRunReason, preflightStatusLabel,
  type PreflightCheck, type PreflightResult,
} from "./preflight";

// 环境预检结果卡（roadmap Phase 1.4）。
//
// 设计原则：先说"缺什么、下一步怎么办"，再说细节。未识别的项目语言明确
// 显示"未识别"，未执行的预检说明原因——绝不用空白掩盖"其实没检查"。

const STATUS_TONE: Record<string, string> = {
  PASS: "var(--success)",
  FAIL: "var(--danger)",
  WARN: "var(--warning, var(--accent-text))",
};

const CHECK_COLUMNS: Column<PreflightCheck>[] = [
  {
    key: "check",
    header: "检查项",
    render: (c) => <span title={c.check}>{preflightCheckLabel(c.check ?? "")}</span>,
  },
  {
    key: "status",
    header: "结果",
    render: (c) => (
      <span style={{ color: STATUS_TONE[c.status ?? ""] }}>{preflightStatusLabel(c.status)}</span>
    ),
  },
  {
    key: "detail",
    header: "详情",
    render: (c) => (
      <span className="mono" title={c.detail}>{c.detail || "—"}</span>
    ),
  },
];

export function PreflightCard(props: { preflight?: PreflightResult | null }): JSX.Element | null {
  const p = props.preflight;
  if (!p || (!p.checks?.length && !p.errors?.length && !p.warnings?.length && !p.not_run)) {
    return null;
  }

  const notRun = preflightNotRunReason(p);
  const blocked = p.passed === false || (p.errors?.length ?? 0) > 0;

  return (
    <Panel
      title="执行环境预检"
      right={
        <span className="pill" style={{ borderColor: blocked ? "var(--danger)" : "var(--success)" }}>
          {blocked ? "环境不满足" : "环境正常"}
        </span>
      }
    >
      {notRun ? <div className="kv-value" style={{ marginBottom: 8 }}>{notRun}</div> : null}

      {p.language ? (
        <div className="kv">
          <span className="kv-label">识别到的项目类型</span>
          <span className="kv-value">{preflightLanguageLabel(p.language)}</span>
        </div>
      ) : null}

      {p.errors && p.errors.length > 0 ? (
        <>
          <div className="kv-label" style={{ margin: "10px 0 6px" }}>需要先处理</div>
          {p.errors.map((e, i) => (
            <div key={i} className="errorbox" style={{ marginBottom: 6 }} title={String(e)}>
              {describePreflightError(String(e))}
            </div>
          ))}
        </>
      ) : null}

      {p.checks && p.checks.length > 0 ? (
        <div style={{ marginTop: 10 }}>
          <Table<PreflightCheck>
            columns={CHECK_COLUMNS}
            rows={p.checks}
            rowKey={(c, i) => `${c.check ?? "check"}-${i}`}
            stickyHeader={false}
          />
        </div>
      ) : null}

      {p.warnings && p.warnings.length > 0 ? (
        <>
          <div className="kv-label" style={{ margin: "10px 0 6px" }}>提醒</div>
          {p.warnings.map((w, i) => (
            <div key={i} className="kv-value" style={{ marginBottom: 4 }} title={String(w)}>{String(w)}</div>
          ))}
        </>
      ) : null}

      {p.skipped && p.skipped.length > 0 ? (
        <details style={{ marginTop: 10 }}>
          <summary style={{ fontSize: 12, color: "var(--color-text-2)" }}>
            不适用于该项目类型的检查（{p.skipped.length} 项）
          </summary>
          <div className="kv-value" style={{ marginTop: 6 }}>
            {p.skipped.map(preflightCheckLabel).join("、")}
          </div>
        </details>
      ) : null}
    </Panel>
  );
}
