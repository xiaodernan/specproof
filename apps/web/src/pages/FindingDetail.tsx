import { useEffect, useState } from "react";
import {
  ApiError, NETWORK_UNREACHABLE, apiGet, createFindingFeedback, downloadCapsule, getJobFeedback,
  getReviewer, setReviewer, type FeedbackData, type FeedbackReceipt, type Finding, type FindingsData,
} from "../api";
import { Button, Degraded, Empty, ErrorBox, Input, Panel, SEVERITY_STOREABLE, Spinner, Term, Textarea, fmtPct, fmtTime, kv, severityPill, severityHint, evidenceLabel } from "../ui";

// The backend already scales this to a percentage; fmtPct() multiplies by
// 100, so routing it through fmtPct would print "5000.0%" for a 50% rate.
function rateText(pct: number | null): string {
  if (pct === null || pct === undefined) return "无法计算（还没有人投票）";
  return pct.toFixed(1) + "%";
}

function describeFeedbackError(e: unknown): string {
  if (e instanceof ApiError) {
    return e.detail + "（HTTP " + e.status + (e.code ? " · " + e.code : "") + "）";
  }
  if (e instanceof Error && e.message === NETWORK_UNREACHABLE) {
    return "网络不可达：反馈服务没有响应，这一票没有记上";
  }
  return e instanceof Error ? e.message : String(e);
}

const STATE_TEXT: Record<FeedbackReceipt["state"], string> = {
  created: "已记下你的一票（这个 finding 的第一条记录）",
  replaced: "已覆盖你之前的一票 —— 同一个人只算一票，不会加权",
  unchanged: "你之前已经投过完全相同的一票，本次没有重复计数",
};

// finding_feedback.severity is the SAME MySQL ENUM as the backend request
// pattern (infra/mysql/migrations/0009 + api/routes/feedback.py), and the
// vocabulary lives in exactly one place: ui/toneMap.ts. A severity outside it
// cannot be stored, so the buttons stay off with the reason on screen —
// enabling them would trade a dead click for a 422 the reviewer cannot act on.

