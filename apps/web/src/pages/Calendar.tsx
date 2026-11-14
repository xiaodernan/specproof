import { useMemo } from "react";
import { useI18n } from "../i18n";
import calendar from "./calendarData.json";
import { ProductIcon } from "../ui/ProductIcon";
import "../styles/calendar.css";

/**
 * The Evidence Calendar — one year of this repository, cell by cell.
 *
 * Every square is a day; every number behind a color is a git commit count,
 * re-derived by scripts/build_calendar.py from `git log --date=short`.
 * The grid is not decorative volume; each cell links nothing, hides nothing,
 * and forgets nothing. Hover or focus any cell to read its date and count.
 */

const WEEKDAY_LABEL = { zh: ["一", "二", "三", "四", "五", "六", "日"], en: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] } as const;

function bucketIndex(count: number): number {
  if (count === 0) return 0;
  if (count < 3) return 1;
  if (count < 6) return 2;
  if (count < 12) return 3;
  return 4;
}

export default function Calendar() {
  const { locale } = useI18n();
  const zh = locale === "zh";

  const weeks = useMemo(() => {
    const days = calendar.days as Record<string, number>;
    const firstIso = Object.keys(days)[0];
    const first = new Date(firstIso + "T00:00:00");
    // Monday-first alignment: pad leading days from the previous week's tail.
    const pad = (first.getDay() + 6) % 7;
    const cells: ({ date: string; count: number } | null)[] = Array.from({ length: pad }, () => null);
    for (const [date, count] of Object.entries(days)) cells.push({ date, count });
    const cols: (typeof cells)[] = [];
    for (let i = 0; i < cells.length; i += 7) cols.push(cells.slice(i, i + 7));
    return cols;
  }, []);

  const total = calendar.total_commits;
  const busiest = `${calendar.busiest_date} · ${calendar.busiest_count} ${zh ? "次" : ""}`;
  const activeDays = Object.values(calendar.days as Record<string, number>).filter((n) => n > 0).length;

  const monthNames = useMemo(() => {
    const seen = new Map<string, number>();
    (weeks as unknown as ({ date: string } | null)[][]).forEach((col, i) => {
      const first = col.find((c) => c);
      if (first) {
        const m = first.date.slice(0, 7);
        if (!seen.has(m)) seen.set(m, i);
      }
    });
    return [...seen.entries()];
  }, [weeks]);

  return (
    <div className="calendar-page">
      <div className="page-head">
        <h1>
          {zh ? "铁证日历" : "The Evidence Calendar"}{" "}
          <span className="calendar-en">{zh ? "THE EVIDENCE CALENDAR" : "铁证日历"}</span>
        </h1>
        <div className="page-sub">
          {zh
            ? "这一年每一格都是一天，每一横都是一次提交。没有插值、没有估算——Git 说了算。"
            : "Every cell is a day; every stroke is a commit. No interpolation, no estimation — git has the final word."}
        </div>
      </div>

      <div className="calendar-legend-row" aria-hidden="true">
        <span className="calendar-legend-cap">{zh ? "少" : "Less"}</span>
        {[0, 1, 2, 3, 4].map((b) => (
          <span key={b} className={`calendar-swatch calendar-bucket-${b}`} />
        ))}
        <span className="calendar-legend-cap">{zh ? "多" : "More"}</span>
        <span className="calendar-count-note">
          {zh ? `${calendar.since} 至 ${calendar.until} · git log 现推` : `${calendar.since} → ${calendar.until} · derived live from git log`}
        </span>
      </div>

      <div className="calendar-scroll">
        <div className="calendar-grid" role="grid" aria-label={zh ? "提交日历" : "Commit calendar"}>
          <div className="calendar-months" style={{ gridTemplateColumns: `repeat(${weeks.length}, 16px)` }}>
            {monthNames.map(([m, i]) => (
              <span key={m} className="calendar-month" style={{ gridColumn: `${i + 1} / span 1` }}>{m.slice(5)}</span>
            ))}
          </div>
          <div className="calendar-body">
            <div className="calendar-dows" aria-hidden="true">
              {WEEKDAY_LABEL[locale].map((d, i) => (
                <span key={i} className="calendar-dow">{d}</span>
              ))}
            </div>
            {(weeks as ({ date: string; count: number } | null)[][]).map((col, i) => (
              <div key={i} className="calendar-week" role="row">
                {col.map((cell, j) =>
                  cell ? (
                    <div
                      key={cell.date}
                      role="gridcell"
                      tabIndex={0}
                      className={`calendar-cell calendar-bucket-${bucketIndex(cell.count)}`}
                      aria-label={`${cell.date}: ${cell.count} ${zh ? "次提交" : "commits"}`}
                      data-count={cell.count}
                    >
                      <span className="calendar-tip">{cell.date} · {cell.count} {zh ? "次" : "commit"}{cell.count === 1 ? "" : (zh ? "" : "s")}</span>
                    </div>
                  ) : (
                    <div key={i + "-" + j} className="calendar-cell is-empty" aria-hidden="true" />
                  ),
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="calendar-stats">
        <div className="calendar-stat">
          <p className="calendar-stat-num">{total.toLocaleString()}</p>
          <p className="calendar-stat-label">{zh ? "这一年的提交" : "commits this year"}</p>
        </div>
        <div className="calendar-stat">
          <p className="calendar-stat-num">{activeDays.toLocaleString()}</p>
          <p className="calendar-stat-label">{zh ? "有提交的日子" : "days with a commit"}</p>
        </div>
        <div className="calendar-stat">
          <p className="calendar-stat-num">{String(busiest)}</p>
          <p className="calendar-stat-label">{zh ? "最忙的一天（合入波峰）" : "busiest day (merge wave)"}</p>
        </div>
        <div className="calendar-stat">
          <p className="calendar-stat-num">{calendar.longest_streak}</p>
          <p className="calendar-stat-label">{zh ? "连续有提交的天数" : "longest daily streak"}</p>
        </div>
      </div>
      <p className="calendar-footnote">
        <ProductIcon name="calendar" size={14} />{" "}
        {zh
          ? "本页由 scripts/build_calendar.py 基于 git log 现推；任何合并提交都会让它变旧——重跑一次就新。"
          : "This page is re-derived by scripts/build_calendar.py from git log — every merge ages it; one re-run refreshes it."}
      </p>
    </div>
  );
}
