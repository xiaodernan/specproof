import { useCallback, useEffect, useState } from "react";
import { ApiError, apiGet } from "../api";
import type { Column } from "../ui";
import {
  ErrorBox,
  Input,
  Panel,
  Select,
  Spinner,
  StatCard,
  Table,
  fmtTime,
  shortId,
} from "../ui";
import { auditDisposition } from "../ui/auditLabels";
import { AUDIT_ROLES } from "../ui/accessRoles";
import { useRoleAccess } from "../ui/useRoleAccess";
import { useI18n } from "../i18n";
import { AUDIT_BY_LOCALE, type AuditCopy } from "./audit.copy";

// Wire shape mirrors GET /api/v1/admin/audit (api/routes/admin.py), whose rows
// come from storage/mysql.py::audit_trail. `job_disposition` is stamped
// server-side; this page never re-derives it.
interface AuditRow {
  id: number;
  job_id: string | null;
  actor: string;
  action: string;
  from_status: string | null;
  to_status: string | null;
  detail: string | null;
  attempted_tenant: string | null;
  created_at: string | null;
  job_disposition: string | null;
}

interface AuditResponse {
  audit: AuditRow[];
  count: number;
  // `total` is how many audit rows the query actually covers (the whole table
  // unfiltered, one job's trail filtered); `job_present` is only answered for a
  // filtered read — null means the server did not probe it.
  total: number | null;
  job_id: string | null;
  job_present: boolean | null;
}

// The API validates 1..1000; offering more would only produce a 422.
const LIMITS = [100, 500, 1000];

// #/audit?job=<id> is the deep link JobDetail hands over. The hash is the one
// source of truth for the filter, so back/forward and a pasted link agree.
function jobFromHash(): string {
  const hash = window.location.hash || "";
  const queryIndex = hash.indexOf("?");
  if (queryIndex < 0) return "";
  const params = new URLSearchParams(hash.slice(queryIndex + 1));
  return (params.get("job") || "").trim();
}

function useAuditAccess(): { checked: boolean; canView: boolean } {
  // #117: one shared fail-closed body lives in ui/useRoleAccess.ts.
  const access = useRoleAccess(AUDIT_ROLES);
  return { checked: access.checked, canView: access.allowed };
}

function dispositionPill(raw: string | null): JSX.Element {
  const spec = auditDisposition(raw);
  return (
    <span className={"pill " + spec.cls} title={spec.hint} data-testid="audit-disposition">
      {spec.label}
    </span>
  );
}

// A filtered read that answers with nothing has three different meanings, and
// the page must not collapse them into "no records" — that sentence
// describes an unfiltered window, not the job the reader asked about.
function filteredEmpty(jobFilter: string, jobPresent: boolean | null, c: AuditCopy): JSX.Element {
  if (jobPresent === false) {
    return (
      <div data-testid="audit-job-missing">
        <h3>{c.missingJobTitle}</h3>
        <p className="muted">
          {c.missingJobBody(jobFilter)}
        </p>
      </div>
    );
  }
  if (jobPresent === true) {
    return (
      <div data-testid="audit-job-no-rows">
        <h3>{c.noRowsTitle}</h3>
        <p className="muted">
          {c.noRowsBody(jobFilter)}
        </p>
      </div>
    );
  }
  return (
    <div data-testid="audit-job-unknown">
      <h3>{c.unknownPresenceTitle}</h3>
      <p className="muted">
        {c.unknownPresenceBody}
      </p>
    </div>
  );
}

