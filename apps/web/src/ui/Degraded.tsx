// Partial-degradation notice: the app runs, but some capabilities fell
// back. Rendered with the warning tokens.
export function Degraded(props: { reasons: string[] }): JSX.Element | null {
  if (!props.reasons || props.reasons.length === 0) return null;
  return (
    <div className="degraded">
      <strong>降级 DEGRADED</strong>
      <ul>
        {props.reasons.map((r, i) => (
          <li key={i}>{r}</li>
        ))}
      </ul>
    </div>
  );
}