export function FeedbackSection(props: { jobId: string; finding: Finding }) {
  const { jobId, finding } = props;
  const [data, setData] = useState<FeedbackData | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const [reviewer, setReviewerName] = useState(getReviewer());
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<"accept" | "reject" | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<FeedbackReceipt | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setLoadError(null);
    getJobFeedback(jobId)
      .then((d) => {
        if (alive) setData(d);
      })
      .catch((e) => {
        // A failed load must never look like "nobody voted".
        if (alive) {
          setData(null);
          setLoadError(describeFeedbackError(e));
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [jobId, reload]);

  const findingId = finding.id ? String(finding.id) : "";
  const who = reviewer.trim();
  const mine = data && findingId
    ? data.rows.find((r) => r.finding_id === findingId && r.created_by === who)
    : undefined;
  const severity = finding.severity ? String(finding.severity) : "";
  const blocking = !findingId
    ? "这条风险没有 id，无法把票挂到它上面（不替你编一个）"
    : !finding.contract_id
      ? "这条风险缺少验收条件编号，后端要求随票一起记录，缺任何一项都无法提交"
      : !SEVERITY_STOREABLE.includes(severity)
        ? "这条风险的严重程度是 " + (severity || "未知") + "，不在后端可记录的值（" +
          SEVERITY_STOREABLE.join("/") + "）之内，所以这一票没有地方存 —— 不是不让你投，是存下来就会说谎"
        : null;

  async function submit(verdict: "accept" | "reject") {
    setFormError(null);
    setReceipt(null);
    if (blocking) {
      setFormError(blocking);
      return;
    }
    if (!who) {
      setFormError("请先填写评审人标识：后端按「同一个人对同一条风险只记一票」计数");
      return;
    }
    if (verdict === "reject" && !reason.trim()) {
      setFormError("打回必须写理由（修复者要知道按哪一条打回）；接受可以不写");
      return;
    }
    setBusy(verdict);
    try {
      const r = await createFindingFeedback(jobId, {
        finding_id: findingId,
        contract_id: String(finding.contract_id),
        severity,
        verdict,
        reason: reason.trim() || null,
        created_by: who,
      });
      setReviewer(who);
      setReceipt(r);
      setReload((k) => k + 1);
    } catch (e) {
      setFormError(describeFeedbackError(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Panel
      title={<Term id="feedback">验收反馈</Term>}
      right={data ? <span className="muted">{rateText(data.stats.acceptance_rate_pct)}</span> : null}
    >
      <div>
        <Input
          label="评审人标识"
          value={reviewer}
          onChange={(e) => setReviewerName(e.target.value)}
          hint="只存在本机浏览器；它是「一人一票」的计票依据，不是登录账号"
        />
        <Textarea
          label="理由（打回必填）"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={2}
          maxLength={1000}
        />
        {blocking ? <p className="severity-hint">{blocking}</p> : null}
        {mine ? (
          <p className="severity-hint">
            你当前的一票：{mine.verdict === "accept" ? "接受" : "打回"}
            {mine.reason ? " · " + mine.reason : ""}（{fmtTime(mine.created_at)}）
          </p>
        ) : null}
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <Button
            variant="primary"
            loading={busy === "accept"}
            disabled={busy !== null || !!blocking}
            onClick={() => submit("accept")}
          >
            接受这条判定
          </Button>
          <Button
            variant="danger"
            loading={busy === "reject"}
            disabled={busy !== null || !!blocking}
            onClick={() => submit("reject")}
          >
            打回（误报/证据不足）
          </Button>
        </div>
        {formError ? <ErrorBox error={formError} /> : null}
        {receipt ? <p className="severity-hint">{STATE_TEXT[receipt.state]}</p> : null}
      </div>

      {loading ? (
        <Spinner />
      ) : loadError ? (
        <div>
          <ErrorBox error={"反馈记录加载失败：" + loadError} />
          <Button variant="ghost" size="sm" onClick={() => setReload((k) => k + 1)}>
            重试
          </Button>
        </div>
      ) : !data || data.rows.length === 0 ? (
        <Empty text="还没有人提交过反馈。注意：没有反馈不等于已接受 —— 接受率在最常见情形下就是「无法计算」。" />
      ) : (
        <table className="data">
          <thead>
            <tr><th>评审人</th><th>判定</th><th>对应风险</th><th>理由</th><th>时间</th></tr>
          </thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={r.id}>
                <td className="mono">{r.created_by}{r.created_by === who ? "（你）" : ""}</td>
                <td>{r.verdict === "accept" ? "接受" : "打回"}</td>
                <td className="mono">{r.finding_id.slice(0, 8)}</td>
                <td>{r.reason || "—"}</td>
                <td className="mono">{fmtTime(r.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data ? (
        <p className="muted">
          本任务计票：接受 {data.stats.accepted} · 打回 {data.stats.rejected} · 接受率{" "}
          {rateText(data.stats.acceptance_rate_pct)}；没有反馈的风险不计入分母。
        </p>
      ) : null}
    </Panel>
  );
}


export default function FindingDetail(props: { jobId: string; findingId: string }) {
  const { jobId, findingId } = props;
  const [data, setData] = useState<FindingsData | null>(null);
  const [error, setError] = useState<Error | string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    apiGet<FindingsData>("/api/v1/jobs/" + encodeURIComponent(jobId) + "/findings")
      .then((d) => {
        if (alive) setData(d);
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
  }, [jobId]);

  if (loading) return <Spinner />;
  if (!data) return <ErrorBox error={error || "加载失败"} />;

  // Exact match only. /jobs/{job}/findings drops any row without an id
  // (api/routes/web.py), so a fuzzy fallback here could never rescue a real
  // payload — it could only pick a DIFFERENT finding than the URL asked for,
  // and a verdict recorded below would be attached to the wrong finding_id.
  const f = data.findings.find((x) => String(x.id) === findingId);
  if (!f) {
    return (
      <div>
        <ErrorBox error={"finding " + findingId + " 不存在于任务 " + jobId} />
        <a href={"#/jobs/" + jobId}>← 返回任务</a>
      </div>
    );
  }

  const sev = severityPill(f.severity);
  const sevHint = severityHint(f.severity);
  const impact = f.impact_path ? JSON.stringify(f.impact_path, null, 2) : null;

  return (
    <div>
      <div className="page-head">
        <h1 className="mono">
          风险详情 {f.id} <span className={"pill " + sev.cls}>{sev.label}</span>
        </h1>
        {sevHint ? <p className="severity-hint">{sevHint}</p> : null}
        <div className="page-sub">
          任务 {jobId} · 验收条件 {f.contract_id || "—"}
        </div>
      </div>
      <ErrorBox error={error} />
      {data.degraded ? <Degraded reasons={[data.degraded_reason || "degraded"]} /> : null}

      <div className="page-grid">
        <Panel title="基本信息">
          {kv("严重程度", sev.label + (sevHint ? " · " + sevHint.split("——")[0] : ""))}
          {kv("对应验收条件", f.contract_id || "—")}
          {kv("证据方式", evidenceLabel(f.evidence_type))}
          {kv("置信度", fmtPct(f.confidence))}
          {kv("代码位置", f.location || "—")}
          {kv("问题类型", f.type || "—")}
          {kv(<Term id="capsule">复现包</Term>, f.capsule_path ? String(f.capsule_path) : "—")}
        </Panel>
        <Panel title="问题描述">
          <p>{f.description || "无描述"}</p>
        </Panel>
      </div>

      <Panel title="影响路径">
        {impact ? <pre className="json">{impact}</pre> : <Empty text="该风险暂无影响路径记录（诚实空态：未编造调用链）。" />}
      </Panel>

      <Panel title={<Term id="evidence">证据来源</Term>}>
        <table className="data">
          <tbody>
            <tr><td className="kv-label">证据方式</td><td className="mono">{evidenceLabel(f.evidence_type)}</td></tr>
            <tr><td className="kv-label">代码位置</td><td className="mono">{f.location || "—"}</td></tr>
            <tr><td className="kv-label">置信度</td><td className="mono">{fmtPct(f.confidence)}</td></tr>
          </tbody>
        </table>
      </Panel>

      <FeedbackSection jobId={jobId} finding={f} />

      <div style={{ display: "flex", gap: 10 }}>
        <a className="btn btn-ghost" href={"#/jobs/" + jobId}>← 返回任务</a>
        {f.capsule_path ? (
          <Button variant="secondary" onClick={() => downloadCapsule(jobId, String(f.capsule_path).split("/").pop())}>
            下载复现包 ↓
          </Button>
        ) : null}
      </div>
    </div>
  );
}
