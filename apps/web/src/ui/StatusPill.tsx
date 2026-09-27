// Design-system status pill. Keeps the legacy .pill class contract
// (W39 e2e asserts .pill on the Matrix page) while rendering with the
// Aurora status tokens.
//
// Single source of truth for status wording: pages must import `statusLabel`
// rather than keep a private map, so the same status never renders two
// different Chinese strings on one screen (e.g. the Jobs list once showed
// "正在验证" beside the pill's "正在验收"). Terminology follows the nav's
// 验收 (acceptance) wording.
//
// SCOPE: job statuses only. UNVERIFIED and INCONCLUSIVE used to live here and
// are NOT job statuses (they are matrix-row / verdict words, resolved by
// resultPill / verdictLabel) — the Jobs filter dropdown is built from this map,
// so offering them sent `?status=UNVERIFIED`, which the API now rejects and
// which used to answer "no results" for a filter that cannot match anything.
// The real vocabulary is JOB_STATUSES below; the API derives the same set from
// storage/mysql.py::_VALID_TRANSITIONS and
// tests/unit/test_job_status_channel_parity.py locks the two together.
export const STATUS_LABELS: Record<string, string> = {
  PENDING: "等待处理",
  QUEUED: "等待执行",
  RUNNING: "正在验收",
  WAITING_FOR_PROVIDER: "等待模型服务",
  VERIFIED: "验收通过",
  BLOCKED: "发现风险",
  FAILED: "执行失败",
  ERROR: "执行出错",
  CANCELLED: "已取消",
  STALE: "已过期",
  // Progress-stream stage rows carry "completed" for every finished stage;
  // without a label the timeline showed the raw token on every row. This is a
  // STREAM word, not a job status — it is deliberately absent from JOB_STATUSES.
  COMPLETED: "已完成",
};

//: The job statuses, in lifecycle order — what a status FILTER may offer.
//: Same ten words the API accepts, ordered for a human reading the dropdown
//: rather than alphabetically.
export const JOB_STATUSES: readonly string[] = [
  "PENDING",
  "QUEUED",
  "RUNNING",
  "WAITING_FOR_PROVIDER",
  "VERIFIED",
  "BLOCKED",
  "FAILED",
  "ERROR",
  "CANCELLED",
  "STALE",
];

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
