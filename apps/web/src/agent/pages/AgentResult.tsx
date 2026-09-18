import { useEffect, useState } from "react";
import { listAgentApprovals } from "../../api";
import { Empty, ErrorBox, Panel, Spinner } from "../../ui";
import { AgentJobShell, ApprovalCard, useAgentJob } from "../components";

const GATE_LABELS: Record<string, string> = { run_test: "相关测试", run_build: "项目构建", run_typecheck: "类型检查", security: "敏感信息检查", self_verify: "改动自检" };
const GATE_STATUS: Record<string, string> = { passed: "通过", failed: "未通过", skipped: "未执行", error: "执行出错" };

export default function AgentResult({ jobId }: { jobId: string }) {
  const { job, error, loading } = useAgentJob(jobId);
  const [approvals, setApprovals] = useState<import("../../api").AgentApproval[]>([]);
  useEffect(() => {
    let alive = true;
    setApprovals([]);
    listAgentApprovals(jobId).then(data => { if (alive) setApprovals(data.approvals || []); }).catch(() => {});
    return () => { alive = false; };
  }, [jobId]);
  if (loading) return <Spinner />;
  if (!job) return <ErrorBox error={error || "暂时无法读取任务结果"} />;
  const result = job.result;
  const completed = job.status === "COMPLETED";
  const gates = result?.gates?.gates || [];
  const models = [...new Set(result?.llm_usage?.calls_detail?.map(call => call.model).filter(Boolean) || [])];
  return <AgentJobShell job={job} active="result">
    <ErrorBox error={error} />
    {!result ? <Panel title="执行结果"><Empty text="任务还在处理中，完成后会在这里显示改动、检查结果和下一步。" /></Panel> : <>
      <section className={"result-overview " + (completed ? "result-complete" : "result-attention")}><div className="eyebrow">DEVELOPMENT RESULT</div><h2>{completed ? "开发执行完成，准备审阅改动" : job.status === "CANCELLED" ? "任务已取消" : "执行未完成，需要处理问题"}</h2><p>{result.reason || (completed ? "先查看代码差异和下方检查结果，再对这次变更进行独立验收。" : "请到执行进度中查看失败原因，调整需求或环境后重新提交。")}</p><div className="result-actions"><a className="btn btn-primary" href={"#/agent/jobs/" + jobId + "/diff"}>审阅代码差异 →</a><a className="btn" href="#/jobs/new">新建独立验收</a></div></section>
      <div className="metrics-grid result-metrics"><div className="metric-card"><div className="metric-top">改动文件</div><strong>{result.diff_stat?.files_changed ?? "—"}</strong><small>本次执行记录的文件变更</small></div><div className="metric-card"><div className="metric-top">执行阶段模型调用</div><strong>{result.llm_usage?.calls ?? "—"}</strong><small>{models.join("、") || "未记录模型调用"}</small></div><div className="metric-card"><div className="metric-top">通过的检查</div><strong>{gates.length ? gates.filter(gate => gate.status === "passed").length + " / " + gates.length : "—"}</strong><small>未执行的检查不算通过</small></div></div>
      <Panel title="检查结果">{gates.length ? <div className="result-gates">{gates.map(gate => <div className="result-gate" key={gate.gate}><div><strong>{GATE_LABELS[gate.gate] || gate.gate}</strong><span className={"pill " + (gate.status === "passed" ? "pill-ok" : gate.status === "skipped" ? "pill-mute" : "pill-bad")}>{GATE_STATUS[gate.status] || gate.status}</span></div><p>{gate.note}</p></div>)}</div> : <Empty text="没有可读取的检查结果，请查看执行日志。" />}<p className="result-boundary">开发完成不等于独立验收通过。未执行或尚未覆盖的检查，需要在交付前补齐。</p></Panel>
      {approvals.length > 0 && <Panel title="审批记录">{approvals.map(approval => <ApprovalCard key={approval.id} approval={approval} />)}</Panel>}
      <details className="result-raw"><summary>查看完整执行记录</summary><pre className="json">{JSON.stringify(result, null, 2)}</pre></details>
    </>}
  </AgentJobShell>;
}
