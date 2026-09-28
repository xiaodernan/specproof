import { Empty, ErrorBox, Panel, Spinner, Table, fmtTime } from "../../ui";
import { AgentJobShell, useAgentJob } from "../components";
import { eventKindLabel } from "../util";

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
        <ErrorBox error={error || "任务不存在 (404)"} />
        <a href="#/agent">← 返回 Agent 总览</a>
      </div>
    );
  }

  const events = liveEvents.filter((ev) => ev.seq);
  const synced = streamState === "closed";

  return (
    <AgentJobShell job={job} active="events">
      <Panel
        title={
          "事件日志 Event log (" +
          events.length +
          " / " +
          job.events_count +
          (synced ? " · 已同步" : " · 实时更新中…") +
          ")"
        }
      >
        {streamState === "error" ? (
          <div className="errorbox">实时事件连接暂时中断，系统正在自动重连。</div>
        ) : null}
        {events.length === 0 ? (
          <Empty text="无事件 (任务尚未产生任何事件 — 诚实空态)" />
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
                header: "序号 Seq",
                width: 90,
                render: (ev) => <span className="mono">#{ev.seq}</span>,
              },
              {
                key: "type",
                header: "类型",
                render: (ev) => (
                  <span className="mono" title={ev.type}>
                    {eventKindLabel(ev.type)}
                  </span>
                ),
              },
              {
                key: "at",
                header: "时间",
                render: (ev) => (
                  <span className="mono muted" title={ev.at}>
                    {fmtTime(ev.at)}
                  </span>
                ),
              },
              {
                key: "data",
                header: "内容",
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
