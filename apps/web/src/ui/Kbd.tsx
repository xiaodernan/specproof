import type { ReactNode } from "react";

export function Kbd(props: { children?: ReactNode }): JSX.Element {
  return <kbd className="ui-kbd">{props.children}</kbd>;
}
