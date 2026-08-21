import { useId, type ReactNode } from "react";

export interface FieldShellProps {
  label?: string;
  required?: boolean;
  error?: string;
  hint?: string;
  errorId?: string;
  hintId?: string;
  htmlFor?: string;
  className?: string;
  children: ReactNode;
}

export function FieldShell(props: FieldShellProps): JSX.Element {
  return (
    <div className={"ui-field" + (props.className ? " " + props.className : "")}>
      {props.label ? (
        <label className="ui-label" htmlFor={props.htmlFor}>
          {props.label}
          {props.required ? (
            <span className="ui-required" aria-hidden="true">
              {" "}
              *
            </span>
          ) : null}
        </label>
      ) : null}
      {props.children}
      {props.error ? (
        <span className="ui-error" id={props.errorId}>
          {props.error}
        </span>
      ) : props.hint ? (
        <span className="ui-hint" id={props.hintId}>
          {props.hint}
        </span>
      ) : null}
    </div>
  );
}

export function fieldErrorHintIds(
  autoId: string,
  error?: string,
  hint?: string
): { errorId: string; hintId: string; describedBy: string | undefined } {
  const errorId = autoId + "-err";
  const hintId = autoId + "-hint";
  const parts = [error ? errorId : undefined, hint ? hintId : undefined].filter(
    (v): v is string => Boolean(v)
  );
  return { errorId, hintId, describedBy: parts.join(" ") || undefined };
}

export function useFieldAutoId(): string {
  return useId().replace(/[^a-zA-Z0-9_-]/g, "");
}
