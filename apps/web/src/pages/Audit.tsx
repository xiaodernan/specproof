import { useCallback, useEffect, useState } from "react";
import { ApiError, apiGet, getAuthMe } from "../api";
import type { PrincipalInfo } from "../api";
import type { Column } from "../ui";
import {
  ErrorBox,
  Panel,
  Select,
  Spinner,
  StatCard,
  Table,
  fmtTime,
  shortId,
} from "../ui";
import { AUDIT_ROLES, auditDisposition } from "../ui/auditLabels";

// Wire shape mirrors GET /api/v1/admin/audit (api/routes/admin.py), whose rows
// come from storage/mysql.py::list_audit_logs. `job_disposition` is stamped
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
}

// The API validates 1..1000; offering more would only produce a 422.
const LIMITS = [100, 500, 1000];

function useAuditAccess(): { checked: boolean; canView: boolean } {
  const [principal, setPrincipal] = useState<PrincipalInfo | null>(null);
  const [checked, setChecked] = useState(false);
  useEffect(() => {
    let alive = true;
    getAuthMe()
      .then((me) => {
        if (alive && me && me.principal) setPrincipal(me.principal);
      })
      .catch(() => {
        // Unknown identity stays fail-open for visibility only; the server is
        // fail-closed and its 403 is rendered as its own state below.
      })
      .finally(() => {
        if (alive) setChecked(true);
      });
    return () => {
      alive = false;
    };
  }, []);
  const canView =
    !checked ||
    principal == null ||
    !Array.isArray(principal.roles) ||
    AUDIT_ROLES.some((role) => principal.roles.includes(role));
  return { checked, canView };
}

function dispositionPill(raw: string | null): JSX.Element {
  const spec = auditDisposition(raw);
  return (
    <span className={"pill " + spec.cls} title={spec.hint} data-testid="audit-disposition">
      {spec.label}
    </span>
  );
}

export default function Audit(): JSX.Element {
  const { checked, canView } = useAuditAccess();
  const [limit, setLimit] = useState<number>(100);
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [reload, setReload] = useState(0);
  const load = useCallback(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    apiGet<AuditResponse>("/api/v1/admin/audit?limit=" + limit)
      .then((data) => {
        if (!alive) return;
        setRows(Array.isArray(data?.audit) ? data.audit : []);
      })
      .catch((err: unknown) => {
        if (!alive) return;
        setRows([]);
        setError(err instanceof ApiError ? err : new ApiError(0, String(err)));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [limit]);
  // Ask only once the identity is known and permitted: a session the handler
  // will refuse should not fire a request it is told it cannot make. The
  // server stays authoritative — this only avoids a guaranteed 403 round-trip.
  useEffect(() => {
    if (!checked || !canView) return undefined;
    return load();
  }, [checked, canView, load, reload]);

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
      {!loading && !error && rows.length > 0 && (
        <p className="muted" data-testid="audit-scope-note">
          以上计数只统计本页已加载的 {rows.length} 条，不代表全部审计历史。
        </p>
      )}
      <Panel title="怎么读这张表 How to read">
        <p className="muted">
          每条审计只保存作业号，不保存作业本身。删除作业记录时，系统会在同一事务里补一行
          job_records_deleted 说明，因此“作业已删除”是可解释的正常状态；三者都对不上的行会被标成
          “引用无法解释”，它需要人工排查，而不是被隐藏。
        </p>
      </Panel>
    </div>
  );
}
