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

export function shortId(id: string | undefined): string {
  return (id || "").slice(0, 8);
}

export type StatTone = "ok" | "bad" | "warn" | "mute";

export function verdictTone(v: string | undefined): StatTone {
  if (v === "VERIFIED") return "ok";
  if (v === "BLOCKED" || v === "FAILED") return "bad";
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
