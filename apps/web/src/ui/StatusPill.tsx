// Design-system status pill. Keeps the legacy .pill class contract
// (W39 e2e asserts .pill on the Matrix page) while rendering with the
// Aurora status tokens.
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
  const labels: Record<string, string> = {
    VERIFIED: "验收通过", BLOCKED: "发现风险", FAILED: "执行失败", ERROR: "执行出错",
    QUEUED: "等待执行", RUNNING: "正在验收", PENDING: "等待处理", CANCELLED: "已取消",
    WAITING_FOR_PROVIDER: "等待模型", UNVERIFIED: "证据不足",
  };
  return <span className={"pill " + cls} title={s}>{labels[s] || s}</span>;
}
