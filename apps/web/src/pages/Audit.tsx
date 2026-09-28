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
  // #117: this used to be a second hand-written copy of the /auth/me + fail-open
  // body. One body now — ui/useRoleAccess.ts — so the three pages cannot
  // disagree about what 'identity unknown' means while still naming the same
  // shared role set. tests/unit/test_access_role_parity.py refuses a new copy.
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
// the page must not collapse them into "最近没有审计记录" — that sentence
// describes an unfiltered window, not the job the reader asked about.
function filteredEmpty(jobFilter: string, jobPresent: boolean | null): JSX.Element {
  if (jobPresent === false) {
    return (
      <div data-testid="audit-job-missing">
        <h3>没有找到这个作业号</h3>
        <p className="muted">
          库里既没有 <code>{jobFilter}</code> 这条作业，也没有它留下的任何审计行。
          审计行不会因为作业被删除而消失，所以这通常意味着作业号抄错了。
        </p>
      </div>
    );
  }
  if (jobPresent === true) {
    return (
      <div data-testid="audit-job-no-rows">
        <h3>作业在册，但没有审计行</h3>
        <p className="muted">
          <code>{jobFilter}</code> 存在于 verification_jobs，却没有记录任何状态转换或取消动作。
          新建后尚未被 worker 领取的作业就是这样；如果它已经跑完，说明有写入路径绕过了审计。
        </p>
      </div>
    );
  }
  return (
    <div data-testid="audit-job-unknown">
      <h3>这个作业号没有返回审计行</h3>
      <p className="muted">
        服务端没有回传该作业是否存在（job_present 为空），所以无法区分“抄错作业号”与
        “作业在但没有审计行”。请确认 API 版本已支持按作业检索。
      </p>
    </div>
  );
}

