import { useI18n } from "../i18n";
import { ProductIcon } from "../ui/ProductIcon";
import inkwell from "./inkwell.json";
import "../styles/inkwell.css";

/**
 * The Inkwell — how this repository writes itself.
 * Counts, streaks, hourly ink-clock, prefix census. Read straight from
 * inkwell.json (git log, author offset). No author names, no addresses —
 * this page practises rhythm, never blame.
 */

interface InkwellData {
  commits: number;
  first: string;
  last: string;
  span_days: number;
  hours_local: number[];
  weekdays: number[];
  weeks52: number[];
  longest_day_streak: number;
  longest_quiet_days: number;
  prefixes: Record<string, number>;
}

const D = inkwell as unknown as InkwellData;
const WEEKDAY_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"] as const;
const WEEKDAY_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] as const;

export default function Inkwell(): JSX.Element {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const L = (a: string, b: string): string => (zh ? a : b);

  const night = D.hours_local[22] + D.hours_local[23] + D.hours_local[0] + D.hours_local[1] + D.hours_local[2] + D.hours_local[3] + D.hours_local[4] + D.hours_local[5];
  const nightPct = ((night / D.commits) * 100).toFixed(0);
  const weekend = D.weekdays[5] + D.weekdays[6];
  const weekendPct = ((weekend / D.commits) * 100).toFixed(0);
  const maxHour = Math.max(...D.hours_local);
  const maxWeek = Math.max(...D.weeks52);
  const maxWeekday = Math.max(...D.weekdays);
  const maxPrefix = Math.max(...Object.values(D.prefixes));
  const prefixEntries = Object.entries(D.prefixes).sort((a, b) => b[1] - a[1]);

  // hourly ink-clock geometry
  const R = 104, cx = 150, cy = 150;
  // hour theta: 0h at top, clockwise, each hour spans 15°
  const theta = (deg: number) => (deg * Math.PI) / 180;
  const pt = (r: number, deg: number) => ({ x: cx + r * Math.sin(theta(deg)), y: cy - r * Math.cos(theta(deg)) });
  const slicePath = (hour: number) => {
    const per = 360 / 24;
    const a0 = hour * per;
    const a1 = (hour + 1) * per;
    const depth = D.hours_local[hour] / maxHour;
    const rIn = R * 0.36;
    const rOut = rIn + (R - rIn) * depth;
    const p0 = pt(rIn, a0), p1 = pt(rOut, a0), p2 = pt(rOut, a1), p3 = pt(rIn, a1);
    return `M ${p0.x.toFixed(2)} ${p0.y.toFixed(2)} L ${p1.x.toFixed(2)} ${p1.y.toFixed(2)} A ${rOut.toFixed(2)} ${rOut.toFixed(2)} 0 0 1 ${p2.x.toFixed(2)} ${p2.y.toFixed(2)} L ${p3.x.toFixed(2)} ${p3.y.toFixed(2)} A ${rIn.toFixed(2)} ${rIn.toFixed(2)} 0 0 0 ${p0.x.toFixed(2)} ${p0.y.toFixed(2)} Z`;
  };

  return (
    <div className="inkwell-page">
      <header className="inkwell-mast">
        <p className="inkwell-kicker">{L("仓 库 的 墨 水 池", "HOW THIS REPOSITORY WRITES ITSELF")}</p>
        <h1>{L("墨水池", "The Inkwell")} <span className="inkwell-en">{L("THE INKWELL · NO NAMES, ONLY RHYTHM", "墨 水 池 · 只 看 手 腕,不 看 姓 名")}</span></h1>
        <p className="inkwell-lead">
          {L(
            "本页只讲这本仓库怎么写自己——写了多少笔、什么时辰浇墨、哪些格式占下话语权。没有一个名字，没有一封邮箱；名字属于他人，墨迹才属于所有人。",
            "This page is about how this repository writes itself — how many strokes were laid, at which hours the ink was poured, which prefixes hold the floor. No names, no addresses: names belong to others; ink belongs to everyone.",
          )}
        </p>
        <div className="inkwell-kpis">
          <div className="inkwell-kpi"><p className="inkwell-kpi-v">{D.commits.toLocaleString()}</p><p className="inkwell-kpi-l">{L("总提交", "total commits")}</p></div>
          <div className="inkwell-kpi"><p className="inkwell-kpi-v">{D.span_days}</p><p className="inkwell-kpi-l">{L("天跨度", "days span")}</p></div>
          <div className="inkwell-kpi"><p className="inkwell-kpi-v">{D.longest_day_streak}</p><p className="inkwell-kpi-l">{L("最长连写（天）", "longest streak (days)")}</p></div>
          <div className="inkwell-kpi"><p className="inkwell-kpi-v">{D.longest_quiet_days}</p><p className="inkwell-kpi-l">{L("最长沉没（天）", "longest quiet spell (days)")}</p></div>
          <div className="inkwell-kpi"><p className="inkwell-kpi-v">{nightPct}%</p><p className="inkwell-kpi-l">{L("深夜下墨（22–06 时）", "ink laid 22:00–06:00")}</p></div>
          <div className="inkwell-kpi"><p className="inkwell-kpi-v">{weekendPct}%</p><p className="inkwell-kpi-l">{L("周末下墨", "ink on weekends")}</p></div>
        </div>
      </header>

      <div className="inkwell-grid">
        {/* ── 24-hour ink clock ─────────────────────────────── */}
        <section className="inkwell-panel inkwell-clock-panel" aria-label={L("时辰墨盘", "Ink clock")}>
          <h2>{L("时辰墨盘 · 一天 24 小时的墨深", "The Ink Clock — 24 hours deep")}</h2>
          <svg viewBox="0 0 300 300" className="inkwell-clock" role="img" aria-label={L("24 小时提交密度环形图", "24-hour commit density ring")}>
            <circle cx={cx} cy={cy} r="40" fill="none" stroke="var(--pigment-veil-5)" strokeWidth="1.5" />
            {D.hours_local.map((_, hour) => (
              <path key={hour} d={slicePath(hour)} fill={hour >= 22 || hour < 6 ? "var(--pigment-gilt-47)" : "var(--pigment-gilt-48)"} opacity={0.28 + 0.72 * (D.hours_local[hour] / maxHour)} />
            ))}
            {[0, 6, 12, 18].map((h) => {
              const p = pt(128, h * 15);
              return <text key={h} x={p.x} y={p.y} textAnchor="middle" dominantBaseline="middle" className="inkwell-clock-label">{zh ? `${h}时` : `${h}:00`}</text>;
            })}
            <text x={cx} y={cy - 4} textAnchor="middle" className="inkwell-clock-center-v">{nightPct}%</text>
            <text x={cx} y={cy + 14} textAnchor="middle" className="inkwell-clock-center-l">{L("深夜", "overnight")}</text>
          </svg>
          <p className="inkwell-footnote">{L("深琥珀 = 22:00–06:00，淡棕 = 白昼。每根墨条长度正比于该时段的提交密度。", "deep amber = 22:00–06:00; tan = daytime. Each wedge scales with its hour's commit density.")}</p>
        </section>

        {/* ── weekday census ─────────────────────────────────── */}
        <section className="inkwell-panel inkwell-weekday-panel">
          <h2>{L("星期密度 · 七天墨量", "Weekday Census — seven kinds of ink")}</h2>
          <ol className="inkwell-weekdays">
            {D.weekdays.map((n, i) => (
              <li key={i} className="inkwell-weekday-row">
                <span className="inkwell-weekday-name">{(zh ? WEEKDAY_ZH : WEEKDAY_EN)[i]}</span>
                <div className="inkwell-weekday-track"><div className="inkwell-weekday-fill" style={{ width: `${(n / maxWeekday) * 100}%` }} /></div>
                <span className="inkwell-weekday-n">{n}</span>
              </li>
            ))}
          </ol>
          <p className="inkwell-footnote">{L("不是「哪一天好」，是「哪一天下笔更多」。本仓库的墨，一半落在周六。", "Not which day is good — which day lays more ink. Half of this repository's ink lands on Saturday.")}</p>
        </section>

        {/* ── 52-week rhythm ─────────────────────────────────── */}
        <section className="inkwell-panel inkwell-weeks-panel">
          <h2>{L("52 周潮汐 · 每周的墨量落起", "52-Week Tide — weekly ink")}</h2>
          <div className="inkwell-weeks" role="img" aria-label={L("52 周提交量变柱图", "52-week commit histogram")}>
            {D.weeks52.map((n, i) => (
              <div key={i} className="inkwell-week" style={{ height: `${Math.max(3, (n / maxWeek) * 100)}%` }} title={`W${i + 1}: ${n}`} />
            ))}
          </div>
          <p className="inkwell-swing">{L("峰值周", "peak week")} <strong>{maxWeek}</strong> · {L("沉寂周", "trough week")} <strong>{Math.min(...D.weeks52)}</strong> · {L("均值", "mean")} <strong>{(D.commits / 52).toFixed(0)}</strong>/{L("周", "week")}</p>
        </section>

        {/* ── prefix census ──────────────────────────────────── */}
        <section className="inkwell-panel inkwell-prefix-panel">
          <h2>{L("话语权普查 · 提交类型前缀", "Prefix Census — where the floor goes")}</h2>
          <ol className="inkwell-prefixes">
            {prefixEntries.map(([tag, n]) => (
              <li key={tag} className="inkwell-prefix-row">
                <code className="inkwell-prefix-tag">{tag}</code>
                <div className="inkwell-prefix-track"><div className="inkwell-prefix-fill" style={{ width: `${(n / maxPrefix) * 100}%` }} /></div>
                <span className="inkwell-prefix-n">{n}</span>
              </li>
            ))}
          </ol>
        </section>
      </div>

      <footer className="inkwell-honesty">
        <ProductIcon name="shield" size={13} />
        <p>
          {zh
            ? "本页不出现任何作者的姓名或邮箱（含本仓库主人与任何协作者）——它只读 git 审计、只算节奏，不替你评判任何人。按提交者自己的时区（git 审计记录）计算深夜、周末等概念；这些概念不构成任何考核、排名或绩效证据。数字来自 scripts/build_inkwell.py 对 git log 的当场清点，不是估计。"
            : "No author name or email appears anywhere here (including the owner's and any collaborator's) — it reads git audit only, counts rhythm, and passes no judgment on anyone. Overnight/weekend are computed in the COMMITTER'S timezone per git audit; they are never review, ranking or performance evidence. Figures come from scripts/build_inkwell.py's live count of git log — nothing is estimated."}
        </p>
      </footer>
    </div>
  );
}
