import { Empty, ErrorBox, Panel, Spinner, fmtTime } from "../../ui";
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
          <table className="data">
            <thead>
              <tr>
                <th>序号 Seq</th>
                <th>类型</th>
                <th>时间</th>
                <th>内容</th>
              </tr>
            </thead>
            <tbody>
              {events.map((ev) => (
                <tr key={ev.seq}>
                  <td className="mono">#{ev.seq}</td>
                  <td className="mono" title={ev.type}>{eventKindLabel(ev.type)}</td>
                  <td className="mono muted" title={ev.at}>{fmtTime(ev.at)}</td>
                  <td className="mono" style={{ wordBreak: "break-all" }}>
                    {JSON.stringify(ev.data)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </AgentJobShell>
  );
}
