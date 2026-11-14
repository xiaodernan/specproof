import { useEffect, useState } from "react";
import { useI18n } from "../i18n";
import {
  ApiError, networkUnreachableMessage, apiGet, createFindingFeedback, downloadCapsule, getJobFeedback,
  getReviewer, setReviewer, type FeedbackData, type FeedbackReceipt, type Finding, type FindingsData,
} from "../api";
import { Button, Degraded, Empty, ErrorBox, Input, Panel, SEVERITY_STOREABLE, Spinner, Table, Term, Textarea, fmtPct, fmtTime, kv, severityPill, severityHint, evidenceLabel } from "../ui";
import { FEEDBACK_VOTE_ROLES } from "../ui/accessRoles";
import { useRoleAccess } from "../ui/useRoleAccess";
import { feedbackVerdictLabel } from "../ui/util";

// The backend already scales this to a percentage; fmtPct() multiplies by
// 100, so routing it through fmtPct would print "5000.0%" for a 50% rate.
function rateText(t: (key: string) => string, pct: number | null): string {
  if (pct === null || pct === undefined) return t("fd.rateUnavailable");
  return pct.toFixed(1) + "%";
}

function describeFeedbackError(t: (key: string) => string, e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 403) {
      // Two independent gates can refuse this call for opposite fixes (role
      // matrix vs token scopes), so the server's own sentence is printed
      // rather than paraphrased into one of them. The code is shown only when
      // the envelope carries one — there is no invented placeholder here.
      return t("fd.perms403")
        .replace("{code}", e.code ? " · " + e.code : "")
        .replace("{detail}", e.detail);
    }
    return e.detail + "（HTTP " + e.status + (e.code ? " · " + e.code : "") + "）";
  }
  if (e instanceof Error && e.message === networkUnreachableMessage()) {
    return t("fd.networkUnreachable");
  }
  return e instanceof Error ? e.message : String(e);
}

const STATE_KEYS: Record<FeedbackReceipt["state"], string> = {
  created: "fd.receiptCreated",
  replaced: "fd.receiptReplaced",
  unchanged: "fd.receiptUnchanged",
};

function receiptText(t: (key: string) => string, state: FeedbackReceipt["state"]): string {
  return t(STATE_KEYS[state]);
}

// finding_feedback.severity is the SAME MySQL ENUM as the backend request
// pattern (infra/mysql/migrations/0009 + api/routes/feedback.py), and the
// vocabulary lives in exactly one place: ui/toneMap.ts. A severity outside it
// cannot be stored, so the buttons stay off with the reason on screen —
// enabling them would trade a dead click for a 422 the reviewer cannot act on.

