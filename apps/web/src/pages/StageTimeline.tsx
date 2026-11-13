// 执行阶段时间线（Phase 3.1 观测可视化）：把 /stages 的 started_at +
// duration_seconds 画成比例条——时间花在哪一眼可见。没有时间戳的阶段
// （Redis 流丢帧、旧数据）不进入条形区，而是在下方如实列出：绝不编造
// 一个位置来填满图表。
import { Empty } from "../ui";

interface StageRow {
  node: string;
  status?: string | null;
  started_at?: string | null;
  duration_seconds?: number | null;
}

function parseMs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : null;
}

const fmtClock = (ms: number): string =>
  new Date(ms).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export function stageSpans(rows: StageRow[]): Array<{
  node: string;
  status: string;
  startMs: number;
  endMs: number;
  durationSeconds: number;
}> {
  const spans: Array<{
    node: string;
    status: string;
    startMs: number;
    endMs: number;
    durationSeconds: number;
  }> = [];
  for (const row of rows) {
    const startMs = parseMs(row.started_at);
    const seconds = row.duration_seconds;
    if (startMs === null || typeof seconds !== "number" || seconds < 0) {
      continue;
    }
    const endMs = startMs + seconds * 1000;
    spans.push({
      node: row.node,
      status: row.status || "",
      startMs,
      endMs,
      durationSeconds: seconds,
    });
  }
  return spans.sort((a, b) => a.startMs - b.startMs || a.node.localeCompare(b.node));
}

// 一行要么被画进条形区，要么被如实列为跳过——按行计数，绝不
// 借同名节点"遮住"一条自己没有时间戳的记录。
export function skippableRows(rows: StageRow[]): StageRow[] {
  return rows.filter((r) => {
    const startMs = parseMs(r.started_at);
    return startMs === null
      || typeof r.duration_seconds !== "number"
      || r.duration_seconds < 0;
  });
}

export function StageTimeline(props: { stages?: StageRow[] | null }) {
  const rows = props.stages ?? [];
  const spans = stageSpans(rows);
  const skipped = skippableRows(rows);
  if (rows.length === 0) return null;
  if (spans.length === 0) {
    return (
      <Empty text="阶段没有可解析的时间戳，无法绘制时间线——下方列表仍是完整事实。" />
    );
  }
  const windowStart = Math.min(...spans.map((s) => s.startMs));
  const windowEnd = Math.max(...spans.map((s) => s.endMs));
  const spanMs = Math.max(1, windowEnd - windowStart);
  const toneClass = (status: string): string => {
    const upper = status.toUpperCase();
    if (upper === "FAILED") return "stage-bar-failed";
    if (upper === "VERIFIED" || upper === "COMPLETED" || upper === "PASS") {
      return "stage-bar-done";
    }
    return "stage-bar-run";
  };
  return (
    <div className="stage-timeline" role="img" aria-label="执行阶段时间线">
      <div className="stage-timeline-track">
        {spans.map((s) => {
          const left = ((s.startMs - windowStart) / spanMs) * 100;
          const width = Math.max(1.5, ((s.endMs - s.startMs) / spanMs) * 100);
          // 端点钉形：最后一个阶段若落在时间轴右端，不能让 overflow:hidden
          // 把它整根吃掉——至少能露出它真实存在的事实。
          const clamped = Math.min(left, Math.max(0, 100 - width));
          return (
            <div
              key={s.node + String(s.startMs)}
              className={"stage-timeline-bar " + toneClass(s.status)}
              style={{ left: clamped + "%", width: width + "%" }}
              title={
                s.node +
                " · " +
                s.durationSeconds.toFixed(2) +
                "s · " +
                new Date(s.startMs).toLocaleTimeString()
              }
            />
          );
        })}
      </div>
      <div className="stage-timeline-scale" aria-hidden="true">
        <span>{fmtClock(windowStart)}</span>
        <span>窗口 {(spanMs / 1000).toFixed(2)}s</span>
        <span>{fmtClock(windowEnd)}</span>
      </div>
      <div className="stage-timeline-list">
        {spans.map((s) => (
          <div key={"label-" + s.node + String(s.startMs)} className="stage-timeline-row">
            <span className="stage-timeline-node">{s.node}</span>
            <span className="stage-timeline-dur">{s.durationSeconds.toFixed(2)}s</span>
          </div>
        ))}
      </div>
      {skipped.length > 0 ? (
        <p className="muted">
          {skipped.length} 个阶段没有可解析的时间戳，未进入条形区（诚实省略）。
        </p>
      ) : null}
    </div>
  );
}
