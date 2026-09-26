import { useEffect, useState } from "react";
import { listAgentApprovals, type AgentJob } from "../../api";
import { Empty, ErrorBox, Panel, Spinner, acceptSeverityLabel, acceptSeverityTone } from "../../ui";
import { describePipelineError } from "../../ui/errorHints";
import { AgentJobShell, ApprovalCard, useAgentJob } from "../components";
import {
  acceptBlockedMeaning,
  acceptBlockedNotice,
  acceptVerdictLabel,
  gateLabel,
  gateStatusPillClass,
  gateStatusLabel,
} from "../util";

function AcceptProjection({ job, jobId }: { job: AgentJob; jobId: string }) {
  const accept = job.accept;
  const terminal = ["COMPLETED", "FAILED", "CANCELLED"].includes(job.status);
  const cliCommand = "specproof craft accept --job " + jobId;

  if (accept?.malformed) {
    return <Panel title="独立验收记录 ACCEPT">
      <div className="errorbox" role="alert">
        <strong>验收记录读不出来</strong>
        <p>作业里存在验收投影，但它的内容无法解析（存储损坏或版本不匹配）。这<strong>不等于“没有验收”</strong>，也不能据此判断交付状态。可在命令行重新读取该作业：</p>
        <pre className="json">{cliCommand}</pre>
      </div>
    </Panel>;
  }

  if (!accept) {
    // The three cases below are not interchangeable: the accept projection is
    // a SEPARATE attach write that only matches a finished run (storage
    // agent_jobs._ATTACH_ACCEPT_SQL: status IN succeeded/failed), so a
    // cancelled job never gets one and "refresh later" would be a false promise.
    return <Panel title="独立验收记录 ACCEPT">
      {!terminal ? <Empty text="任务尚未进入终态，独立验收还不会运行。" /> : job.status === "CANCELLED" ? <>
        <Empty text="这一轮已取消，不会有独立验收记录。" />
        <p className="result-boundary">验收投影只挂在执行完的轮次上（成功或失败），取消的轮次不会补出它。需要独立验收结论，请重新发起一次开发执行。</p>
      </> : <>
        <Empty text="这次运行还没有独立验收记录。" />
        <p className="result-boundary">独立验收由 <strong>开发执行完成</strong>之后的一次单独闭包产生（门禁复核 + 合并证书 + 签名），它与执行终态是两次写入，所以刚完成的一瞬间可能还没有——可稍后刷新本页；也可以直接在命令行补一次：</p>
        <pre className="json">{cliCommand}</pre>
      </>}
    </Panel>;
  }

  const verdict = acceptVerdictLabel(accept.verdict, accept.gates?.overall);
  const blocked = accept.verdict === "BLOCKED" ? acceptBlockedNotice(acceptBlockedMeaning(accept.gates?.overall)) : "";
  const gates = accept.gates;
  const findings = accept.findings || [];
  return <Panel title="独立验收记录 ACCEPT">
    <div className="result-accept-head">
      <span className={"pill " + (verdict.tone === "ok" ? "pill-ok" : verdict.tone === "bad" ? "pill-bad" : verdict.tone === "warn" ? "pill-unverified" : "pill-mute")} title={accept.verdict || undefined}>{verdict.label}</span>
      {accept.rolled_back === true ? <span className="pill pill-bad">已回滚 rolled_back</span> : null}
      {accept.rolled_back === false ? <span className="pill pill-mute" title="rolled_back=false">未回滚</span> : null}
      {accept.rolled_back === undefined ? <span className="muted" title="accept 投影未记录 rolled_back">回滚状态未记录</span> : null}
    </div>
    {accept.note ? <p className="quality-cell-copy">{accept.note}</p> : null}
    {blocked ? <p className="result-boundary">{blocked}</p> : null}
    {gates ? <>
      <div className="kv-label" style={{ margin: "12px 0 6px" }}>门禁汇总（独立验收）</div>
      {gates.entries.length ? <div className="result-gates">{gates.entries.map((entry, index) => <div className="result-gate" key={entry.gate + index}>
        <div><strong>{gateLabel(entry.gate)}</strong><span className={gateStatusPillClass(entry.status)} title={entry.status}>{gateStatusLabel(entry.status)}</span></div>
        <p>{entry.note || "（无说明）"}{entry.findings_total > 0 ? ` · 关联发现 ${entry.findings_total} 条` : ""}</p>
      </div>)}</div> : <Empty text="验收投影里没有逐条门禁记录。" />}
      {gates.truncated ? <p className="result-boundary">门禁记录较多，此处仅展示前 {gates.entries.length} 条（共 {gates.total} 条）。</p> : null}
      <p className="muted mono" style={{ fontSize: 11 }} title={gates.summary || undefined}>overall: {gates.overall || "未知"}</p>
    </> : <p className="result-boundary">该投影不含门禁摘要（例如验收过程本身出错时）。缺摘要不等于全通过。</p>}
    {accept.certificate_path ? <p className="mono muted" style={{ fontSize: 11 }} title="证书由服务端本机路径保存，Web 端不提供下载">合并证书：{accept.certificate_path}</p> : <p className="result-boundary">本次未签发合并证书。</p>}
    {findings.length ? <>
      <div className="kv-label" style={{ margin: "12px 0 6px" }}>验收发现</div>
      {/* This used to be `JSON.stringify(findings)`: that was honest but not
          readable — the severity of a leaked credential could only be seen by
          parsing the object. The full projection stays in the raw dump below. */}
      <div className="result-gates">{findings.map((finding, index) => <div className="result-gate" key={String(finding.file || finding.kind || "finding") + index}>
        <div>
          <span className={"pill pill-" + acceptSeverityTone(finding.severity)} title={finding.severity || undefined}>
            {acceptSeverityLabel(finding.severity)}
          </span>
          <strong> {finding.kind || "未记录类型"}</strong>
          {finding.file
            ? <span className="mono muted">{finding.file}{finding.line ? ":" + finding.line : ""}</span>
            : null}
        </div>
        <p>{finding.description || "（该发现没有描述文字）"}</p>
      </div>)}</div>
      {accept.findings_truncated ? <p className="result-boundary">发现记录较多，此处仅展示前 {findings.length} 条（共 {accept.findings_total ?? findings.length} 条）。</p> : null}
    </> : null}
    <details className="result-raw"><summary>查看完整验收投影</summary><pre className="json">{JSON.stringify(accept, null, 2)}</pre></details>
  </Panel>;
}

