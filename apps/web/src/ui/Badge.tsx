import type { ReactNode } from "react";

export type BadgeTone = "neutral" | "accent" | "success" | "warning" | "danger" | "info";

export interface BadgeProps {
  tone?: BadgeTone;
  children?: ReactNode;
  className?: string;
}

export function Badge(props: BadgeProps): JSX.Element {
  const cls =
    "ui-badge ui-badge-" + (props.tone ?? "neutral") + (props.className ? " " + props.className : "");
  return <span className={cls}>{props.children}</span>;
}
