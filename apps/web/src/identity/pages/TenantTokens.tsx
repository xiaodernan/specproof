import { useEffect, useState } from "react";
import {
  TokenRow,
  createToken,
  listTokens,
  revokeToken,
  saveToken,
} from "../../api";
import { Button, ErrorBox, Panel, Table, fmtTime, type Column } from "../../ui";
import { loadFailed } from "../../ui/errorHints";
import { PermissionDenied } from "../PermissionDenied";
import { useIdentityAccess } from "../useIdentityAccess";

// Renders a unix-seconds timestamp as a friendly local date, with the exact
// ISO instant kept in the title tooltip so the raw value stays inspectable.
function tsCell(ts: number | null | undefined): JSX.Element {
  if (!ts) return <>—</>;
  const iso = new Date(ts * 1000).toISOString();
  return (
    <span className="mono" title={iso}>
      {fmtTime(iso)}
    </span>
  );
}

// Token management (RBAC: admin/operator). Minted tokens are show-once: the
// cleartext appears exactly once and is then discarded from component state;
// saving hands it to the tenant switcher's local store (localStorage).
export default function TenantTokens() {
  const { canManage } = useIdentityAccess();
  const [tokens, setTokens] = useState<TokenRow[]>([]);
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState("");
  const [error, setError] = useState<Error | string | null>(null);
  const [loading, setLoading] = useState(true);
  const [cleartext, setCleartext] = useState<string | null>(null);
  const [cleartextName, setCleartextName] = useState("");

  function reload() {
    setError(null);
    setLoading(true);
    listTokens()
      .then((data) => {
        setTokens(data.tokens);
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
          <h1>Token 管理 Tokens</h1>
          <div className="page-sub">IDENTITY — sp_* 本地凭证, show-once (RBAC: admin/operator)</div>
        </div>
        <PermissionDenied action="Token 管理仅对 admin/operator 开放 (RBAC fail-closed)" />
      </div>
    );
  }

  function mint() {
    setError(null);
    createToken(name.trim() || "token", scopes.trim())
      .then((res) => {
        setName("");
        setScopes("");
        setCleartext(res.cleartext);
        setCleartextName(res.token.name);
        reload();
      })
      .catch((e: Error) => setError(e));
  }

  function revoke(token: TokenRow) {
    setError(null);
    revokeToken(token.id)
      .then(reload)
      .catch((e: Error) => setError(e));
  }

  const columns: Column<TokenRow>[] = [
    { key: "name", header: "名称 Name", sortable: true },
    { key: "user_email", header: "用户 User", sortable: true },
    {
      key: "scopes",
      header: "权限范围 Scopes",
      render: (t) => (
        <span className="mono" title={t.scopes || undefined}>
          {t.scopes || "—"}
        </span>
      ),
    },
    {
      key: "expires_at",
      header: "过期 Expires",
      sortable: true,
      sortValue: (t) => t.expires_at ?? 0,
      render: (t) => tsCell(t.expires_at),
    },
    {
      key: "last_used_at",
      header: "最近使用 Last used",
      sortable: true,
      sortValue: (t) => t.last_used_at ?? 0,
      render: (t) => tsCell(t.last_used_at),
    },
    {
      key: "actions",
      header: "操作",
      render: (t) => (
        <Button variant="ghost" size="sm" onClick={() => revoke(t)}>
          吊销 Revoke
        </Button>
      ),
    },
  ];

  return (
    <div>
      <div className="page-head">
        <h1>Token 管理 Tokens</h1>
        <div className="page-sub">IDENTITY — sp_* 本地凭证, show-once (RBAC: admin/operator)</div>
      </div>
      <Panel title="签发新 Token">
        <div style={{ display: "flex", gap: 8 }}>
          <input
            type="text"
            aria-label="Token 名称 Name"
            value={name}
            placeholder="名称 (如 ci)"
            onChange={(e) => setName(e.target.value)}
          />
          <input
            type="text"
            aria-label="权限范围 Scopes (逗号分隔)"
            value={scopes}
            placeholder="scopes (如 jobs:read, 留空=角色矩阵决定)"
            onChange={(e) => setScopes(e.target.value)}
          />
          <Button variant="primary" onClick={mint}>
            签发 Mint
          </Button>
        </div>
      </Panel>
      {cleartext ? (
        <Panel title="仅展示一次 SHOW-ONCE — 复制并妥善保存">
          <div className="cleartext" data-testid="cleartext">
            {cleartext}
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <Button
              variant="secondary"
              onClick={() => {
                saveToken(cleartextName, cleartext);
                setCleartext(null);
              }}
            >
              保存到租户切换器 Save
            </Button>
            <Button variant="ghost" onClick={() => setCleartext(null)}>
              我已复制 Done
            </Button>
          </div>
          <div className="muted" style={{ marginTop: 8 }}>
            服务端只存 HMAC-SHA256(token) 与 bcrypt(secret); 此明文永不落库、无法找回。
          </div>
        </Panel>
      ) : null}
      <ErrorBox error={error} />
      <Panel title="已签发 Tokens">
        {loadFailed(error) ? (
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span>Token 列表暂时无法加载（请求失败）— 这不代表没有 Token。</span>
            <Button variant="secondary" size="sm" onClick={reload}>重试 Retry</Button>
          </div>
        ) : loading ? (
          <div className="spinner">加载中 LOADING…</div>
        ) : (
          <Table<TokenRow>
            columns={columns}
            rows={tokens}
            rowKey={(t) => t.id}
            emptyTitle="暂无 Token No tokens"
            emptyDescription="当前租户还没有签发过 Token。"
          />
        )}
      </Panel>
    </div>
  );
}
