import type { ReactNode } from "react";

// Section panel: hairline border, layered elevation, uppercase kicker
// header — the design-system successor of the legacy .panel block.
// `title` accepts a node so a header can carry an inline <Term> explanation
// (roadmap Phase 3.3) — same latitude `right` already had.
export function Panel(props: {
  title: ReactNode;
  children?: ReactNode;
  right?: ReactNode;
}): JSX.Element {
  return (
    <section className="panel">
      <header className="panel-head">
        <h2>{props.title}</h2>
        {props.right ? <div className="panel-right">{props.right}</div> : null}
      </header>
      <div className="panel-body">{props.children}</div>
    </section>
  );
}
