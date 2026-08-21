import type { ReactNode } from "react";

export type StatTone = "ok" | "bad" | "warn" | "info" | "mute";

// Metric tile with tabular-nums value and a per-tone accent color.
export function StatCard(props: {
  label: string;
  value: ReactNode;
  tone?: StatTone;
  sub?: string;
}): JSX.Element {
  const tone = props.tone || "info";
  return (
    <div className={"stat stat-" + tone}>
      <div className="stat-value">{props.value}</div>
      <div className="stat-label">{props.label}</div>
      {props.sub ? <div className="stat-sub">{props.sub}</div> : null}
    </div>
  );
}
