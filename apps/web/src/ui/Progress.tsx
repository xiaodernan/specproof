export interface ProgressProps {
  value: number;
  max?: number;
  tone?: "accent" | "success" | "warning" | "danger";
  size?: "sm" | "md" | "lg";
  label?: string;
  showValue?: boolean;
}

export function Progress(props: ProgressProps): JSX.Element {
  const { value, max = 100, tone = "accent", size = "md", label, showValue = false } = props;
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const cls =
    "ui-progress ui-progress-" + size + " ui-progress-" + tone;
  return (
    <div className="ui-progress-row">
      {label || showValue ? (
        <div className="ui-progress-head">
          {label ? <span className="ui-progress-label">{label}</span> : <span />}
          {showValue ? <span className="ui-progress-value">{Math.round(pct)}%</span> : null}
        </div>
      ) : null}
      <div
        className={cls}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={value}
        aria-label={label}
      >
        <div className="ui-progress-fill" style={{ width: pct + "%" }} />
      </div>
    </div>
  );
}
