import { useEffect, useRef, useState } from "react";
import { AgentEvent, getAgentJob, openAgentEventStream } from "../../api";
import { ErrorBox, Panel, Spinner } from "../../ui";
import { AgentJobShell, EventRow, useAgentJob } from "../components";
import { eventKindLabel } from "../util";

function useToolEvents(jobId: string) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [sseState, setSseState] = useState<string>("closed");
  const [done, setDone] = useState(false);
  const bufferRef = useRef<AgentEvent[]>([]);

  useEffect(() => {
    let alive = true;
    getAgentJob(jobId)
      .then((d) => {
        if (alive) setDone(["COMPLETED", "FAILED", "CANCELLED"].includes(d.job.status));
      })
      .catch(() => {
        // done-state snapshot is best effort; the stream stays the truth
      });
    const close = openAgentEventStream(
      jobId,
      (ev) => {
        if (!alive) return;
        bufferRef.current = [...bufferRef.current.slice(-299), ev];
        setEvents(bufferRef.current);
      },
      (state) => {
        if (alive) setSseState(state);
      },
      () => {
        if (alive) setDone(true);
      }
    );
    return () => {
      alive = false;
      close();
    };
  }, [jobId]);

  return { events, sseState, done };
}

export default function AgentToolStream(props: { jobId: string }) {
  const { jobId } = props;
  const { job, error, loading } = useAgentJob(jobId);
  const { events, sseState, done } = useToolEvents(jobId);

  if (loading) return <Spinner />;
  if (!job) {
    return (
      <div>
        <ErrorBox error={error || "任务不存在 (404)"} />
        <a href="#/agent">← 返回 Agent 总览</a>
      </div>
    );
  }

  const toolish = events.filter((ev) => ev.type !== "progress");
  const consoleText =
    toolish.length === 0
      ? "[等待工具事件… 计划批准后 worker 会发出 tool_call/tool_result/edit/gate]\n"
      : toolish
          .map((ev) => {
            const d = ev.data || {};
            const detail =
              typeof d.tool === "string"
                ? " → " + JSON.stringify(d)
                : JSON.stringify(d);
            return "#" + ev.seq + " [" + eventKindLabel(ev.type) + "]" + detail;
          })
          .join("\n");

  return (
    <AgentJobShell job={job} active="tools">
      <Panel
        title={
          "实时工具流 Tool stream (" +
          events.length +
          " 帧 · SSE " +
          sseState +
          (done ? " · 已结束 closed" : "") +
          ")"
        }
      >
        <div className="console" aria-label="agent-tool-stream">
          {consoleText}
        </div>
        <div style={{ marginTop: 12 }}>
          <div className="kv-label">最近事件 Recent events (全部类型)</div>
          {events.length === 0 ? (
            <div className="muted">—</div>
          ) : (
            events
              .slice(-12)
              .reverse()
              .map((ev) => <EventRow key={ev.seq} ev={ev} />)
          )}
        </div>
      </Panel>
    </AgentJobShell>
  );
}
