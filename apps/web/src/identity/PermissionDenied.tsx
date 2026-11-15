import { Panel } from "../ui";
import { storedLocale } from "../i18n/strings";

const isZh = (): boolean => storedLocale() === "zh";
const L = (zh: string, en: string): string => (isZh() ? zh : en);

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
        {L("无权限 — ", "NO ACCESS — ")}{props.action}
      </div>
      <Panel title={L("权限说明", "Permission explanation")}>
        <div className="kv">
          <span className="kv-label">{L("租户", "Tenant")}</span>
          <span className="kv-value">
            {L(
              "当前凭据所属租户决定可见的数据范围；服务端从不信任客户端传来的 tenant id —— 跨租户请求一律 401/403。",
              "The tenant your credential belongs to decides which data is visible; the server never trusts a client-supplied tenant id — cross-tenant requests always answer 401/403."
            )}
          </span>
        </div>
        <div className="kv">
          <span className="kv-label">{L("角色", "Role")}</span>
          <span className="kv-value">
            {L(
              "管理页面仅对 admin / operator 开放；viewer 保留只读能力 (jobs:read 等)。角色变更由管理员操作，前端不能自行提升。",
              "Management pages are admin/operator only; viewer keeps read-only abilities (jobs:read etc.). Role changes are performed by an admin — the frontend cannot promote itself."
            )}
          </span>
        </div>
        <div className="kv">
          <span className="kv-label">{L("来源", "Source")}</span>
          <span className="kv-value">
            {L(
              "权限来自服务端 /auth/me 解析的当前身份 (sp_* 令牌 / OIDC id_token)；本页仅做可见性门控，服务端 RBAC fail-closed 才是权威。",
              "Permissions come from the server-side /auth/me resolution of your identity (an sp_* token or an OIDC id_token); this page only gates visibility — the server-side fail-closed RBAC is the authority."
            )}
          </span>
        </div>
        <div className="kv">
          <span className="kv-label">{L("失效", "Expiry")}</span>
          <span className="kv-value">
            {L(
              "令牌过期或被吊销后，所有管理接口立即返回 401/403；重新登录或切换为有效令牌后生效。",
              "Once a token expires or is revoked, every admin endpoint immediately answers 401/403; sign in again or switch to a valid token."
            )}
          </span>
        </div>
        <div className="permission-hint" data-testid="contact-admin-hint">
          {L(
            "需要访问？请联系租户管理员 —— 请管理员在「身份」页将你的角色提升为 admin/operator，或为你签发新的 API 令牌。",
            "Need access? Contact your tenant admin — have them promote your role to admin/operator on the Identity page, or mint a new API token for you."
          )}
        </div>
      </Panel>
    </div>
  );
}
