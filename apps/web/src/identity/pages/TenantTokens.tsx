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
import { storedLocale } from "../../i18n/strings";

const isZh = (): boolean => storedLocale() === "zh";
const L = (zh: string, en: string): string => (isZh() ? zh : en);


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
          <h1>{L("Token 管理", "Tokens")}</h1>
          <div className="page-sub">{L("IDENTITY — sp_* 本地凭证，show-once（RBAC: admin/operator）", "Identity — sp_* local credentials, show-once (RBAC: admin/operator)")}</div>
        </div>
        <PermissionDenied action={L("Token 管理仅对 admin/operator 开放 (RBAC fail-closed)", "Token management is admin/operator only (RBAC fail-closed)")} />
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
    { key: "name", header: L("名称", "Name"), sortable: true },
    { key: "user_email", header: L("用户", "User"), sortable: true },
    {
      key: "scopes",
      header: L("权限范围", "Scopes"),
      render: (t) => (
        <span className="mono" title={t.scopes || undefined}>
          {t.scopes || "—"}
        </span>
      ),
    },
    {
      key: "expires_at",
      header: L("过期", "Expires"),
      sortable: true,
      sortValue: (t) => t.expires_at ?? 0,
      render: (t) => tsCell(t.expires_at),
    },
    {
      key: "last_used_at",
      header: L("最近使用", "Last used"),
      sortable: true,
      sortValue: (t) => t.last_used_at ?? 0,
      render: (t) => tsCell(t.last_used_at),
    },
    {
      key: "actions",
      header: L("操作", "Actions"),
      render: (t) => (
        <Button variant="ghost" size="sm" onClick={() => revoke(t)}>
          {L("吊销", "Revoke")}
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
      <Panel title={L("签发新 Token", "Mint a token")}>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            type="text"
            aria-label={L("Token 名称", "Token name")}
            value={name}
            placeholder={L("名称（如 ci）", "Name (e.g. ci)")}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            type="text"
            aria-label={L("权限范围（逗号分隔）", "Scopes (comma-separated)")}
            value={scopes}
            placeholder={L("scopes（如 jobs:read，留空 = 角色矩阵决定）", "scopes (e.g. jobs:read, empty = role matrix decides)")}
            onChange={(e) => setScopes(e.target.value)}
          />
          <Button variant="primary" onClick={mint}>
            {L("签发", "Mint")}
          </Button>
        </div>
      </Panel>
      {cleartext ? (
        <Panel title={L("仅展示一次（show-once）— 复制并妥善保存", "Show-once — copy and keep it safe")}>
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
              {L("保存到租户切换器", "Save to tenant switcher")}
            </Button>
            <Button variant="ghost" onClick={() => setCleartext(null)}>
              {L("我已复制", "Done")}
            </Button>
          </div>
          <div className="muted" style={{ marginTop: 8 }}>
            {L("服务端只存 HMAC-SHA256(token) 与 bcrypt(secret)；此明文永不落库、无法找回。", "The server stores only HMAC-SHA256(token) + bcrypt(secret); the cleartext is never written to the DB and cannot be recovered.")}
          </div>
        </Panel>
      ) : null}
      <ErrorBox error={error} />
      <Panel title={L("已签发的 Token", "Issued tokens")}>
        {loadFailed(error) ? (
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span>{L("Token 列表暂时无法加载（请求失败）——这不代表没有 Token。", "The token list cannot be loaded right now (request failed) — this does NOT mean there are no tokens.")}</span>
            <Button variant="secondary" size="sm" onClick={reload}>{L("重试", "Retry")}</Button>
          </div>
        ) : loading ? (
          <div className="spinner">{L("加载中…", "Loading…")}</div>
        ) : (
          <Table<TokenRow>
            columns={columns}
            rows={tokens}
            rowKey={(t) => t.id}
            emptyTitle={L("暂无 Token", "No tokens yet")}
            emptyDescription={L("当前租户还没有签发过 Token。", "This tenant has not minted any tokens yet.")}
          />
        )}
      </Panel>
    </div>
  );
}
