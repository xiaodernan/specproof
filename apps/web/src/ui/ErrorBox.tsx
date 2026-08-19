// Graceful-degradation notice. Class + testid are part of the W39 e2e
// contract (.errorbox, data-testid="errorbox").
export function ErrorBox(props: { error: Error | string | null }): JSX.Element | null {
  if (!props.error) return null;
  const text = typeof props.error === "string" ? props.error : props.error.message;
  return (
    <div className="errorbox" data-testid="errorbox" role="alert">
      {"错误 ERROR — " + text}
    </div>
  );
}
