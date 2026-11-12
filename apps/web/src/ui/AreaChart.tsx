import { useId } from "react";

/**
 * AreaChart — a dependency-free, theme-aware SVG area chart with a smooth
 * (Catmull-Rom → cubic Bézier) line, gradient fill, gridlines and a draw-in
 * animation. The line "draws" using the SVG `pathLength="1"` normalization so
 * the dash animation is resolution-independent; the whole animation is disabled
 * under prefers-reduced-motion (see viz.css). Each data point carries a native
 * <title> so hovering reveals its exact value without custom JS tooltips.
 */
export interface AreaChartPoint {
  label: string;
  value: number;
  /** Optional secondary detail shown in the hover title, e.g. "失败 3 次". */
  meta?: string;
}

interface AreaChartProps {
  data: AreaChartPoint[];
  /** viewBox height in user units; width is normalized to 1000. */
  height?: number;
  className?: string;
  ariaLabel?: string;
  formatValue?: (n: number) => string;
  emptyHint?: string;
}

const W = 1000;
const PAD_X = 12;
const PAD_Y = 14;

function buildSmoothPath(pts: { x: number; y: number }[]): string {
  if (pts.length === 0) return "";
  if (pts.length === 1) return `M ${pts[0].x} ${pts[0].y}`;
  let d = `M ${pts[0].x} ${pts[0].y}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] ?? pts[i];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[i + 2] ?? p2;
    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = p1.y + (p2.y - p0.y) / 6;
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = p2.y - (p3.y - p1.y) / 6;
    d += ` C ${cp1x.toFixed(2)} ${cp1y.toFixed(2)}, ${cp2x.toFixed(2)} ${cp2y.toFixed(2)}, ${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`;
  }
  return d;
}

export function AreaChart({
  data,
  height = 220,
  className,
  ariaLabel,
  formatValue,
  emptyHint = "暂无数据",
}: AreaChartProps): JSX.Element {
  const gradId = useId().replace(/:/g, "");
  if (data.length === 0) {
    return (
      <div className={"viz-empty" + (className ? " " + className : "")} role="img" aria-label={ariaLabel || emptyHint}>
        {emptyHint}
      </div>
    );
  }

  const H = height;
  const maxV = Math.max(1, ...data.map((d) => d.value));
  const stepX = data.length > 1 ? (W - 2 * PAD_X) / (data.length - 1) : 0;
  const coords = data.map((d, i) => ({
    x: PAD_X + i * stepX,
    y: H - PAD_Y - (d.value / maxV) * (H - 2 * PAD_Y),
    point: d,
  }));

  const linePath = buildSmoothPath(coords);
  const areaPath =
    linePath +
    ` L ${coords[coords.length - 1].x.toFixed(2)} ${H - PAD_Y} L ${coords[0].x.toFixed(2)} ${H - PAD_Y} Z`;

  const fmt = formatValue ?? ((n: number) => String(n));
  const gridLines = [0.25, 0.5, 0.75];

  return (
    <svg
      className={"viz-area" + (className ? " " + className : "")}
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={ariaLabel || "趋势图"}
    >
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--accent-500)" stopOpacity="0.40" />
          <stop offset="100%" stopColor="var(--accent-2-400)" stopOpacity="0.02" />
        </linearGradient>
      </defs>

      {gridLines.map((g) => (
        <line
          key={g}
          className="viz-grid"
          x1={PAD_X}
          x2={W - PAD_X}
          y1={PAD_Y + g * (H - 2 * PAD_Y)}
          y2={PAD_Y + g * (H - 2 * PAD_Y)}
        />
      ))}

      <path className="viz-area-fill" d={areaPath} fill={`url(#${gradId})`} />
      <path className="viz-area-line" d={linePath} pathLength={1} fill="none" />

      {coords.map((c, i) => (
        <circle key={i} className="viz-dot" cx={c.x} cy={c.y} r={4}>
          <title>
            {c.point.label}
            {" · "}
            {fmt(c.point.value)}
            {c.point.meta ? `（${c.point.meta}）` : ""}
          </title>
        </circle>
      ))}
    </svg>
  );
}
