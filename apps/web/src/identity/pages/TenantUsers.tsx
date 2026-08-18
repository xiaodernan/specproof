import { useEffect, useState } from "react";
import {
  UserRow,
  createUser,
  listUsers,
  setUserRole,
  setUserStatus,
} from "../../api";
import { Empty, ErrorBox, Panel } from "../../components";

// User management (RBAC: admin/operator). Operators always act on their own
// tenant — a request-side tenant override is ignored by the backend, and
// cross-tenant user ids answer 404, which renders as the ApiError text.
export default function TenantUsers() {
  const [users, setUsers] = useState<UserRow[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("viewer");
  const [error, setError] = useState<Error | string | null>(null);
  const [loading, setLoading] = useState(true);

  function reload() {
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

  useEffect(reload, []);

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

  return (
    <div>
      <div className="page-head">
        <h1>用户管理 Users</h1>
        <div className="page-sub">IDENTITY — 当前租户用户 (RBAC: admin/operator)</div>
      </div>
      <Panel title="新建用户">
        <div style={{ display: "flex", gap: 8 }}>
          <input
            type="text"
            value={email}
            placeholder="user@example.com"
            onChange={(e) => setEmail(e.target.value)}
          />
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="viewer">viewer</option>
            <option value="operator">operator</option>
            <option value="auditor">auditor</option>
            <option value="admin">admin</option>
          </select>
          <button className="btn" onClick={create}>
            创建 Create
          </button>
        </div>
        <div className="muted" style={{ marginTop: 8 }}>
          operator 只能授予 viewer/operator; admin 角色仅 admin 可授予 (后端强制)。
        </div>
      </Panel>
      <ErrorBox error={error} />
      <Panel title="用户列表">
        {loading ? (
          <div className="spinner">加载中 LOADING…</div>
        ) : users.length === 0 ? (
          <Empty text="暂无用户 No users" />
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>邮箱 Email</th>
                <th>角色 Role</th>
                <th>状态 Status</th>
                <th>操作 Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.email}</td>
                  <td>
                    <span className="pill pill-mute">{u.role}</span>
                  </td>
                  <td>{u.status}</td>
                  <td style={{ display: "flex", gap: 6 }}>
                    <select
                      value={u.role}
                      onChange={(e) => changeRole(u, e.target.value)}
                    >
                      <option value="viewer">viewer</option>
                      <option value="operator">operator</option>
                      <option value="auditor">auditor</option>
                      <option value="admin">admin</option>
                    </select>
                    <button className="btn btn-ghost" onClick={() => toggleStatus(u)}>
                      {u.status === "active" ? "停用 Disable" : "启用 Enable"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
