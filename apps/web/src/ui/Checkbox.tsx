import { useEffect, useRef, type InputHTMLAttributes } from "react";
import { CheckIcon, DashIcon } from "./icons";
import { useFieldAutoId } from "./Field";

export interface CheckboxProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "children"> {
  label?: string;
  error?: string;
  hint?: string;
  indeterminate?: boolean;
}

export function Checkbox(props: CheckboxProps): JSX.Element {
  const { label, error, hint, indeterminate, className, id, checked, onChange, disabled, ...rest } = props;
  const autoId = useFieldAutoId();
  const inputId = id ?? autoId;
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.indeterminate = Boolean(indeterminate);
  }, [indeterminate]);

  return (
    <div className={"ui-field" + (className ? " " + className : "")}>
      <label className="ui-checkbox" htmlFor={inputId}>
        <span className="ui-checkbox-box">
          <input
            ref={ref}
            id={inputId}
            type="checkbox"
            className="ui-checkbox-input"
            checked={checked}
            onChange={onChange}
            disabled={disabled}
            aria-invalid={error ? true : undefined}
            {...rest}
          />
          <span className="ui-checkbox-frame" aria-hidden="true" />
          <CheckIcon className="ui-checkbox-check" size={10} />
          <DashIcon className="ui-checkbox-dash" size={10} />
        </span>
        {label ? <span className="ui-checkbox-label">{label}</span> : null}
      </label>
      {error ? (
        <span className="ui-error">{error}</span>
      ) : hint ? (
        <span className="ui-hint">{hint}</span>
      ) : null}
    </div>
  );
}
