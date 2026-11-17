// Partial-degradation notice: the app runs, but some capabilities fell
// back. Rendered with the warning tokens.
import { describeDegradedReason } from "./errorHints";
import { storedLocale } from "../i18n/strings";

export function Degraded(props: { reasons: string[] }): JSX.Element | null {
  if (!props.reasons || props.reasons.length === 0) return null;
  return (
    <div className="degraded">
      <strong>{storedLocale() === "zh" ? "降级" : "DEGRADED"}</strong>
      <ul>
        {props.reasons.map((r, i) => (
          <li key={i} title={r}>{describeDegradedReason(r)}</li>
        ))}
      </ul>
    </div>
  );
}
