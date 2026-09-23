import { useMemo } from "react";
import { Empty, ErrorBox, Panel, Spinner, fmtTime } from "../../ui";
import { AgentJobShell, useAgentJob } from "../components";
import { sseStateLabel } from "../util";

// Edits arrive as "edit" events on the shared realtime channel (the same SSE +
// polling collector the event log uses); this page just keeps the edit frames.
// It must NOT open its own fetch stream — the previous bespoke collector built
// `/agent/jobs/:id/events?key=<API Key>`, leaking the key into the URL query
// (browser history, proxies, server access logs).
export default function AgentEdits(props: { jobId: string }) {
  const { jobId } = props;
  const { job, error, loading, events, streamState } = useAgentJob(jobId);
  const edits = useMemo(
    () => events.filter((ev) => ev.seq && ev.type === "edit"),
    [events]
  );

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
        {streamState === "error" ? (
          <div className="errorbox">{sseStateLabel(streamState)}</div>
        ) : null}
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
                <span className="mono muted">{files} 个文件 files</span>
                <span className="mono muted" title={ev.at}>{fmtTime(ev.at)}</span>
                <a className="btn btn-ghost btn-sm" href={"#/agent/jobs/" + jobId + "/diff"}>
                  查看差异 Diff
                </a>
              </div>
            );
          })
        )}
      </Panel>
    </AgentJobShell>
  );
}
