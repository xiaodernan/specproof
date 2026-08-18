import AgentOverview from "./pages/AgentOverview";
import AgentWizard from "./pages/AgentWizard";
import AgentJobDetail from "./pages/AgentJobDetail";
import AgentPlanReview from "./pages/AgentPlanReview";
import AgentPlanStep from "./pages/AgentPlanStep";
import AgentToolStream from "./pages/AgentToolStream";
import AgentEventLog from "./pages/AgentEventLog";
import AgentEdits from "./pages/AgentEdits";
import AgentGates from "./pages/AgentGates";
import AgentDiffViewer from "./pages/AgentDiffViewer";
import AgentJobApprovals from "./pages/AgentJobApprovals";
import AgentResult from "./pages/AgentResult";
import AgentApprovalsInbox from "./pages/AgentApprovalsInbox";
import AgentApprovalDetail from "./pages/AgentApprovalDetail";
import AgentSettings from "./pages/AgentSettings";

// The agent console sub-router: 20 hash routes under /agent/*.
//   /agent                          overview list
//   /agent/new[/spec|gates|review]  4-step new-task wizard
//   /agent/jobs/:id                 detail + status timeline
//   /agent/jobs/:id/plan[:step]     plan review (per-step approve/reject)
//   /agent/jobs/:id/tools           live tool stream (SSE)
//   /agent/jobs/:id/events          full event log
//   /agent/jobs/:id/edits           edit history
//   /agent/jobs/:id/gates           gate review + approve/reject
//   /agent/jobs/:id/diff[/unified|/split] structured diff viewer
//   /agent/jobs/:id/approvals       per-job approval records
//   /agent/jobs/:id/result          final result summary
//   /agent/approvals                cross-job approvals inbox
//   /agent/approvals/:approvalId    approval detail
//   /agent/settings                 console settings
export default function AgentApp(props: { seg: string[] }) {
  // seg = ["agent", ...rest] as produced by App.tsx's hash router
  const rest = props.seg.slice(1);

  if (rest.length === 0) return <AgentOverview />;

  if (rest[0] === "new") {
    if (rest.length === 1) return <AgentWizard step="repo" />;
    if (rest[1] === "spec") return <AgentWizard step="spec" />;
    if (rest[1] === "gates") return <AgentWizard step="gates" />;
    if (rest[1] === "review") return <AgentWizard step="review" />;
    return <AgentWizard step="repo" />;
  }

  if (rest[0] === "approvals") {
    if (rest.length === 1) return <AgentApprovalsInbox />;
    return <AgentApprovalDetail approvalId={decodeURIComponent(rest[1])} />;
  }

  if (rest[0] === "settings") return <AgentSettings />;

  if (rest[0] === "jobs" && rest.length >= 2) {
    const jobId = decodeURIComponent(rest[1]);
    const sub = rest[2];
    if (!sub) return <AgentJobDetail jobId={jobId} />;
    if (sub === "plan") {
      if (rest.length >= 4) {
        const idx = Number.parseInt(rest[3], 10);
        if (!Number.isNaN(idx) && idx >= 0) {
          return <AgentPlanStep jobId={jobId} stepIndex={idx} />;
        }
      }
      return <AgentPlanReview jobId={jobId} />;
    }
    if (sub === "tools") return <AgentToolStream jobId={jobId} />;
    if (sub === "events") return <AgentEventLog jobId={jobId} />;
    if (sub === "edits") return <AgentEdits jobId={jobId} />;
    if (sub === "gates") return <AgentGates jobId={jobId} />;
    if (sub === "diff") {
      if (rest[3] === "split") return <AgentDiffViewer jobId={jobId} mode="split" />;
      return <AgentDiffViewer jobId={jobId} mode="unified" />;
    }
    if (sub === "approvals") return <AgentJobApprovals jobId={jobId} />;
    if (sub === "result") return <AgentResult jobId={jobId} />;
    return <AgentJobDetail jobId={jobId} />;
  }

  return <AgentOverview />;
}
