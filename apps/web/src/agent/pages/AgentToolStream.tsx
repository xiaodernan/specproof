import { useEffect, useRef, useState } from "react";
import { AgentEvent } from "../../api";
import { ErrorBox, Panel, Spinner } from "../../ui";
import { AgentJobShell, EventRow, useAgentJob } from "../components";
import { eventKindLabel, sseStateLabel } from "../util";

/** 与本文件之外的调用方（测试）共用的原始事件缓冲上限。 */
const MAX_BUFFERED_EVENTS = 300;

/**
 * 原始事件缓冲：同一个任务只建立一条 SSE 连接。
 *
 * 这里刻意**不再自己开流**——`useAgentJob` 已成为唯一的实时通道（验证详情页
 * 与开发助手共用）。此前本页与详情页各开一条连接，同一任务会被订阅两次。
 * `ready` 为 false 时保持"尚未收到任何事件"的真实状态，而不是伪造空列表。
 */
function useToolEvents(
  jobId: string, streamEvents: AgentEvent[], streamState: string,
) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [done, setDone] = useState(false);
  const bufferRef = useRef<AgentEvent[]>([]);
  const highestRef = useRef(0);

  useEffect(() => {
    // 切换任务时清空，避免把上一个任务的事件留在新任务的日志里。
    bufferRef.current = [];
    highestRef.current = 0;
    setEvents([]); setDone(false);
  }, [jobId]);

  useEffect(() => {
    for (const ev of streamEvents) {
      if (ev.seq <= highestRef.current) continue;  // 重放去重
      highestRef.current = ev.seq;
      bufferRef.current = [...bufferRef.current.slice(-(MAX_BUFFERED_EVENTS - 1)), ev];
    }
    setEvents(bufferRef.current);
  }, [streamEvents]);

  useEffect(() => {
    if (streamState === "closed") setDone(true);
  }, [streamState]);

  return { events, sseState: streamState, done };
}

export default function AgentToolStream(props: { jobId: string }) {
  const { jobId } = props;
  const { job, error, loading, events: streamEvents, streamState } = useAgentJob(jobId);
  const { events, sseState, done } = useToolEvents(jobId, streamEvents, streamState);

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
              ev.type === "model_output" && typeof d.text === "string" ? d.text : typeof d.tool === "string"
                ? " → " + JSON.stringify(d)
                : JSON.stringify(d);
            return "#" + ev.seq + " [" + eventKindLabel(ev.type) + "]" + detail;
          })
          .join("\n");

  return (
    <AgentJobShell job={job} active="tools">
      <ErrorBox error={error} />
      <Panel
        title={
          "实时工具流 Tool stream (" +
          events.length +
          " 帧 · SSE " +
          sseStateLabel(sseState) +
          (done || ["COMPLETED", "FAILED", "CANCELLED"].includes(job.status) ? " · 已结束 closed" : "") +
          ")"
        }
      >
        <div className="console" role="log" aria-live="polite" aria-relevant="additions text" aria-label="agent-tool-stream">
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
