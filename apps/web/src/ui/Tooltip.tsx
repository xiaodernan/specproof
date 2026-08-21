import { cloneElement, isValidElement, useId, type ReactElement, type ReactNode } from "react";

export interface TooltipProps {
  content: ReactNode;
  side?: "top" | "bottom" | "left" | "right";
  children: ReactNode;
}

export function Tooltip(props: TooltipProps): JSX.Element {
  const { content, side = "top", children } = props;
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const sideClass = side === "top" ? "" : " ui-tooltip-side-" + side;

  const trigger = isValidElement(children)
    ? cloneElement(children as ReactElement<Record<string, unknown>>, {
        "aria-describedby": id,
      })
    : children;

  return (
    <span className="ui-tooltip-wrap">
      {trigger}
      <span role="tooltip" id={id} className={"ui-tooltip" + sideClass}>
        {content}
      </span>
    </span>
  );
}
