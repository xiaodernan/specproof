import { forwardRef, type SelectHTMLAttributes } from "react";
import { FieldShell, fieldErrorHintIds, useFieldAutoId } from "./Field";
import { ChevronDownIcon } from "./icons";

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  required?: boolean;
  error?: string;
  hint?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(props, ref) {
  const { label, required, error, hint, className, id, children, ...rest } = props;
  const autoId = useFieldAutoId();
  const selectId = id ?? autoId;
  const ids = fieldErrorHintIds(autoId, error, hint);
  return (
    <FieldShell
      label={label}
      required={required}
      error={error}
      hint={hint}
      errorId={ids.errorId}
      hintId={ids.hintId}
      htmlFor={selectId}
      className={className}
    >
      <span className="ui-select-wrap">
        <select
          ref={ref}
          id={selectId}
          className="ui-select"
          aria-invalid={error ? true : undefined}
          aria-describedby={ids.describedBy}
          {...rest}
        >
          {children}
        </select>
        <span className="ui-select-chevron" aria-hidden="true">
          <ChevronDownIcon size={14} />
        </span>
      </span>
    </FieldShell>
  );
});
