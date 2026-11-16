import { useEffect, useRef, useState } from "react";
import { AgentEvent, AgentReplayGap } from "../../api";
import { ErrorBox, Panel, Spinner } from "../../ui";
import { AgentJobShell, EventRow, useAgentJob } from "../components";
import { agentRunPhase, eventKindLabel, isAgentTerminal, sseStateLabel } from "../util";
import { storedLocale } from "../../i18n/strings";

const isZh = (): boolean => storedLocale() === "zh";
const L = (zh: string, en: string): string => (isZh() ? zh : en);

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
  jobId: string, streamEvents: AgentEvent[], streamState: string, replayGap: AgentReplayGap | null,
) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [done, setDone] = useState(false);
  const bufferRef = useRef<AgentEvent[]>([]);
  const highestRef = useRef(0);
  const gapRef = useRef<AgentReplayGap | null>(null);

  useEffect(() => {
    // 切换任务时清空，避免把上一个任务的事件留在新任务的日志里。
    bufferRef.current = [];
    highestRef.current = 0;
    gapRef.current = null;
    setEvents([]); setDone(false);
  }, [jobId]);

  useEffect(() => {
    if (replayGap) gapRef.current = replayGap;
  }, [replayGap]);

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

  return { events, sseState: streamState, done, replayGap: gapRef.current };
}

export default function AgentToolStream(props: { jobId: string }) {
  const { jobId } = props;
  const { job, error, loading, events: streamEvents, streamState, replayGap } = useAgentJob(jobId);
  const { events, sseState, done, replayGap: activeGap } = useToolEvents(jobId, streamEvents, streamState, replayGap);

  if (loading) return <Spinner />;
  if (!job) {
    return (
      <div>
        <ErrorBox error={error || L("任务不存在（404）", "Task not found (404)")} />
        <a href="#/agent">{L("← 返回 Agent 总览", "← Back to Agent overview")}</a>
      </div>
    );
  }

  const toolish = events.filter((ev) => ev.type !== "progress");
  const gapNotice = activeGap
    ? isZh()
      ? (isZh() ? `\n[日志缺口 replay_gap：请补 seq>${activeGap.requested_after}，首个可见 seq=${activeGap.first_available}，中间缺 ${activeGap.first_available - activeGap.requested_after - 1} 条]\n` : `\n[replay_gap: please re-fetch seq>${activeGap.requested_after} — first visible seq=${activeGap.first_available}; ${activeGap.first_available - activeGap.requested_after - 1} missing]\n`)
      : `\n[Replay gap: requested seq>${activeGap.requested_after}; first available seq=${activeGap.first_available}; ${activeGap.first_available - activeGap.requested_after - 1} event(s) missing in between]\n`
    : "";
  const consoleText =
    toolish.length === 0
      ? (isZh()
          ? (isZh() ? "[等待工具事件——计划批准后 worker 会发送 tool_call/tool_result/edit/gate]\n" : "[waiting for tool events — the worker emits tool_call/tool_result/edit/gate after plan approval]\n") + gapNotice
          : "[waiting for tool events — after plan approval the worker emits tool_call/tool_result/edit/gate]\n" + gapNotice)
      : toolish
          .map((ev) => {
            const d = ev.data || {};
            const detail =
              ev.type === "model_output" && typeof d.text === "string" ? d.text : typeof d.tool === "string"
                ? " → " + JSON.stringify(d)
                : JSON.stringify(d);
            return "#" + ev.seq + " [" + eventKindLabel(ev.type) + "]" + detail;
          })
          .join("\n") + gapNotice;

  return (
    <AgentJobShell job={job} active="tools">
      <ErrorBox error={error} />
      <Panel
        title={
          L("实时工具流", "Tool stream") +
          " (" +
          events.length +
          (isZh() ? " 帧" : " frames") +
          " · SSE " +
          sseStateLabel(sseState) +
          // "closed" is only ever claimed from two facts: this stream received done,
          // or the job status is in the terminal vocabulary.
          (done || isAgentTerminal(job.status) ? (isZh() ? " · 已结束" : " · closed") : "") +
          (agentRunPhase(job.status) === "unknown" ? (isZh() ? " · 状态未识别" : " · unrecognized") : "") +
          ")"
        }
      >
        <div className="console" role="log" aria-live="polite" aria-relevant="additions text" aria-label="agent-tool-stream">
          {consoleText}
        </div>
        <div style={{ marginTop: 12 }}>
          <div className="kv-label">{L("最近事件", "Recent events")} {L("（全部类型）", "(all kinds)")}</div>
          {events.length === 0 ? (
            <div className="muted">{L("—（无事件）", "— (none)")}</div>
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
