import type { ReactNode } from "react";

export function fmtPct(x: number | null | undefined): string {
  if (x === null || x === undefined) return "—";
  return (x * 100).toFixed(1) + "%";
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

// §3.1: per-node elapsed time on the stage timeline. The backend computes
// `duration_seconds` (first stamp to last stamp on the node's stream). An
// unparseable stamp yields null, so a missing duration renders as "—" and is
// never dressed up as a real measurement.
export function fmtDurationSeconds(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  if (seconds < 1) return seconds.toFixed(2) + " 秒";
  if (seconds < 60) return seconds.toFixed(1) + " 秒";
  const mins = Math.floor(seconds / 60);
  const rem = Math.floor(seconds % 60);
  if (mins < 60) return mins + " 分 " + rem + " 秒";
  const hrs = Math.floor(mins / 60);
  const remMin = mins % 60;
  return hrs + " 小时 " + remMin + " 分";
}

export function shortId(id: string | undefined): string {
  return (id || "").slice(0, 8);
}

// Artifact references arrive from the SSE stream with a machine-prefix
// the viewer does not yet know. Turn each reference into one honest,
// plain-language sentence a reviewer can act on — never dress an
// unknown reference up as something it is not.
export function artifactHint(ref: string): string {
  const r = (ref || "").trim();
  if (!r) return "空的产物引用（未知来源）";
  if (r.startsWith("capsule:file=")) {
    return "复现包（capsule）—— base/head 双侧工作树与执行日志，供评审者本地复现本次验收。";
  }
  if (r.startsWith("counterexample_test:")) {
    return "反例测试（针对性回归）—— 该用例在 head 上失败、在 base 上通过，是本次变更最直接的可复现证据。";
  }
  if (r.startsWith("report:")) {
    return "验收报告—— 证据级 HTML 报告，含契约矩阵、findings 与 verdict；点开可交付评审。";
  }
  if (r.startsWith("s3://") || r.startsWith("oss://") || r.startsWith("http://") || r.startsWith("https://")) {
    return "复现包（capsule）—— 对象存储地址，下载即得可复现的 base/head 环境。";
  }
  return "产物引用（来源未知）—— 原样展示了 SSE 帧里的字符串，未做任何猜测。";
}

export type StatTone = "ok" | "bad" | "warn" | "mute";

export function verdictTone(v: string | undefined): StatTone {
  if (v === "VERIFIED") return "ok";
  if (v === "BLOCKED" || v === "FAILED") return "bad";
  // NEEDS_REVIEW is neither: nothing is proven wrong, and nothing is
  // proven right. "warn" is the honest tone — "bad" would send the reader
  // after a defect that may not exist, "mute" would hide a verdict that
  // still refuses the change.
  if (v === "NEEDS_REVIEW") return "warn";
  return "mute";
}

// The summary verdict arrives as an English enum; the 验证结论 headline should
// speak the user's language. Known tokens map to Chinese; anything unexpected
// is shown verbatim rather than guessed at (an unknown label is honest, a wrong
// friendly label would mislead a merge decision). Exactly the words the worker
// writes into `summary.verdict` — see evidence/verdict_channels.py, which
// fails the build if this record and that channel disagree. Status words
// (STALE, ERROR, CANCELLED) live in STATUS_HELP on the job page, not here.
const VERDICT_LABELS: Record<string, string> = {
  VERIFIED: "通过",
  BLOCKED: "受阻",
  NEEDS_REVIEW: "待人工判断",
  FAILED: "执行失败",
};

export function verdictLabel(v: string | undefined): string {
  if (!v) return "—";
  return VERDICT_LABELS[v] ?? v;
}

// #118: the acceptance-feedback verdict is a DIFFERENT vocabulary from the summary
// verdict above -- accept/reject is what a reviewer casts, VERIFIED/BLOCKED/FAILED is
// what a run concluded. Keeping them in one map would let one word's meaning leak into
// the other's column.
//
// The keys are the words the backend stores; tests/unit/test_feedback_verdict_parity.py
// refuses a label for a verdict the ENUM cannot hold, and refuses a stored verdict with
// no label here. An unexpected value is shown verbatim, never guessed at: a binary
// `=== "accept" ? "接受" : "打回"` filed every unknown (empty, a typo, a future third
// word) as 打回, which told a reader a reviewer rejected something they never rejected.
const FEEDBACK_VERDICT_LABELS: Record<string, string> = {
  accept: "接受",
  reject: "打回",
};

export function feedbackVerdictWords(): string[] {
  return Object.keys(FEEDBACK_VERDICT_LABELS);
}

export function feedbackVerdictLabel(v: string | undefined): string {
  if (!v) return "—";
  return FEEDBACK_VERDICT_LABELS[v] ?? v;
}

export function kv(label: ReactNode, value: ReactNode): ReactNode {
  return (
    <div className="kv">
      <span className="kv-label">{label}</span>
      <span className="kv-value">{value}</span>
    </div>
  );
}
