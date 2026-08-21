import { useEffect, useState } from "react";
import { AgentEvent } from "../../api";
import { Empty, ErrorBox, Panel, Spinner } from "../../ui";
import { AgentJobShell, useAgentJob } from "../components";

// The full event log is replayed over SSE from seq 0; the stream closes
// itself with "done" once the job is terminal, so the page drains the
// complete history in one pass.
async function collectEvents(jobId: string, onEvent: (ev: AgentEvent) => void): Promise<void> {
  const { getApiKey, apiBase } = await import("../../api");
  const url =
    apiBase() + "/agent/jobs/" + encodeURIComponent(jobId) + "/events?key=" +
    encodeURIComponent(getApiKey());
  const resp = await fetch(url, { headers: { Accept: "text/event-stream" } });
  if (!resp.ok) throw new Error("event stream unavailable: " + resp.status);
  if (!resp.body) return;
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const dataLine = frame.split("\n").find((l) => l.startsWith("data: "));
      if (!dataLine) continue;
      try {
        const ev = JSON.parse(dataLine.slice(6)) as AgentEvent;
        if (ev.seq) onEvent(ev);
      } catch {
        // skip malformed frames
      }
    }
  }
}

export default function AgentEventLog(props: { jobId: string }) {
  const { jobId } = props;
  const { job, error, loading } = useAgentJob(jobId);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(true);

  useEffect(() => {
    let alive = true;
    const onEvent = (ev: AgentEvent) => {
      if (alive) setEvents((prev) => [...prev, ev]);
    };
    collectEvents(jobId, onEvent)
      .catch((e) => {
        if (alive) setStreamError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (alive) setStreaming(false);
      });
    return () => {
      alive = false;
    };
  }, [jobId]);

  if (loading) return <Spinner />;
  if (!job) {
    return (
      <div>
        <ErrorBox error={error || "任务不存在 (404)"} />
        <a href="#/agent">← 返回 Agent 总览</a>
      </div>
    );
  }

  return (
    <AgentJobShell job={job} active="events">
      <Panel
        title={
          "事件日志 Event log (" +
          events.length +
          " / " +
          job.events_count +
          (streaming ? " · 拉取中…" : " · 已同步") +
          ")"
        }
      >
        {streamError ? <div className="errorbox">{streamError}</div> : null}
        {events.length === 0 ? (
          <Empty text="无事件 (任务尚未产生任何事件 — 诚实空态)" />
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Seq</th>
                <th>类型</th>
                <th>时间</th>
                <th>内容</th>
              </tr>
            </thead>
            <tbody>
              {events.map((ev) => (
                <tr key={ev.seq}>
                  <td className="mono">#{ev.seq}</td>
                  <td className="mono">{ev.type}</td>
                  <td className="mono muted">{ev.at}</td>
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
