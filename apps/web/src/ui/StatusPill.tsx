// Design-system status pill. Keeps the legacy .pill class contract
// (W39 e2e asserts .pill on the Matrix page) while rendering with the
// Aurora status tokens.
//
// Single source of truth for status wording: pages must import `statusLabel`
// rather than keep a private map, so the same status never renders two
// different Chinese strings on one screen (e.g. the Jobs list once showed
// "正在验证" beside the pill's "正在验收"). Terminology follows the nav's
// 验收 (acceptance) wording.
export const STATUS_LABELS: Record<string, string> = {
  VERIFIED: "验收通过",
  BLOCKED: "发现风险",
  FAILED: "执行失败",
  ERROR: "执行出错",
  QUEUED: "等待执行",
  RUNNING: "正在验收",
  PENDING: "等待处理",
  CANCELLED: "已取消",
  WAITING_FOR_PROVIDER: "等待模型服务",
  UNVERIFIED: "证据不足",
  INCONCLUSIVE: "尚无明确结论",
  // Progress-stream stage rows carry "completed" for every finished stage;
  // without a label the timeline showed the raw token on every row.
  COMPLETED: "已完成",
};

export function statusLabel(status?: string | null): string {
  const s = (status || "").toUpperCase();
  return STATUS_LABELS[s] || s;
}

export function StatusPill(props: { status: string }): JSX.Element {
  const s = (props.status || "UNKNOWN").toUpperCase();
  const cls =
    s === "VERIFIED"
      ? "pill-ok"
      : s === "BLOCKED" || s === "FAILED" || s === "ERROR"
      ? "pill-bad"
      : s === "RUNNING" || s === "QUEUED" || s === "PENDING" || s === "WAITING_FOR_PROVIDER"
      ? "pill-run"
      : "pill-mute";
  return <span className={"pill " + cls} title={s}>{statusLabel(s)}</span>;
}
