import { useEffect, useState } from "react";
import { listAgentApprovals, type AgentJob } from "../../api";
import { Empty, ErrorBox, Panel, Spinner, acceptSeverityLabel, acceptSeverityTone } from "../../ui";
import { describePipelineError } from "../../ui/errorHints";
import { storedLocale } from "../../i18n/strings";

const isZh = (): boolean => storedLocale() === "zh";
const L = (zh: string, en: string): string => (isZh() ? zh : en);
import { AgentJobShell, ApprovalCard, useAgentJob } from "../components";
import {
  acceptBlockedMeaning,
  acceptBlockedNotice,
  acceptVerdictLabel,
  agentRunPhase,
  agentUnknownNotice,
  gateLabel,
  gateStatusPillClass,
  gateStatusLabel,
} from "../util";

function AcceptProjection({ job, jobId }: { job: AgentJob; jobId: string }) {
  const accept = job.accept;
  const phase = agentRunPhase(job.status);
  const cliCommand = "specproof craft accept --job " + jobId;

  if (accept?.malformed) {
    return <Panel title="独立验收记录 ACCEPT">
      <div className="errorbox" role="alert">
        <strong>{L("验收记录读不出来", "The acceptance record cannot be read")}</strong>
        <p>{L("作业里存在验收投影，但它的内容无法解析（存储损坏或版本不匹配）。这", "An accept projection exists on this job, but its content cannot be parsed (storage corrupt or version mismatch). This is ")}<strong>{L("不等于“没有验收”", "not the same as “no acceptance”")}</strong>{L("，也不能据此判断交付状态。可在命令行重新读取该作业：", ", and says nothing about the delivery state. Re-read the job from the CLI:")}</p>
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
      {phase === "unknown" ? <>
        {/* A status this console has never seen is not "still running". The
            runtime maps unknown store statuses through verbatim, so an
            already-finished run can arrive here with a word outside the six
            labels — and 「尚未进入终态」 would then be a promise that never
            expires. Say what is unknown instead. */}
        <Empty text={L("这一轮上报的状态不在本页词表里，无法判断独立验收是否应当已经发生。", "The status reported this round is not in this page's vocabulary — whether independent acceptance should have happened cannot be determined.")} />
        <p className="result-boundary">{agentUnknownNotice(job.status)}</p>
      </> : phase !== "terminal" ? <Empty text={L("任务尚未进入终态，独立验收还不会运行。", "The task has not reached a terminal state — independent acceptance has not run yet.")} /> : job.status === "CANCELLED" ? <>
        <Empty text={L("这一轮已取消，不会有独立验收记录。", "This round was cancelled — there is no acceptance record.")} />
        <p className="result-boundary">{L("验收投影只挂在执行完的轮次上（成功或失败），取消的轮次不会补出它。需要独立验收结论，请重新发起一次开发执行。", "The acceptance projection is attached only to completed rounds (success or failed) — cancelled rounds never gain one. If you need an acceptance verdict, start a development run again.")}</p>
      </> : <>
        <Empty text={L("这次运行还没有独立验收记录。", "This run has no acceptance record yet.")} />
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
      {accept.rolled_back === true ? <span className="pill pill-bad">{L("已回滚", "Rolled back")} (rolled_back)</span> : null}
      {accept.rolled_back === false ? <span className="pill pill-mute" title="rolled_back=false">{L("未回滚", "Not rolled back")}</span> : null}
      {accept.rolled_back === undefined ? <span className="muted" title="accept projection recorded no rolled_back">{L("回滚状态未记录", "Rollback status not recorded")}</span> : null}
    </div>
    {accept.note ? <p className="quality-cell-copy">{accept.note}</p> : null}
    {blocked ? <p className="result-boundary">{blocked}</p> : null}
    {gates ? <>
      <div className="kv-label">{L("门禁汇总（独立验收）", "Gate summary (independent acceptance)")}</div>
      {gates.entries.length ? <div className="result-gates">{gates.entries.map((entry, index) => <div className="result-gate" key={entry.gate + index}>
        <div><strong>{gateLabel(entry.gate)}</strong><span className={gateStatusPillClass(entry.status)} title={entry.status}>{gateStatusLabel(entry.status)}</span></div>
        <p>{entry.note || L("（无说明）", "(no note)")}{entry.findings_total > 0 ? (isZh() ? ` · 关联发现 ${entry.findings_total} 条` : ` · ${entry.findings_total} linked finding${entry.findings_total === 1 ? "" : "s"}`) : ""}</p>
      </div>)}</div> : <Empty text={L("验收投影里没有逐条门禁记录。", "The accept projection carries no per-gate entries.")} />}
      {gates.truncated ? <p className="result-boundary">门禁记录较多，此处仅展示前 {gates.entries.length} 条（共 {gates.total} 条）。</p> : null}
      <p className="muted mono" style={{ fontSize: 11 }} title={gates.summary || undefined}>overall: {gates.overall || L("未知", "unknown")}</p>
    </> : <p className="result-boundary">{L("该投影不含门禁摘要（例如验收过程本身出错时）。缺摘要不等于全通过。", "This projection carries no gate summary (e.g. when the acceptance process itself errored). No summary does not mean “all passed”.")}</p>}
    {accept.certificate_path ? <p className="mono muted" style={{ fontSize: 11 }} title={L("证书由服务端本机路径保存，Web 端不提供下载", "The certificate is held at a server-side local path; the web app does not offer downloads")}>{L("合并证书：", "Merge certificate: ")}{accept.certificate_path}</p> : <p className="result-boundary">{L("本次未签发合并证书。", "No merge certificate issued this time.")}</p>}
    {findings.length ? <>
      <div className="kv-label">{L("验收发现", "Findings")}</div>
      {/* This used to be `JSON.stringify(findings)`: that was honest but not
          readable — the severity of a leaked credential could only be seen by
          parsing the object. The full projection stays in the raw dump below. */}
      <div className="result-gates">{findings.map((finding, index) => <div className="result-gate" key={String(finding.file || finding.kind || "finding") + index}>
        <div>
          <span className={"pill pill-" + acceptSeverityTone(finding.severity)} title={finding.severity || undefined}>
            {acceptSeverityLabel(finding.severity)}
          </span>
          <strong> {finding.kind || L("未记录类型", "Unrecorded kind")}</strong>
          {finding.file
            ? <span className="mono muted">{finding.file}{finding.line ? ":" + finding.line : ""}</span>
            : null}
        </div>
        <p>{finding.description || L("（该发现没有描述文字）", "(This finding has no description.)")}</p>
      </div>)}</div>
      {accept.findings_truncated ? <p className="result-boundary">发现记录较多，此处仅展示前 {findings.length} 条（共 {accept.findings_total ?? findings.length} 条）。</p> : null}
    </> : null}
    <details className="result-raw"><summary>{L("查看完整验收投影", "View the full accept projection")}</summary><pre className="json">{JSON.stringify(accept, null, 2)}</pre></details>
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
  if (!job) return <ErrorBox error={error || L("暂时无法读取任务结果", "Cannot read this job's result right now")} />;
  const result = job.result;
  const completed = job.status === "COMPLETED";
  const phase = agentRunPhase(job.status);
  const gates = result?.gates?.gates || [];
  const models = [...new Set(result?.llm_usage?.calls_detail?.map(call => call.model).filter(Boolean) || [])];
  // #145: the sandbox's own statement about the dependency cache it consumed
  // ("缓存完整性通过…" / "缓存完整性: 未校验 (NOT VERIFIED)…") is written into the
  // step evidence by craft/loop.py. Until now the only way to read it in the
  // product was to expand the raw-JSON <details> and know the English key name —
  // an honest disclosure that no reviewer would find. Lifted out here, in the
  // reader's language, on the panel that also carries the gates.
  //
  // Deduplicated because the same note is recorded once per step that ran a
  // command; the page states the fact, not how many steps repeated it.
  const cacheNotes = [...new Set(
    (result?.steps || [])
      .map(step => step.evidence?.cache_note)
      .filter((note): note is string => typeof note === "string" && note.trim() !== "")
  )];
  return <AgentJobShell job={job} active="result">
    <ErrorBox error={error} />
    {!result ? <Panel title={L("执行结果", "Development result")}>{phase === "unknown" ? <>
      <Empty text={L("这一轮上报的状态不在本页词表里，无法判断它是仍在执行还是已经结束。", "The status reported is not in this page's vocabulary — cannot tell whether it is still running or already finished.")} />
      <p className="result-boundary">{agentUnknownNotice(job.status)}要判断这一轮发生了什么，请查看执行进度与事件记录，或在命令行用 <code>specproof craft accept --job {jobId}</code> 复核。<strong>这里不会替这个状态编一个含义，也不会因为读不出来就说“还在处理中”。</strong></p>
    </> : phase === "terminal" ? (job.status === "COMPLETED" ? <>
      <Empty text={L("任务显示已完成，但记录里没有执行结果投影。", "The job shows as completed but carries no result projection.")} />
      {/* Status and result ride the SAME UPDATE (storage agent_jobs
          _UPDATE_STATUS_TERMINAL_SQL), so this combination is not a timing
          window — promising a refresh would be false. */}
      <p className="result-boundary">{L("执行终态与结果投影是", "The terminal status and the result projection are written by ")}<strong>{L("同一条写入", "the same statement")}</strong>{L("落库的，因此“已完成但没有结果”说明这一行的终态不是本轮执行写下的（例如被回收或由 supervisor 置位），或它是该规则之前完成的历史记录。", " landing in one write — so “completed but no result” means this row’s terminal status was not written by this run (e.g. reclaimed or set by a supervisor), or it is a historical record from before that rule. ")}<strong>{L("稍后刷新不会补出结果", "Refreshing later will not produce the result")}</strong>；请查看事件记录，或在命令行用 <code>craft accept --job …</code> 复核。<strong>{L("在结果出现之前，这里不会显示“通过”，也不会显示“失败”。", "Until a result appears, this page will show neither “passed” nor “failed”.")}</strong></p>
    </> : <>
      <Empty text={job.status === "FAILED" ? L("这一轮以失败结束，没有产生执行结果。", "This round ended in failure — no result was produced.") : L("这一轮已取消，没有产生执行结果。", "This round was cancelled — no result was produced.")} />
      <p className="result-boundary">{L("失败或取消的轮次不会补出结果投影。要判断出了什么问题，请查看执行进度里的失败原因；处理后再提交一次。", "Failed or cancelled rounds never gain a result projection. To see what went wrong, check the failure cause in the execution progress; fix it and resubmit.")}</p>
    </>) : <Empty text={L("任务还在处理中，完成后会在这里显示改动、检查结果和下一步。", "The task is still in progress — changes, gate results and the next step will appear here when it completes.")} />}</Panel> : <>
      <section className={"result-overview " + (completed ? "result-complete" : "result-attention")}><div className="eyebrow">{L("开发结论", "DEVELOPMENT RESULT")}</div><h2>{completed ? L("开发执行完成，准备审阅改动", "Development complete — review the change") : job.status === "CANCELLED" ? L("任务已取消", "Task cancelled") : L("执行未完成，需要处理问题", "Run incomplete — issues need attention")}</h2><p title={result.reason || undefined}>{result.reason ? describePipelineError(String(result.reason)) : (completed ? L("先查看代码差异和下方检查结果，再对这次变更进行独立验收。", "Review the diff and the gate results below, then put this change through independent acceptance.") : L("请到执行进度中查看失败原因，调整需求或环境后重新提交。", "See the failure cause in the execution progress; adjust the requirement or the environment and resubmit."))}</p><div className="result-actions"><a className="btn btn-primary" href={"#/agent/jobs/" + jobId + "/diff"}>{L("审阅代码差异 →", "Review the code diff →")}</a><a className="btn" href={"#/jobs/new?repo=" + encodeURIComponent(job.repo_path)}>{L("新建独立验收", "New independent acceptance")}</a></div></section>
      <div className="metrics-grid result-metrics"><div className="metric-card"><div className="metric-top">{L("改动文件", "Files changed")}</div><strong>{result.diff_stat?.files_changed ?? "—"}</strong><small>{L("本次执行记录的文件变更", "Files recorded by this run")}</small></div><div className="metric-card"><div className="metric-top">{L("执行阶段模型调用", "Model calls in this run")}</div><strong>{result.llm_usage?.calls ?? "—"}</strong><small>{models.join("、") || L("未记录模型调用", "No model calls recorded")}</small></div><div className="metric-card"><div className="metric-top">{L("通过的检查", "Gates passed")}</div><strong>{gates.length ? gates.filter(gate => gate.status === "passed").length + " / " + gates.length : "—"}</strong><small>{L("未执行的检查不算通过", "Gates not run do not count as passed")}</small></div></div>
      <Panel title={L("检查结果", "Gate results")}>{gates.length ? <div className="result-gates">{gates.map(gate => <div className="result-gate" key={gate.gate}><div><strong>{gateLabel(gate.gate)}</strong><span className={gateStatusPillClass(gate.status)} title={gate.status}>{gateStatusLabel(gate.status)}</span></div><p>{gate.note}</p></div>)}</div> : <Empty text={L("没有可读取的检查结果，请查看执行日志。", "No gate results can be read — see the execution log.")} />}<p className="result-boundary">{L("开发完成不等于独立验收通过。未执行或尚未覆盖的检查，需要在交付前补齐。", "Development complete does not mean acceptance passed. Gates that did not run or were not covered must be filled in before delivery.")}</p></Panel>
      {cacheNotes.length > 0 && <Panel title={L("依赖缓存完整性", "Dependency cache integrity")}>
        {cacheNotes.map(note => <p className="result-boundary" key={note}>{note}</p>)}
        {/* An empty note means the profile mounted no cache. That must stay
            silent rather than become "verified" — so this panel is absent, not
            reassuring, when there is nothing to disclose. */}
      </Panel>}
      {approvalsError ? <Panel title={L("审批记录", "Approvals")}><div className="errorbox" title={approvalsError instanceof Error ? approvalsError.message : String(approvalsError)}>审批记录暂时无法加载（请求失败）— 不代表没有审批，请稍后重试</div></Panel> : approvals.length > 0 ? <Panel title="审批记录">{approvals.map(approval => <ApprovalCard key={approval.id} approval={approval} />)}</Panel> : null}
      <details className="result-raw"><summary>{L("查看完整执行记录", "View the full execution record")}</summary><pre className="json">{JSON.stringify(result, null, 2)}</pre></details>
    </>}
    {/* Mounted outside the result branch on purpose: the accept projection is
        an independent record, and a job whose result row has not been written
        yet must still show whatever the acceptance closure did say. */}
    <AcceptProjection job={job} jobId={jobId} />
  </AgentJobShell>;
}
