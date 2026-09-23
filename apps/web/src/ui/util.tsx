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
  if (v === "BLOCKED" || v === "FAILED" || v === "ERROR") return "bad";
  if (v === "NEEDS REVIEW") return "warn";
  return "mute";
}

// The summary verdict arrives as an English enum; the 验证结论 headline should
// speak the user's language. Known tokens map to Chinese; anything unexpected
// is shown verbatim rather than guessed at (an unknown label is honest, a wrong
// friendly label would mislead a merge decision).
const VERDICT_LABELS: Record<string, string> = {
  VERIFIED: "通过",
  BLOCKED: "受阻",
  FAILED: "执行失败",
  ERROR: "执行错误",
  UNVERIFIED: "待验证",
  "NEEDS REVIEW": "需复核",
  STALE: "已过期",
  CANCELLED: "已取消",
};

export function verdictLabel(v: string | undefined): string {
  if (!v) return "—";
  return VERDICT_LABELS[v] ?? v;
}

export function kv(label: ReactNode, value: ReactNode): ReactNode {
  return (
    <div className="kv">
      <span className="kv-label">{label}</span>
      <span className="kv-value">{value}</span>
    </div>
  );
}
