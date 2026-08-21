import { forwardRef, type InputHTMLAttributes } from "react";
import { FieldShell, fieldErrorHintIds, useFieldAutoId } from "./Field";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  required?: boolean;
  error?: string;
  hint?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(props, ref) {
  const { label, required, error, hint, className, id, ...rest } = props;
  const autoId = useFieldAutoId();
  const inputId = id ?? autoId;
  const ids = fieldErrorHintIds(autoId, error, hint);
  return (
    <FieldShell
      label={label}
      required={required}
      error={error}
      hint={hint}
      errorId={ids.errorId}
      hintId={ids.hintId}
      htmlFor={inputId}
      className={className}
    >
      <input
        ref={ref}
        id={inputId}
        className="ui-input"
        aria-invalid={error ? true : undefined}
        aria-describedby={ids.describedBy}
        {...rest}
      />
    </FieldShell>
  );
});
