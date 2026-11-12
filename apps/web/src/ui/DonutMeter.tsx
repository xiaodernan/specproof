/**
 * DonutMeter — a dependency-free SVG donut for a small composition (e.g. the
 * verified / blocked / running / failed split of a verification workspace). Each
 * segment is normalized to `pathLength="1"` so every arc is a unitless fraction
 * of the ring; segments sweep in with a staggered dashoffset animation that is
 * disabled under prefers-reduced-motion. Colors are passed as CSS color values
 * (a literal or `var(--success)`), so the ring re-tints with the theme.
 */
export interface DonutSegment {
  label: string;
  value: number;
  /** Any CSS color: a literal hex or a token like "var(--success)". */
  color: string;
}

interface DonutMeterProps {
  segments: DonutSegment[];
  size?: number;
  thickness?: number;
  centerLabel?: string;
  centerValue?: string | number;
  className?: string;
  ariaLabel?: string;
  emptyHint?: string;
}

export function DonutMeter({
  segments,
  size = 168,
  thickness = 18,
  centerLabel,
  centerValue,
  className,
  ariaLabel,
  emptyHint = "暂无数据",
}: DonutMeterProps): JSX.Element {
  const total = segments.reduce((s, seg) => s + Math.max(0, seg.value), 0);

  if (total <= 0 || segments.length === 0) {
    return (
      <div className={"viz-empty" + (className ? " " + className : "")} role="img" aria-label={ariaLabel || emptyHint}>
        {emptyHint}
      </div>
    );
  }

  const cx = size / 2;
  const cy = size / 2;
  const r = (size - thickness) / 2;

  let cumulative = 0; // 0..1
  const arcs = segments
    .filter((s) => s.value > 0)
    .map((s, i) => {
      const fraction = Math.max(0, s.value) / total;
      const startAngle = cumulative * 360 - 90; // -90 so the first segment starts at 12 o'clock
      cumulative += fraction;
      return { fraction, startAngle, color: s.color, label: s.label, value: s.value, index: i };
    });

  return (
    <div className={"viz-donut" + (className ? " " + className : "")} role="img" aria-label={ariaLabel || "构成"}>
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size}>
        <circle className="viz-donut-track" cx={cx} cy={cy} r={r} fill="none" strokeWidth={thickness} />
        {arcs.map((a) => (
          <circle
            key={a.label}
            className="viz-donut-arc"
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke={a.color}
            strokeWidth={thickness}
            strokeLinecap="round"
            pathLength={1}
            strokeDasharray={`${a.fraction} ${1 - a.fraction}`}
            transform={`rotate(${a.startAngle} ${cx} ${cy})`}
            style={{ ["--arc" as string]: a.fraction, animationDelay: `${a.index * 120}ms` }}
          >
            <title>
              {a.label}：{a.value}（{Math.round(a.fraction * 100)}%）
            </title>
          </circle>
        ))}
        {(centerValue !== undefined || centerLabel) && (
          <g>
            {centerValue !== undefined && (
              <text className="viz-donut-value" x={cx} y={cy - 2} textAnchor="middle">
                {centerValue}
              </text>
            )}
            {centerLabel && (
              <text className="viz-donut-label" x={cx} y={cy + (centerValue !== undefined ? 16 : 4)} textAnchor="middle">
                {centerLabel}
              </text>
            )}
          </g>
        )}
      </svg>
      <ul className="viz-legend">
        {arcs.map((a) => (
          <li key={a.label}>
            <span className="viz-legend-dot" style={{ background: a.color }} />
            <span className="viz-legend-label">{a.label}</span>
            <span className="viz-legend-value">{a.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
