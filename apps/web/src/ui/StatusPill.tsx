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
  return <span className={"pill " + cls}>{s}</span>;
}
