import { forwardRef, type TextareaHTMLAttributes } from "react";
import { FieldShell, fieldErrorHintIds, useFieldAutoId } from "./Field";

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  required?: boolean;
  error?: string;
  hint?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(props, ref) {
  const { label, required, error, hint, className, id, ...rest } = props;
  const autoId = useFieldAutoId();
  const textareaId = id ?? autoId;
  const ids = fieldErrorHintIds(autoId, error, hint);
  return (
    <FieldShell
      label={label}
      required={required}
      error={error}
      hint={hint}
      errorId={ids.errorId}
      hintId={ids.hintId}
      htmlFor={textareaId}
      className={className}
    >
      <textarea
        ref={ref}
        id={textareaId}
        className="ui-textarea"
        aria-invalid={error ? true : undefined}
        aria-describedby={ids.describedBy}
        {...rest}
      />
    </FieldShell>
  );
});