export default function Audit(): JSX.Element {
  const { locale } = useI18n();
  const c = AUDIT_BY_LOCALE[locale];
  const { checked, canView } = useAuditAccess();
  const [limit, setLimit] = useState<number>(100);
  const [jobFilter, setJobFilter] = useState<string>(() => jobFromHash());
  const [jobDraft, setJobDraft] = useState<string>("");
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [jobPresent, setJobPresent] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    const onChange = () => {
      const next = jobFromHash();
      setJobFilter(next);
      setJobDraft(next);
    };
    window.addEventListener("hashchange", onChange);
    onChange();
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  const load = useCallback(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    const query =
      "/api/v1/admin/audit?limit=" +
      limit +
      (jobFilter ? "&job_id=" + encodeURIComponent(jobFilter) : "");
    apiGet<AuditResponse>(query)
      .then((data) => {
        if (!alive) return;
        setRows(Array.isArray(data?.audit) ? data.audit : []);
        // null, not 0: a server that does not answer the total must not be
        // read as "there are none".
        setTotal(typeof data?.total === "number" ? data.total : null);
        setJobPresent(data?.job_present ?? null);
      })
      .catch((err: unknown) => {
        if (!alive) return;
        setRows([]);
        setTotal(null);
        setJobPresent(null);
        setError(err instanceof ApiError ? err : new ApiError(0, String(err)));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [limit, jobFilter]);
  // Ask only once the identity is known and permitted: a session the handler
  // will refuse should not fire a request it is told it cannot make. The
  // server stays authoritative — this only avoids a guaranteed 403 round-trip.
  useEffect(() => {
    if (!checked || !canView) return undefined;
    return load();
  }, [checked, canView, load, reload]);

  // The filter travels through the hash so one job's trail can be linked from
  // its job page or pasted to a colleague. Assigning the hash fires no event
  // when it already holds that value, so the state is set here as well.
  const applyJob = (raw: string) => {
    const next = raw.trim();
    const target = next ? "#/audit?job=" + encodeURIComponent(next) : "#/audit";
    if (window.location.hash !== target) window.location.hash = target;
    setJobFilter(next);
  };

  if (!canView) {
    return (
      <div>
        <div className="errorbox" data-testid="audit-forbidden" role="alert">
          {c.forbiddenText}
        </div>
        <Panel title={c.panelTitle}>
          <div className="kv">
            <span className="kv-label">{c.scopeLabel}</span>
            <span className="kv-value">
              {c.scopeValuePrefix}{AUDIT_ROLES.join(" / ")}{c.scopeValueSuffix}
            </span>
          </div>
          <div className="permission-hint">
            {c.hint}
          </div>
        </Panel>
      </div>
    );
  }

  const counts = rows.reduce<Record<string, number>>((acc, row) => {
    const key = row.job_disposition || "unregistered";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const unexplained = counts.unexplained || 0;

  const columns: Column<AuditRow>[] = [
    {
      key: "created_at",
      header: c.colTime,
      render: (row) => <span title={row.created_at || ""}>{fmtTime(row.created_at)}</span>,
    },
    { key: "actor", header: c.colActor, render: (row) => row.actor || c.actorEmpty },
    {
      key: "action",
      header: c.colAction,
      render: (row) => (
        <span title={row.detail || ""} data-testid="audit-action">
          {row.action}
        </span>
      ),
    },
    {
      key: "transition",
      header: c.colTransition,
      render: (row) =>
        row.from_status || row.to_status
          ? (row.from_status || c.transitionEmpty) + " → " + (row.to_status || c.transitionEmpty)
          : c.transitionEmpty,
    },
    {
      key: "job_id",
      header: c.colJob,
      render: (row) =>
        row.job_id ? (
          row.job_disposition === "present" ? (
            <a href={"#/jobs/" + encodeURIComponent(row.job_id)}>{shortId(row.job_id)}</a>
          ) : (
            <span title={row.job_id}>{shortId(row.job_id)}</span>
          )
        ) : (
          <span className="pill pill-mute">{c.noJob}</span>
        ),
    },
    {
      key: "job_disposition",
      header: c.colDisposition,
      render: (row) => dispositionPill(row.job_disposition),
    },
  ];

  return (
    <div className="page-stack">
      <Panel
        title={c.trailTitle}
        right={
          <div className="row-gap">
            <form
              className="row-gap"
              onSubmit={(event) => {
                event.preventDefault();
                applyJob(jobDraft);
              }}
            >
              <Input
                label={c.jobInputLabel}
                type="search"
                value={jobDraft}
                placeholder={c.jobInputPlaceholder}
                maxLength={64}
                onChange={(event) => setJobDraft(event.target.value)}
              />
              <button className="btn" type="submit">
                {c.query}
              </button>
              {jobFilter ? (
                <button
                  className="btn btn-ghost"
                  type="button"
                  onClick={() => applyJob("")}
                >
                  {c.clearFilter}
                </button>
              ) : null}
            </form>
            <Select
              label={c.limitLabel}
              value={String(limit)}
              onChange={(event) => setLimit(Number(event.target.value))}
            >
              {LIMITS.map((n) => (
                <option key={n} value={String(n)}>
                  {c.limitRows(n)}
                </option>
              ))}
            </Select>
            <button className="btn btn-ghost" onClick={() => setReload((v) => v + 1)}>
              {c.reload}
            </button>
          </div>
        }
      >
        {loading ? (
          <Spinner />
        ) : error ? (
          error.status === 503 ? (
            <div data-testid="audit-auth-disabled">
              <ErrorBox
                error={c.authDisabledPrefix + error.detail}
              />
              <p className="muted">
                {c.authDisabledHint}
              </p>
            </div>
          ) : error.status === 403 ? (
            <div data-testid="audit-denied">
              <ErrorBox error={c.deniedPrefix + error.detail} />
              <p className="muted">
                {c.deniedHint(AUDIT_ROLES.join(" / "))}
              </p>
            </div>
          ) : (
            <ErrorBox
              error={c.genericFailurePrefix + (error.code || error.status || c.unknownError) + "：" + error.detail}
            />
          )
        ) : jobFilter && rows.length === 0 ? (
          filteredEmpty(jobFilter, jobPresent, c)
        ) : (
          <Table
            columns={columns}
            rows={rows}
            rowKey={(row) => String(row.id)}
            emptyTitle={c.emptyTitle}
            emptyDescription={c.emptyDescription}
          />
        )}
      </Panel>
      {!loading && !error && (
        <div className="stat-grid">
          <StatCard label={c.statLoaded} value={rows.length} tone="info" />
          <StatCard label={c.statPresent} value={counts.present || 0} tone="ok" />
          <StatCard
            label={c.statPurged}
            value={counts.purged_by_lifecycle || 0}
            tone="mute"
          />
          <StatCard
            label={c.statUnexplained}
            value={unexplained}
            tone={unexplained ? "bad" : "mute"}
          />
        </div>
      )}
      {!loading && !error && jobFilter && (
        <p className="muted" data-testid="audit-filter-note">
          {c.filterNotePrefix}<code>{jobFilter}</code>{" · "}
          {jobPresent === false
            ? rows.length > 0
              ? c.filterNoteMissingWithRows
              : c.filterNoteMissingNoRows
            : jobPresent === true
              ? c.filterNotePresent
              : c.filterNoteUnknown}
          {jobPresent !== false ? (
            <a href={"#/jobs/" + encodeURIComponent(jobFilter)}>{c.filterNoteLink}</a>
          ) : null}
        </p>
      )}
      {!loading && !error && rows.length > 0 && (
        <p className="muted" data-testid="audit-scope-note">
          {total === null
            ? `${c.scopeNoteNull}`
            : total > rows.length
              ? c.scopeNotePartial(total, rows.length, total - rows.length)
              : c.scopeNoteAll(total)}{" "}
          {c.scopeNoteTail}
        </p>
      )}
      <Panel title={c.howToReadTitle}>
        <p className="muted">
          {c.howToReadBody}
        </p>
      </Panel>
    </div>
  );
}
