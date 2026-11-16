import { Empty, ErrorBox, Panel, Spinner, Table, fmtTime } from "../../ui";
import { AgentJobShell, useAgentJob } from "../components";
import { eventKindLabel } from "../util";
import { storedLocale } from "../../i18n/strings";
const isZh = (): boolean => storedLocale() === "zh";
const L = (zh: string, en: string): string => (isZh() ? zh : en);

export default function AgentEventLog(props: { jobId: string }) {
  const { jobId } = props;
  // Same single realtime channel as the verification detail page: `useAgentJob`
  // replays the full log from seq 0 over the shared SSE stream and stops on the
  // server's terminal "done" event. No second, weaker fetch-with-?key stream here.
  const { job, error, loading, events: liveEvents, streamState } = useAgentJob(jobId);

  if (loading) return <Spinner />;
  if (!job) {
    return (
      <div>
        <ErrorBox error={error || L("任务不存在（404）", "Task not found (404)")} />
        <a href="#/agent">{L("← 返回 Agent 总览", "← Back to Agent overview")}</a>
      </div>
    );
  }

  const events = liveEvents.filter((ev) => ev.seq);
  const synced = streamState === "closed";

  return (
    <AgentJobShell job={job} active="events">
      <Panel
        title={
          L("事件日志", "Event log") + " (" +
          events.length +
          " / " +
          job.events_count +
          (synced ? L(" · 已同步", " · synced") : L(" · 实时更新中…", " · live…")) +
          ")"
        }
      >
        {streamState === "error" ? (
          <div className="errorbox">{L("实时事件连接暂时中断，系统正在自动重连…", "The live event connection dropped; reconnecting…")}</div>
        ) : null}
        {events.length === 0 ? (
          <Empty text={L("无事件（任务尚未产生任何事件——诚实空态）", "No events yet (the task has not produced any — honest empty state).")} />
        ) : (
          // Through the shared table (#122): the payload column is arbitrary
          // server JSON, and `.ui-table-wrap` scrolls it inside the panel
          // instead of letting one long value widen the page.
          <Table
            rows={events}
            rowKey={(ev) => String(ev.seq)}
            columns={[
              {
                key: "seq",
                header: L("序号", "Seq"),
                width: 90,
                render: (ev) => <span className="mono">#{ev.seq}</span>,
              },
              {
                key: "type",
                header: L("类型", "Type"),
                render: (ev) => (
                  <span className="mono" title={ev.type}>
                    {eventKindLabel(ev.type)}
                  </span>
                ),
              },
              {
                key: "at",
                header: L("时间", "Time"),
                render: (ev) => (
                  <span className="mono muted" title={ev.at}>
                    {fmtTime(ev.at)}
                  </span>
                ),
              },
              {
                key: "data",
                header: L("内容", "Content"),
                render: (ev) => (
                  <span className="mono" style={{ wordBreak: "break-all" }}>
                    {JSON.stringify(ev.data)}
                  </span>
                ),
              },
            ]}
          />
        )}
      </Panel>
    </AgentJobShell>
  );
}
