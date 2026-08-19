import type { ReactNode } from "react";

export interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}

export function EmptyState(props: EmptyStateProps): JSX.Element {
  return (
    <div className="ui-empty">
      {props.icon ? <div className="ui-empty-icon">{props.icon}</div> : null}
      <div className="ui-empty-title">{props.title}</div>
      {props.description ? <div className="ui-empty-desc">{props.description}</div> : null}
      {props.action ? <div className="ui-empty-action">{props.action}</div> : null}
    </div>
  );
}
