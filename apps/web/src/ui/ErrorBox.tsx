import { storedLocale } from "../i18n/strings";
// Graceful-degradation notice. Class + testid are part of the W39 e2e
// contract (.errorbox, data-testid="errorbox").
export function ErrorBox(props: { error: Error | string | null }): JSX.Element | null {
  if (!props.error) return null;
  const text = typeof props.error === "string" ? props.error : props.error.message;
  return (
    <div className="errorbox" data-testid="errorbox" role="alert">
      {(storedLocale() === "zh" ? "错误 ERROR · " : "ERROR · ") + text}
    </div>
  );
}