export default function Audit(): JSX.Element {
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
          当前身份没有审计读取权限。
        </div>
        <Panel title="权限说明 Permission explanation">
          <div className="kv">
            <span className="kv-label">范围 Scope</span>
            <span className="kv-value">
              审计读取仅对 {AUDIT_ROLES.join(" / ")} 角色开放；operator 与 viewer
              会被服务端以 TENANT_FORBIDDEN (403) 拒绝。
            </span>
          </div>
          <div className="permission-hint">
            需要访问？请联系租户管理员在 身份 Identity 页调整角色，或签发相应范围的令牌。
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
      header: "时间 Time",
      render: (row) => <span title={row.created_at || ""}>{fmtTime(row.created_at)}</span>,
    },
    { key: "actor", header: "操作者 Actor", render: (row) => row.actor || "—" },
    {
      key: "action",
      header: "动作 Action",
      render: (row) => (
        <span title={row.detail || ""} data-testid="audit-action">
          {row.action}
        </span>
      ),
    },
    {
      key: "transition",
      header: "状态转换 Transition",
      render: (row) =>
        row.from_status || row.to_status
          ? (row.from_status || "—") + " → " + (row.to_status || "—")
          : "—",
    },
    {
      key: "job_id",
      header: "作业 Job",
      render: (row) =>
        row.job_id ? (
          row.job_disposition === "present" ? (
            <a href={"#/jobs/" + encodeURIComponent(row.job_id)}>{shortId(row.job_id)}</a>
          ) : (
            <span title={row.job_id}>{shortId(row.job_id)}</span>
          )
        ) : (
          <span className="pill pill-mute">无作业号</span>
        ),
    },
    {
      key: "job_disposition",
      header: "作业去向 Disposition",
      render: (row) => dispositionPill(row.job_disposition),
    },
  ];

  return (
    <div className="page-stack">
      <Panel
        title="审计轨迹 Audit trail"
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
                label="按作业号过滤 Job id"
                type="search"
                value={jobDraft}
                placeholder="粘贴作业号后查询"
                maxLength={64}
                onChange={(event) => setJobDraft(event.target.value)}
              />
              <button className="btn" type="submit">
                查询
              </button>
              {jobFilter ? (
                <button
                  className="btn btn-ghost"
                  type="button"
                  onClick={() => applyJob("")}
                >
                  清除筛选
                </button>
              ) : null}
            </form>
            <Select
              label="读取条数 Limit"
              value={String(limit)}
              onChange={(event) => setLimit(Number(event.target.value))}
            >
              {LIMITS.map((n) => (
                <option key={n} value={String(n)}>
                  最近 {n} 条
                </option>
              ))}
            </Select>
            <button className="btn btn-ghost" onClick={() => setReload((v) => v + 1)}>
              重新读取
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
                error={
                  "这个部署没有开启多租户鉴权，审计接口不可用（不是没有记录）：" + error.detail
                }
              />
              <p className="muted">
                审计视图按租户鉴权暴露。开启方式：设置 SPECPROOF_AUTH_ENABLED=true
                或配置 OIDC_ISSUER 后重启 API。
              </p>
            </div>
          ) : error.status === 403 ? (
            <div data-testid="audit-denied">
              <ErrorBox error={"服务端拒绝了本次审计读取：" + error.detail} />
              <p className="muted">
                审计读取仅限 {AUDIT_ROLES.join(" / ")} 角色，请联系管理员调整。
              </p>
            </div>
          ) : (
            <ErrorBox
              error={"审计读取失败（" + (error.code || error.status || "未知错误") + "）：" + error.detail}
            />
          )
        ) : jobFilter && rows.length === 0 ? (
          filteredEmpty(jobFilter, jobPresent)
        ) : (
          <Table
            columns={columns}
            rows={rows}
            rowKey={(row) => String(row.id)}
            emptyTitle="最近没有审计记录"
            emptyDescription="完成一次验收或取消操作后，这里会出现对应的审计行。"
          />
        )}
      </Panel>
      {!loading && !error && (
        <div className="stat-grid">
          <StatCard label="已加载条数" value={rows.length} tone="info" />
          <StatCard label="作业在册" value={counts.present || 0} tone="ok" />
          <StatCard
            label="已按生命周期删除"
            value={counts.purged_by_lifecycle || 0}
            tone="mute"
          />
          <StatCard
            label="引用无法解释"
            value={unexplained}
            tone={unexplained ? "bad" : "mute"}
          />
        </div>
      )}
      {!loading && !error && jobFilter && (
        <p className="muted" data-testid="audit-filter-note">
          当前按作业号 <code>{jobFilter}</code> 检索 ·{" "}
          {jobPresent === false
            ? rows.length > 0
              ? "库里已无这条作业，下面这些是它留下的审计行；作业详情已经打不开"
              : "库里既没有这条作业，也没有它留下的审计行（见下方说明）；作业详情无从链接"
            : jobPresent === true
              ? "作业在册 · "
              : "服务端未回传作业是否存在 · "}
          {jobPresent !== false ? (
            <a href={"#/jobs/" + encodeURIComponent(jobFilter)}>查看作业详情</a>
          ) : null}
        </p>
      )}
      {!loading && !error && rows.length > 0 && (
        <p className="muted" data-testid="audit-scope-note">
          {total === null
            ? `服务端未回传命中总数，因此无法判断是否还有未加载的历史。`
            : total > rows.length
              ? `这次查询共命中 ${total} 条，这里显示最近的 ${rows.length} 条，另有 ${total - rows.length} 条未加载。`
              : `这次查询共命中 ${total} 条，已全部显示。`}{" "}
          统计卡只数本页已加载的行。
        </p>
      )}
      <Panel title="怎么读这张表 How to read">
        <p className="muted">
          每条审计只保存作业号，不保存作业本身。删除作业记录时，系统会在同一事务里补一行
          job_records_deleted 说明，因此“作业已删除”是可解释的正常状态；三者都对不上的行会被标成
          “引用无法解释”，它需要人工排查，而不是被隐藏。
          排查某一个作业时请用上方的作业号检索：整张表只返回最近若干条，
          一个作业的轨迹通常根本不在这个窗口里。
        </p>
      </Panel>
    </div>
  );
}