export default function AgentResult({ jobId }: { jobId: string }) {
  const { job, error, loading } = useAgentJob(jobId);
  const [approvals, setApprovals] = useState<import("../../api").AgentApproval[]>([]);
  const [approvalsError, setApprovalsError] = useState<Error | string | null>(null);
  useEffect(() => {
    let alive = true;
    setApprovals([]);
    setApprovalsError(null);
    listAgentApprovals(jobId)
      .then((data) => { if (alive) setApprovals(data.approvals || []); })
      .catch((e) => { if (alive) setApprovalsError(e as Error); });
    return () => { alive = false; };
  }, [jobId]);
  if (loading) return <Spinner />;
  if (!job) return <ErrorBox error={error || "暂时无法读取任务结果"} />;
  const result = job.result;
  const completed = job.status === "COMPLETED";
  const terminal = ["COMPLETED", "FAILED", "CANCELLED"].includes(job.status);
  const gates = result?.gates?.gates || [];
  const models = [...new Set(result?.llm_usage?.calls_detail?.map(call => call.model).filter(Boolean) || [])];
  return <AgentJobShell job={job} active="result">
    <ErrorBox error={error} />
    {!result ? <Panel title="执行结果">{terminal ? (job.status === "COMPLETED" ? <>
      <Empty text="任务显示已完成，但记录里没有执行结果投影。" />
      {/* Status and result ride the SAME UPDATE (storage agent_jobs
          _UPDATE_STATUS_TERMINAL_SQL), so this combination is not a timing
          window — promising a refresh would be false. */}
      <p className="result-boundary">执行终态与结果投影是<strong>同一条写入</strong>落库的，因此"已完成但没有结果"说明这一行的终态不是本轮执行写下的（例如被回收或由 supervisor 置位），或它是该规则之前完成的历史记录。<strong>稍后刷新不会补出结果</strong>；请查看事件记录，或在命令行用 <code>craft accept --job …</code> 复核。<strong>在结果出现之前，这里不会显示“通过”，也不会显示“失败”。</strong></p>
    </> : <>
      <Empty text={job.status === "FAILED" ? "这一轮以失败结束，没有产生执行结果。" : "这一轮已取消，没有产生执行结果。"} />
      <p className="result-boundary">失败或取消的轮次不会补出结果投影。要判断出了什么问题，请查看执行进度里的失败原因；处理后再提交一次。</p>
    </>) : <Empty text="任务还在处理中，完成后会在这里显示改动、检查结果和下一步。" />}</Panel> : <>
      <section className={"result-overview " + (completed ? "result-complete" : "result-attention")}><div className="eyebrow">开发结果 DEVELOPMENT RESULT</div><h2>{completed ? "开发执行完成，准备审阅改动" : job.status === "CANCELLED" ? "任务已取消" : "执行未完成，需要处理问题"}</h2><p title={result.reason || undefined}>{result.reason ? describePipelineError(String(result.reason)) : (completed ? "先查看代码差异和下方检查结果，再对这次变更进行独立验收。" : "请到执行进度中查看失败原因，调整需求或环境后重新提交。")}</p><div className="result-actions"><a className="btn btn-primary" href={"#/agent/jobs/" + jobId + "/diff"}>审阅代码差异 →</a><a className="btn" href={"#/jobs/new?repo=" + encodeURIComponent(job.repo_path)}>新建独立验收</a></div></section>
      <div className="metrics-grid result-metrics"><div className="metric-card"><div className="metric-top">改动文件</div><strong>{result.diff_stat?.files_changed ?? "—"}</strong><small>本次执行记录的文件变更</small></div><div className="metric-card"><div className="metric-top">执行阶段模型调用</div><strong>{result.llm_usage?.calls ?? "—"}</strong><small>{models.join("、") || "未记录模型调用"}</small></div><div className="metric-card"><div className="metric-top">通过的检查</div><strong>{gates.length ? gates.filter(gate => gate.status === "passed").length + " / " + gates.length : "—"}</strong><small>未执行的检查不算通过</small></div></div>
      <Panel title="检查结果">{gates.length ? <div className="result-gates">{gates.map(gate => <div className="result-gate" key={gate.gate}><div><strong>{gateLabel(gate.gate)}</strong><span className={gateStatusPillClass(gate.status)} title={gate.status}>{gateStatusLabel(gate.status)}</span></div><p>{gate.note}</p></div>)}</div> : <Empty text="没有可读取的检查结果，请查看执行日志。" />}<p className="result-boundary">开发完成不等于独立验收通过。未执行或尚未覆盖的检查，需要在交付前补齐。</p></Panel>
      {approvalsError ? <Panel title="审批记录"><div className="errorbox" title={approvalsError instanceof Error ? approvalsError.message : String(approvalsError)}>审批记录暂时无法加载（请求失败）— 不代表没有审批，请稍后重试</div></Panel> : approvals.length > 0 ? <Panel title="审批记录">{approvals.map(approval => <ApprovalCard key={approval.id} approval={approval} />)}</Panel> : null}
      <details className="result-raw"><summary>查看完整执行记录</summary><pre className="json">{JSON.stringify(result, null, 2)}</pre></details>
    </>}
    {/* Mounted outside the result branch on purpose: the accept projection is
        an independent record, and a job whose result row has not been written
        yet must still show whatever the acceptance closure did say. */}
    <AcceptProjection job={job} jobId={jobId} />
  </AgentJobShell>;
}