export function FeedbackSection(props: { jobId: string; finding: Finding }) {
  const { t } = useI18n();
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
  const vote = useRoleAccess(FEEDBACK_VOTE_ROLES);

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
          setLoadError(describeFeedbackError(t, e));
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
  // #115b: this is BOTH what the box shows and what the "my current vote" lookup below
  // compares against. cb55acd made the ledger record the session identity, so leaving
  // this as the local name showed one identity in the box and filed the vote under
  // another -- and `mine` then never matched the reviewer's own recorded vote.
  const who = (vote.userId ?? reviewer).trim();
  const mine = data && findingId
    ? data.rows.find((r) => r.finding_id === findingId && r.created_by === who)
    : undefined;
  const severity = finding.severity ? String(finding.severity) : "";
  const notYourVote = vote.known && !vote.allowed
    ? t("fd.notYourVote").replace("{roles}", FEEDBACK_VOTE_ROLES.join(" / "))
    : null;
  const blocking = notYourVote ?? (!findingId
    ? t("fd.noFindingId")
    : !finding.contract_id
      ? t("fd.noContractId")
      : !SEVERITY_STOREABLE.includes(severity)
        ? t("fd.severityUnstorable")
            .replace("{sev}", severity || "?")
            .replace("{allowed}", SEVERITY_STOREABLE.join("/"))
        : null);

  async function submit(verdict: "accept" | "reject") {
    setFormError(null);
    setReceipt(null);
    if (blocking) {
      setFormError(blocking);
      return;
    }
    if (!who) {
      setFormError(t("fd.reviewerRequired"));
      return;
    }
    if (verdict === "reject" && !reason.trim()) {
      setFormError(t("fd.rejectReasonRequired"));
      return;
    }
    setBusy(verdict);
    try {
      // #121: wait for the identity ONLY while /auth/me is still in flight. Once the
      // check has settled the vote goes out in this same tick -- #116 certifies that a
      // granted role's click actually casts, and an unconditional await delayed it by a
      // microtask (measured: that test went red on `toHaveBeenCalledTimes(1)`).
      const settled = vote.checked ? null : await vote.identity;
      const reviewerKey = (vote.userId ?? settled ?? reviewer).trim();
      const r = await createFindingFeedback(jobId, {
        finding_id: findingId,
        contract_id: String(finding.contract_id),
        severity,
        verdict,
        reason: reason.trim() || null,
        created_by: reviewerKey,
      });
      setReviewer(who);
      setReceipt(r);
      setReload((k) => k + 1);
    } catch (e) {
      setFormError(describeFeedbackError(t, e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Panel
      title={<Term id="feedback">{t("fd.panelFeedback")}</Term>}
      right={data ? <span className="muted">{rateText(t, data.stats.acceptance_rate_pct)}</span> : null}
    >
      <div>
        <Input
          label={t("fd.reviewerFieldLabel")}
          value={who}
          onChange={(e) => setReviewerName(e.target.value)}
          readOnly={!!vote.userId}
          hint={
            vote.userId
              ? t("fd.reviewerSelfClaim").replace("{who}", vote.userId)
              : t("fd.reviewerGuestClaim")
          }
        />
        <Textarea
          label={t("fd.reasonLabel")}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={2}
          maxLength={1000}
        />
        {blocking ? <p className="severity-hint">{blocking}</p> : null}
        {mine ? (
          <p className="severity-hint">
            {t("fd.yourVote")}{feedbackVerdictLabel(mine.verdict)}
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
            {t("fd.accept")}
          </Button>
          <Button
            variant="danger"
            loading={busy === "reject"}
            disabled={busy !== null || !!blocking}
            onClick={() => submit("reject")}
          >
            {t("fd.reject")}
          </Button>
        </div>
        {formError ? <ErrorBox error={formError} /> : null}
        {receipt ? <p className="severity-hint">{receiptText(t, receipt.state)}</p> : null}
      </div>

      {loading ? (
        <Spinner />
      ) : loadError ? (
        <div>
          <ErrorBox error={t("fd.loadFailed") + loadError} />
          <Button variant="ghost" size="sm" onClick={() => setReload((k) => k + 1)}>
            {t("fd.retry")}
          </Button>
        </div>
      ) : !data || data.rows.length === 0 ? (
        <Empty text={t("fd.emptyFeedback")} />
      ) : (
        // Through the shared table (#122): 理由 is the one cell on this page a
        // human types freely, and `.ui-table-wrap` scrolls a long unbroken
        // reason inside the panel instead of widening the whole page.
        <Table
          rows={data.rows}
          rowKey={(r) => r.id}
          columns={[
            {
              key: "created_by",
              header: t("fd.colReviewer"),
              render: (r) => (
                <span className="mono">
                  {r.created_by}
                  {r.created_by === who ? t("fd.youSuffix") : ""}
                </span>
              ),
            },
            { key: "verdict", header: t("fd.colVerdict"), render: (r) => feedbackVerdictLabel(r.verdict) },
            {
              key: "finding_id",
              header: t("fd.colFinding"),
              render: (r) => <span className="mono">{r.finding_id.slice(0, 8)}</span>,
            },
            { key: "reason", header: t("fd.colReason"), render: (r) => r.reason || "—" },
            {
              key: "created_at",
              header: t("fd.colTime"),
              render: (r) => <span className="mono">{fmtTime(r.created_at)}</span>,
            },
          ]}
        />
      )}
      {data ? (
        <p className="muted">
          {t("fd.tally")
            .replace("{a}", String(data.stats.accepted))
            .replace("{r}", String(data.stats.rejected))
            .replace("{rate}", rateText(t, data.stats.acceptance_rate_pct))}
        </p>
      ) : null}
    </Panel>
  );
}


export default function FindingDetail(props: { jobId: string; findingId: string }) {
  const { t } = useI18n();
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
  if (!data) return <ErrorBox error={(error as Error | null)?.message || t("fd.loadingFailed")} />;

  // Exact match only. /jobs/{job}/findings drops any row without an id
  // (api/routes/web.py), so a fuzzy fallback here could never rescue a real
  // payload — it could only pick a DIFFERENT finding than the URL asked for,
  // and a verdict recorded below would be attached to the wrong finding_id.
  const f = data.findings.find((x) => String(x.id) === findingId);
  if (!f) {
    return (
      <div>
        <ErrorBox error={t("fd.nonexistentFinding").replace("{id}", findingId).replace("{job}", jobId)} />
        <a href={"#/jobs/" + jobId}>{t("fd.backToJob")}</a>
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
          {t("fd.findingDetail")}{f.id} <span className={"pill " + sev.cls}>{sev.label}</span>
        </h1>
        {sevHint ? <p className="severity-hint">{sevHint}</p> : null}
        <div className="page-sub">
          {t("fd.jobContractLine").replace("{job}", jobId).replace("{contract}", String(f.contract_id || "—"))}
        </div>
      </div>
      <ErrorBox error={error} />
      {data.degraded ? <Degraded reasons={[data.degraded_reason || "degraded"]} /> : null}

      <div className="page-grid">
        <Panel title={t("fd.basicInfo")}>
          {kv(t("fd.kvSeverity"), sev.label + (sevHint ? " · " + sevHint.split("——")[0] : ""))}
          {kv(t("fd.kvContract"), f.contract_id || "—")}
          {kv(t("fd.kvEvidence"), evidenceLabel(f.evidence_type))}
          {kv(t("fd.kvConfidence"), fmtPct(f.confidence))}
          {kv(t("fd.kvLocation"), f.location || "—")}
          {kv(t("fd.kvType"), f.type || "—")}
          {kv(<Term id="capsule">{t("fd.kvCapsule")}</Term>, f.capsule_path ? String(f.capsule_path) : "—")}
        </Panel>
        <Panel title={t("fd.descPanel")}>
          <p>{f.description || t("fd.noDesc")}</p>
        </Panel>
      </div>

      <Panel title={t("fd.impactPanel")}>
        {impact ? <pre className="json">{impact}</pre> : <Empty text={t("fd.noImpact")} />}
      </Panel>

      <Panel title={<Term id="evidence">{t("fd.evidencePanel")}</Term>}>
        {/* Three label/value pairs, not a table: `.kv-value` wraps a long
            unbroken path (`word-break: break-all`), which is the whole point —
            a <td> here had no way to break one (#122). */}
        {kv(t("fd.kvEvidence"), evidenceLabel(f.evidence_type))}
        {kv(t("fd.kvLocation"), f.location || "—")}
        {kv(t("fd.kvConfidence"), fmtPct(f.confidence))}
      </Panel>

      <FeedbackSection jobId={jobId} finding={f} />

      <div style={{ display: "flex", gap: 10 }}>
        <a className="btn btn-ghost" href={"#/jobs/" + jobId}>{t("fd.backToJob")}</a>
        {f.capsule_path ? (
          <Button variant="secondary" onClick={() => downloadCapsule(jobId, String(f.capsule_path).split("/").pop())}>
            {t("fd.downloadCapsule")}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
