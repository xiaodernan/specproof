// Shared components + hooks for the SpecCraft agent console pages.

import { ReactNode, useEffect, useState } from "react";
import { AgentApproval, AgentEvent, AgentJob, getAgentJob } from "../api";
import { fmtTime, shortId } from "../components";
import { agentStatusMeta, eventKindLabel } from "./util";

export function useAgentJob(jobId: string) {
  const [job, setJob] = useState<AgentJob | null>(null);
  const [error, setError] = useState<Error | string | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = () => {
    let alive = true;
    getAgentJob(jobId)
      .then((d) => {
        if (alive) setJob(d.job);
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
  };

  useEffect(() => reload(), [jobId]);

  return { job, error, loading, reload };
}

export function AgentJobShell(props: {
  job: AgentJob;
  active: string;
  children: ReactNode;
  right?: ReactNode;
  reload?: () => void;
}) {
  const { job } = props;
  const meta = agentStatusMeta(job.status);
  const tabs: { key: string; label: string; href: string }[] = [
    { key: "overview", label: "概览", href: "#/agent/jobs/" + job.id },
    { key: "plan", label: "计划 Plan", href: "#/agent/jobs/" + job.id + "/plan" },
    { key: "tools", label: "工具流 Tools", href: "#/agent/jobs/" + job.id + "/tools" },
    { key: "events", label: "事件 Events", href: "#/agent/jobs/" + job.id + "/events" },
    { key: "edits", label: "编辑 Edits", href: "#/agent/jobs/" + job.id + "/edits" },
    { key: "gates", label: "门禁 Gates", href: "#/agent/jobs/" + job.id + "/gates" },
    { key: "diff", label: "Diff", href: "#/agent/jobs/" + job.id + "/diff" },
    { key: "approvals", label: "审批 (" + job.approvals_count + ")", href: "#/agent/jobs/" + job.id + "/approvals" },
    { key: "result", label: "结果 Result", href: "#/agent/jobs/" + job.id + "/result" },
  ];
  return (
    <div>
      <div className="page-head">
        <h1 className="mono">
          {job.task_name} <span className="muted mono">({shortId(job.id)})</span>{" "}
          <span className={"pill " + (meta.tone === "ok" ? "pill-ok" : meta.tone === "bad" ? "pill-bad" : meta.tone === "warn" ? "pill-run" : "pill-mute")}>
            {job.status}
          </span>
        </h1>
        <div className="page-sub">
          {"repo: " + job.repo_path + " · 更新 " + fmtTime(job.updated_at)}
        </div>
      </div>
      <div className="tabs">
        {tabs.map((t) => (
          <a key={t.key} href={t.href} className={"tab" + (t.key === props.active ? " tab-active" : "")}>
            {t.label}
          </a>
        ))}
        <div className="panel-right" style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          {props.right}
          {props.reload ? (
            <button className="btn btn-ghost btn-sm" onClick={() => props.reload?.()}>
              刷新 Refresh
            </button>
          ) : null}
        </div>
      </div>
      {props.children}
    </div>
  );
}

export function EventRow(props: { ev: AgentEvent; compact?: boolean }) {
  const { ev } = props;
  const data = ev.data || {};
  const title = String(
    (data.tool as string) || (data.status as string) || (data.message as string) || ev.type
  );
  return (
    <div className="event-row">
      <span className="event-seq mono">#{ev.seq}</span>
      <span className="event-kind mono">{eventKindLabel(ev.type)}</span>
      <span className="event-title">{title}</span>
      {props.compact ? null : (
        <span className="event-time muted mono">{fmtTime(ev.at)}</span>
      )}
    </div>
  );
}

export function ApprovalCard(props: { approval: AgentApproval; jobLabel?: string }) {
  const a = props.approval;
  return (
    <div className="approval-card">
      <div className="approval-head">
        <span className={"pill " + (a.decision === "approve" ? "pill-ok" : "pill-bad")}>
          {a.decision === "approve" ? "APPROVE 批准" : "REJECT 拒绝"}
        </span>
        <span className="mono muted">
          {a.target + (a.step_index !== null ? " #" + a.step_index : "")}
        </span>
        <span className="muted mono" style={{ marginLeft: "auto" }}>
          {fmtTime(a.created_at)}
        </span>
      </div>
      {props.jobLabel ? <div className="mono muted">job: {props.jobLabel}</div> : null}
      {a.note ? <div className="approval-note">{a.note}</div> : null}
      <div className="mono muted">by {a.actor} · {shortId(a.id)}</div>
    </div>
  );
}

export function ProgressBar(props: { percent: number }) {
  const pct = Math.max(0, Math.min(100, props.percent));
  return (
    <div className="bar">
      <div className="bar-fill" style={{ width: pct + "%" }} />
    </div>
  );
}
