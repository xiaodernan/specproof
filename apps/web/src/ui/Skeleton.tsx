import type { CSSProperties } from "react";

export interface SkeletonProps {
  variant?: "text" | "rect" | "circle";
  width?: number | string;
  height?: number | string;
  count?: number;
  className?: string;
}

export function Skeleton(props: SkeletonProps): JSX.Element {
  const { variant = "text", width, height, count = 1, className } = props;
  const style: CSSProperties = {};
  if (width !== undefined) style.width = typeof width === "number" ? width + "px" : width;
  if (height !== undefined) style.height = typeof height === "number" ? height + "px" : height;
  const cls = "ui-skeleton ui-skeleton-" + variant + (className ? " " + className : "");
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <span key={i} className={cls} style={style} aria-hidden="true" />
      ))}
    </>
  );
}
