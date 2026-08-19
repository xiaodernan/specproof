import { useEffect, useState } from "react";
import { AgentEvent } from "../../api";
import { Empty, ErrorBox, Panel, Spinner } from "../../ui";
import { AgentJobShell, useAgentJob } from "../components";

// Edits arrive as "edit" events on the SSE stream; this page reuses the
// event-log collector and keeps the edit frames only.
async function collectEdits(jobId: string, onEvent: (ev: AgentEvent) => void): Promise<void> {
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
        if (ev.seq && ev.type === "edit") onEvent(ev);
      } catch {
        // skip malformed frames
      }
    }
  }
}

export default function AgentEdits(props: { jobId: string }) {
  const { jobId } = props;
  const { job, error, loading } = useAgentJob(jobId);
  const [edits, setEdits] = useState<AgentEvent[]>([]);
  const [streamError, setStreamError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    collectEdits(jobId, (ev) => {
      if (alive) setEdits((prev) => [...prev, ev]);
    }).catch((e) => {
      if (alive) setStreamError(e instanceof Error ? e.message : String(e));
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
    <AgentJobShell job={job} active="edits">
      <Panel title={"编辑记录 Edits (" + edits.length + ")"}>
        {streamError ? <div className="errorbox">{streamError}</div> : null}
        {edits.length === 0 ? (
          <Empty text="尚无文件编辑事件 (worker 未产生改动或未接线 — 诚实空态)" />
        ) : (
          edits.map((ev) => {
            const d = ev.data || {};
            const bundle = d.bundle as Record<string, unknown> | undefined;
            const files =
              bundle && typeof bundle.files_changed === "number"
                ? bundle.files_changed
                : "?";
            return (
              <div key={ev.seq} className="edit-row">
                <span className="mono">#{ev.seq}</span>
                <span>变更包 Change bundle</span>
                <span className="mono muted">{files} file(s)</span>
                <span className="mono muted">{ev.at}</span>
                <a className="btn btn-ghost btn-sm" href={"#/agent/jobs/" + jobId + "/diff"}>
                  查看 Diff
                </a>
              </div>
            );
          })
        )}
      </Panel>
    </AgentJobShell>
  );
}
