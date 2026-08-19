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

export function severityTone(s: string | undefined): "bad" | "warn" | "info" {
  if (s === "BLOCKER") return "bad";
  if (s === "MAJOR") return "warn";
  return "info";
}

export function kv(label: string, value: ReactNode): ReactNode {
  return (
    <div className="kv">
      <span className="kv-label">{label}</span>
      <span className="kv-value">{value}</span>
    </div>
  );
}
