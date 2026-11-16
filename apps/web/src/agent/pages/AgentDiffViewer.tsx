import { useEffect, useState } from "react";
import { AgentDiff, getAgentDiff } from "../../api";
import { Empty, ErrorBox, Panel, Spinner } from "../../ui";
import { AgentJobShell, useAgentJob } from "../components";
import { diffFileStatusLabel, diffModeLabel } from "../util";
import { loadFailed } from "../../ui/errorHints";
import { storedLocale } from "../../i18n/strings";
const isZh = (): boolean => storedLocale() === "zh";
const L = (zh: string, en: string): string => (isZh() ? zh : en);

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
        <ErrorBox error={jobError || L("任务不存在（404）", "Task not found (404)")} />
        <a href="#/agent">{L("← 返回 Agent 总览", "← Back to Agent overview")}</a>
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
        title={L("结构化 Diff —— ", "Structured diff — ") + (diff ? diff.stats.files_changed + L(" 个文件", " file(s)") : "—")}
        right={
          <div style={{ display: "flex", gap: 8 }}>
            {modeBtn("unified", L("统一", "Unified"))}
            {modeBtn("split", L("分栏", "Split"))}
          </div>
        }
      >
        {!diff ? (
          loadFailed(error) ? (
            <Empty text={L("变更包暂时无法加载（请求失败）——这不代表没有改动，请稍后重试。", "The change bundle failed to load (request failed); this does not mean there are no changes — retry shortly.")} />
          ) : (
            <Empty text={L("变更包不可用（worker 尚未产生 bundle——诚实 404 空态）", "Change bundle unavailable (the worker has not produced one yet — honest 404 empty state).")} />
          )
        ) : diff.files.length === 0 ? (
          <Empty text={L("变更包为空（无文件改动）", "The change bundle is empty (no file changes).")} />
        ) : (
          <>
            <div className="diff-stats mono">
              <span className="diff-add">+{diff.stats.insertions}</span>
              <span className="diff-del">-{diff.stats.deletions}</span>
              <span className="muted">{diff.stats.files_changed} {L("个文件", "file(s)")}</span>
              <span className="muted">{diffModeLabel(diff.mode)}</span>
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
                    {diffFileStatusLabel(file.status)}
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
