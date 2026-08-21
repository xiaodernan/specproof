import { Panel } from "../ui";

// Shared forbidden view for the identity console (RBAC: admin/operator).
// The errorbox keeps the W39 e2e contract (data-testid="identity-forbidden",
// role="alert") and adds the §14.4 permission explanation — tenant / role /
// source / expiry — plus an actionable contact-admin hint. The backend
// stays the authority: this UI gate is visibility-only, enforcement is
// fail-closed server-side.
export function PermissionDenied(props: { action: string }): JSX.Element {
  return (
    <div>
      <div className="errorbox" data-testid="identity-forbidden" role="alert">
        无权限 NO ACCESS — {props.action}
      </div>
      <Panel title="权限说明 Permission explanation">
        <div className="kv">
          <span className="kv-label">租户 Tenant</span>
          <span className="kv-value">
            当前凭据所属租户决定可见的数据范围; 服务端从不信任客户端传来的 tenant id — 跨租户请求一律 401/403。
          </span>
        </div>
        <div className="kv">
          <span className="kv-label">角色 Role</span>
          <span className="kv-value">
            管理页面仅对 admin / operator 开放; viewer 保留只读能力 (jobs:read 等)。角色变更由管理员操作, 前端不能自行提升。
          </span>
        </div>
        <div className="kv">
          <span className="kv-label">来源 Source</span>
          <span className="kv-value">
            权限来自服务端 /auth/me 解析的当前身份 (sp_* 令牌或 OIDC id_token); 本页仅做可见性门控, 服务端 RBAC fail-closed 才是权威。
          </span>
        </div>
        <div className="kv">
          <span className="kv-label">失效 Expiry</span>
          <span className="kv-value">
            令牌过期或被吊销后, 所有管理接口立即返回 401/403; 重新登录或切换为有效令牌后生效。
          </span>
        </div>
        <div className="permission-hint" data-testid="contact-admin-hint">
          需要访问? 请联系租户管理员 Contact admin — 请管理员在 身份 Identity 页将你的角色提升为 admin/operator, 或为你签发新的 API 令牌。
        </div>
      </Panel>
    </div>
  );
}
