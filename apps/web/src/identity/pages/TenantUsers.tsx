import { useEffect, useState } from "react";
import {
  UserRow,
  createUser,
  listUsers,
  setUserRole,
  setUserStatus,
} from "../../api";
import { Button, ErrorBox, Panel, Table, type Column } from "../../ui";
import { loadFailed } from "../../ui/errorHints";
import { PermissionDenied } from "../PermissionDenied";
import { useIdentityAccess } from "../useIdentityAccess";
import { roleLabel, userStatusLabel } from "../labels";
import { storedLocale } from "../../i18n/strings";

const isZh = (): boolean => storedLocale() === "zh";
const L = (zh: string, en: string): string => (isZh() ? zh : en);


// User management (RBAC: admin/operator). Operators always act on their own
// tenant — a request-side tenant override is ignored by the backend, and
// cross-tenant user ids answer 404, which renders as the ApiError text.
export default function TenantUsers() {
  const { canManage } = useIdentityAccess();
  const [users, setUsers] = useState<UserRow[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("viewer");
  const [error, setError] = useState<Error | string | null>(null);
  const [loading, setLoading] = useState(true);

  function reload() {
    setError(null);
    setLoading(true);
    listUsers()
      .then((data) => {
        setUsers(data.users);
        setLoading(false);
      })
      .catch((e: Error) => {
        setError(e);
        setLoading(false);
      });
  }

  useEffect(() => {
    if (canManage) reload();
  }, [canManage]);

  if (!canManage) {
    return (
      <div>
        <div className="page-head">
          <h1>{L("用户管理", "Users")}</h1>
          <div className="page-sub">{L("IDENTITY — 当前租户用户", "Identity — users in this tenant")} (RBAC: admin/operator)</div>
        </div>
        <PermissionDenied action={L("用户管理仅对 admin/operator 开放 (RBAC fail-closed)", "User management is admin/operator only (RBAC fail-closed)")} />
      </div>
    );
  }

  function create() {
    setError(null);
    createUser(email.trim(), role)
      .then(() => {
        setEmail("");
        reload();
      })
      .catch((e: Error) => setError(e));
  }

  function changeRole(user: UserRow, next: string) {
    setError(null);
    setUserRole(user.id, next)
      .then(reload)
      .catch((e: Error) => setError(e));
  }

  function toggleStatus(user: UserRow) {
    setError(null);
    setUserStatus(user.id, user.status === "active" ? "disabled" : "active")
      .then(reload)
      .catch((e: Error) => setError(e));
  }

  const columns: Column<UserRow>[] = [
    { key: "email", header: L("邮箱", "Email"), sortable: true },
    {
      key: "role",
      header: L("角色", "Role"),
      sortable: true,
      render: (u) => (
        <span className="pill pill-mute" title={u.role}>
          {roleLabel(u.role)}
        </span>
      ),
    },
    {
      key: "status",
      header: L("状态", "Status"),
      sortable: true,
      render: (u) => <span title={u.status}>{userStatusLabel(u.status)}</span>,
    },
    {
      key: "actions",
      header: L("操作", "Actions"),
      render: (u) => (
        <span style={{ display: "flex", gap: 6 }}>
          <select value={u.role} aria-label={L("用户角色", "User role") + " — " + u.email} onChange={(e) => changeRole(u, e.target.value)}>
            <option value="viewer">viewer</option>
            <option value="operator">operator</option>
            <option value="auditor">auditor</option>
            <option value="admin">admin</option>
          </select>
          <Button variant="ghost" size="sm" onClick={() => toggleStatus(u)}>
            {u.status === "active" ? L("停用", "Disable") : L("启用", "Enable")}
          </Button>
        </span>
      ),
    },
  ];

  return (
    <div>
      <div className="page-head">
        <h1>{L("用户管理", "Users")}</h1>
        <div className="page-sub">{L("IDENTITY — 当前租户用户（RBAC: admin/operator）", "IDENTITY — users of the current tenant (RBAC: admin/operator)")}</div>
      </div>
      <Panel title={L("新建用户", "New user")}>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            type="text"
            aria-label={L("新用户邮箱", "New user email")}
            value={email}
            placeholder="user@example.com"
            onChange={(e) => setEmail(e.target.value)}
          />
          <select aria-label={L("用户角色", "User role")} value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="viewer">viewer</option>
            <option value="operator">operator</option>
            <option value="auditor">auditor</option>
            <option value="admin">admin</option>
          </select>
          <Button variant="primary" onClick={create}>
            {L("创建", "Create")}
          </Button>
        </div>
        <div className="muted" style={{ marginTop: 8 }}>
          {L("operator 只能授予 viewer/operator；admin 角色仅 admin 可授予（后端强制）。", "Operators can only grant viewer/operator; admin role can only be granted by an admin (server-enforced).")}
        </div>
      </Panel>
      <ErrorBox error={error} />
      <Panel title={L("用户列表", "Users")}>
        {loadFailed(error) ? (
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span>{L("用户列表暂时无法加载（请求失败）——这不代表没有用户。", "The user list cannot be loaded right now (request failed) — this does NOT mean there are no users.")}</span>
            <Button variant="secondary" size="sm" onClick={reload}>{L("重试", "Retry")}</Button>
          </div>
        ) : loading ? (
          <div className="spinner">{L("加载中…", "Loading…")}</div>
        ) : (
          <Table<UserRow>
            columns={columns}
            rows={users}
            rowKey={(u) => u.id}
            emptyTitle={L("暂无用户", "No users yet")}
            emptyDescription={L("当前租户还没有用户，可在上方「新建用户」创建。", "This tenant has no users yet — create one above.")}
          />
        )}
      </Panel>
    </div>
  );
}
