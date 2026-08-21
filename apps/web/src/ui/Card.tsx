import type { ReactNode } from "react";

export interface CardProps {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  pad?: boolean;
}

export function Card(props: CardProps): JSX.Element {
  const hasHead = Boolean(props.title || props.actions);
  const cls = "ui-card" + (props.className ? " " + props.className : "");
  return (
    <section className={cls}>
      {hasHead ? (
        <header className="ui-card-head">
          <div>
            {props.title ? <div className="ui-card-title">{props.title}</div> : null}
            {props.subtitle ? <div className="ui-card-sub">{props.subtitle}</div> : null}
          </div>
          {props.actions ? <div className="ui-card-actions">{props.actions}</div> : null}
        </header>
      ) : null}
      <div className={props.pad === false ? "ui-card-body ui-card-body-flush" : "ui-card-body"}>
        {props.children}
      </div>
    </section>
  );
}
