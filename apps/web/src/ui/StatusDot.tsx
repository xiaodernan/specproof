export type DotStatus = "running" | "success" | "warning" | "danger" | "info" | "idle" | "neutral";

export interface StatusDotProps {
  status?: DotStatus;
  label?: string;
  pulse?: boolean;
  size?: "sm" | "md";
}

export function StatusDot(props: StatusDotProps): JSX.Element {
  const status = props.status ?? "neutral";
  const pulsing = props.pulse ?? status === "running";
  const cls =
    "ui-statusdot ui-statusdot-" +
    status +
    (props.size === "sm" ? " ui-statusdot-sm" : "") +
    (pulsing ? " ui-statusdot-pulse" : "");
  return (
    <span className={cls}>
      <span className="ui-statusdot-dot" aria-hidden="true" />
      {props.label ? <span className="ui-statusdot-label">{props.label}</span> : null}
    </span>
  );
}
