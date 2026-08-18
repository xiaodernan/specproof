import { useEffect, useState } from "react";
import {
  TokenRow,
  createToken,
  listTokens,
  revokeToken,
  saveToken,
} from "../../api";
import { Empty, ErrorBox, Panel } from "../../components";

// Token management (RBAC: admin/operator). Minted tokens are show-once: the
// cleartext appears exactly once and is then discarded from component state;
// saving hands it to the tenant switcher's local store (localStorage).
export default function TenantTokens() {
  const [tokens, setTokens] = useState<TokenRow[]>([]);
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState("");
  const [error, setError] = useState<Error | string | null>(null);
  const [loading, setLoading] = useState(true);
  const [cleartext, setCleartext] = useState<string | null>(null);
  const [cleartextName, setCleartextName] = useState("");

  function reload() {
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

  useEffect(reload, []);

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
            value={name}
            placeholder="名称 (如 ci)"
            onChange={(e) => setName(e.target.value)}
          />
          <input
            type="text"
            value={scopes}
            placeholder="scopes (如 jobs:read, 留空=角色矩阵决定)"
            onChange={(e) => setScopes(e.target.value)}
          />
          <button className="btn" onClick={mint}>
            签发 Mint
          </button>
        </div>
      </Panel>
      {cleartext ? (
        <Panel title="仅展示一次 SHOW-ONCE — 复制并妥善保存">
          <div className="cleartext" data-testid="cleartext">
            {cleartext}
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <button
              className="btn"
              onClick={() => {
                saveToken(cleartextName, cleartext);
                setCleartext(null);
              }}
            >
              保存到租户切换器 Save
            </button>
            <button className="btn btn-ghost" onClick={() => setCleartext(null)}>
              我已复制 Done
            </button>
          </div>
          <div className="muted" style={{ marginTop: 8 }}>
            服务端只存 HMAC-SHA256(token) 与 bcrypt(secret); 此明文永不落库、无法找回。
          </div>
        </Panel>
      ) : null}
      <ErrorBox error={error} />
      <Panel title="已签发 Tokens">
        {loading ? (
          <div className="spinner">加载中 LOADING…</div>
        ) : tokens.length === 0 ? (
          <Empty text="暂无 Token No tokens" />
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>名称 Name</th>
                <th>用户 User</th>
                <th>Scopes</th>
                <th>过期 Expires</th>
                <th>最近使用 Last used</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {tokens.map((t) => (
                <tr key={t.id}>
                  <td>{t.name}</td>
                  <td>{t.user_email}</td>
                  <td className="mono">{t.scopes || "—"}</td>
                  <td>{t.expires_at ? new Date(t.expires_at * 1000).toISOString() : "—"}</td>
                  <td>{t.last_used_at ? new Date(t.last_used_at * 1000).toISOString() : "—"}</td>
                  <td>
                    <button className="btn btn-ghost" onClick={() => revoke(t)}>
                      吊销 Revoke
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
