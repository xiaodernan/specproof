import { useEffect, useState } from "react";
import { AgentDiff, getAgentDiff } from "../../api";
import { Empty, ErrorBox, Panel, Spinner } from "../../components";
import { AgentJobShell, useAgentJob } from "../components";

function useDiff(jobId: string, mode: "unified" | "split") {
  const [diff, setDiff] = useState<AgentDiff | null>(null);
  const [error, setError] = useState<Error | string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    getAgentDiff(jobId, mode)
      .then((d) => {
        if (alive) setDiff(d);
      })
      .catch((e) => {
        if (alive) setError(e as Error);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [jobId, mode]);

  return { diff, error, loading };
}

export default function AgentDiffViewer(props: { jobId: string; mode: "unified" | "split" }) {
  const { jobId, mode } = props;
  const { job, error: jobError, loading: jobLoading } = useAgentJob(jobId);
  const { diff, error, loading } = useDiff(jobId, mode);

  if (jobLoading || loading) return <Spinner />;
  if (!job) {
    return (
      <div>
        <ErrorBox error={jobError || "任务不存在 (404)"} />
        <a href="#/agent">← 返回 Agent 总览</a>
      </div>
    );
  }

  const modeBtn = (m: "unified" | "split", label: string) => (
    <a
      className={"btn btn-ghost btn-sm" + (mode === m ? " nav-active" : "")}
      href={"#/agent/jobs/" + jobId + "/diff/" + m}
      style={{ textDecoration: "none" }}
    >
      {label}
    </a>
  );

  return (
    <AgentJobShell job={job} active="diff">
      <ErrorBox error={error} />
      <Panel
        title={"结构化 Diff — " + (diff ? diff.stats.files_changed + " 文件" : "—")}
        right={
          <div style={{ display: "flex", gap: 8 }}>
            {modeBtn("unified", "统一 Unified")}
            {modeBtn("split", "分栏 Split")}
          </div>
        }
      >
        {!diff ? (
          <Empty text="变更包不可用 (worker 尚未产生 bundle — 诚实 404 空态)" />
        ) : diff.files.length === 0 ? (
          <Empty text="变更包为空 (无文件改动)" />
        ) : (
          <>
            <div className="diff-stats mono">
              <span className="diff-add">+{diff.stats.insertions}</span>
              <span className="diff-del">-{diff.stats.deletions}</span>
              <span className="muted">{diff.stats.files_changed} files</span>
              <span className="muted">{diff.mode}</span>
            </div>
            {diff.files.map((file) => (
              <div key={file.path} className="diff-file">
                <div className="diff-file-head">
                  <span
                    className={
                      "pill " +
                      (file.status === "added"
                        ? "pill-ok"
                        : file.status === "deleted"
                        ? "pill-bad"
                        : "pill-run")
                    }
                  >
                    {file.status}
                  </span>
                  <span className="mono">{file.path}</span>
                  <span className="mono diff-add">+{file.insertions}</span>
                  <span className="mono diff-del">-{file.deletions}</span>
                </div>
                {file.hunks.map((hunk, hi) => (
                  <div key={hi}>
                    <div className="diff-hunk-head mono muted">
                      @@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@
                    </div>
                    <div className={mode === "split" ? "diff-split" : "diff-unified"}>
                      {hunk.lines.map((line, li) => {
                        const key = hi + ":" + li;
                        return mode === "split" ? (
                          <div key={key} className="diff-row">
                            <span className="diff-no mono muted">{line.old_no ?? ""}</span>
                            <span className={"diff-cell " + line.type}>
                              {line.type === "add" ? "" : line.text}
                            </span>
                            <span className="diff-no mono muted">{line.new_no ?? ""}</span>
                            <span className={"diff-cell " + line.type}>
                              {line.type === "del" ? "" : line.text}
                            </span>
                          </div>
                        ) : (
                          <div key={key} className={"diff-row " + line.type}>
                            <span className="diff-no mono muted">{line.old_no ?? ""}</span>
                            <span className="diff-no mono muted">{line.new_no ?? ""}</span>
                            <span className="diff-text">
                              {(line.type === "add" ? "+" : line.type === "del" ? "-" : " ") +
                                line.text}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </>
        )}
      </Panel>
    </AgentJobShell>
  );
}
