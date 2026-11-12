/**
 * Sparkline — a tiny inline SVG line, optionally filled, used inside dense
 * surfaces (metric cards, table cells, status dots). Zero dependencies; the
 * stroke color is the current text color so it inherits from the parent. There
 * is no animation (it is meant to be a quiet background signal), which also
 * keeps it cheap to render in long lists.
 */
interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
  color?: string;
  fill?: boolean;
  className?: string;
  ariaLabel?: string;
}

export function Sparkline({
  values,
  width = 96,
  height = 28,
  color = "currentColor",
  fill = false,
  className,
  ariaLabel,
}: SparklineProps): JSX.Element {
  if (values.length === 0) {
    return <span className={className} aria-label={ariaLabel || "empty"} />;
  }
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const span = Math.max(1, max - min);
  const stepX = values.length > 1 ? width / (values.length - 1) : 0;
  const coords = values.map((v, i) => ({
    x: i * stepX,
    y: height - ((v - min) / span) * (height - 4) - 2,
  }));
  const line = coords.map((c, i) => `${i === 0 ? "M" : "L"} ${c.x.toFixed(2)} ${c.y.toFixed(2)}`).join(" ");
  const area = `${line} L ${width} ${height} L 0 ${height} Z`;

  return (
    <svg
      className={className}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={ariaLabel || "sparkline"}
    >
      {fill && <path d={area} fill={color} fillOpacity={0.12} stroke="none" />}
      <path d={line} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}
