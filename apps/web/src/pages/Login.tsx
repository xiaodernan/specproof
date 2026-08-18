import { useEffect, useState } from "react";
import {
  AuthConfig,
  apiBase,
  getAuthConfig,
  getAuthMe,
  setApiKey,
  setBearerToken,
} from "../api";
import { ErrorBox } from "../components";

// Login supports three credential modes, mirroring api/routes/admin.py:
//   1. legacy X-API-Key (single-tenant deployments);
//   2. local scoped token sp_<id>_<secret> (multi-tenant);
//   3. OIDC redirect (/auth/oidc/login -> IdP -> /auth/oidc/callback ->
//      #oidc_token=... consumed by App.tsx).
// The auth config endpoint decides which modes are offered.

type Mode = "key" | "token";

export default function Login(props: { onConnected?: () => void }) {
  const [mode, setMode] = useState<Mode>("key");
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [config, setConfig] = useState<AuthConfig | null>(null);

  useEffect(() => {
    getAuthConfig()
      .then(setConfig)
      .catch(() => setConfig({ auth_mode: "legacy", oidc: { enabled: false, issuer: "", client_id: "" } }));
  }, []);

  function connect() {
    const v = value.trim();
    if (!v) {
      setError(mode === "key" ? "请输入 API Key" : "请输入本地 Token (sp_...)");
      return;
    }
    if (mode === "key") {
      setApiKey(v);
      if (props.onConnected) props.onConnected();
      window.location.hash = "#/dashboard";
      return;
    }
    // Local token: store it and prove it against /auth/me before entering.
    setBearerToken(v);
    getAuthMe()
      .then((me) => {
        setError(null);
        setBearerToken(v);
        window.sessionStorage.setItem("specproof_principal_tenant", me.principal.tenant_id);
        if (props.onConnected) props.onConnected();
        window.location.hash = "#/dashboard";
      })
      .catch((e: Error) => {
        setBearerToken("");
        setError(e.message || "本地 Token 校验失败 (401)");
      });
  }

  function startOidc() {
    const returnTo = window.location.hash || "#/dashboard";
    window.location.href =
      apiBase() + "/auth/oidc/login?return_to=" + encodeURIComponent(returnTo);
  }

  const tenantMode = config !== null && config.auth_mode === "tenant";
  const oidcEnabled = config !== null && config.oidc.enabled;

  return (
    <div className="login-wrap">
      <div className="login-card">
        <h1>SpecProof Control Room</h1>
        <div className="login-sub">AI CHANGE ACCEPTANCE FIREWALL — 鉴权接入</div>
        {tenantMode ? (
          <div className="login-modes">
            <button
              className={"btn btn-ghost" + (mode === "token" ? " btn-active" : "")}
              onClick={() => {
                setMode("token");
                setError(null);
              }}
            >
              本地 Token Local
            </button>
            <button
              className={"btn btn-ghost" + (mode === "key" ? " btn-active" : "")}
              onClick={() => {
                setMode("key");
                setError(null);
              }}
            >
              API Key
            </button>
          </div>
        ) : null}
        <label className="field" htmlFor="credential">
          {mode === "token" ? "本地 Token (sp_...)" : "API Key (SPECPROOF_API_KEY)"}
        </label>
        <input
          id="credential"
          type="password"
          value={value}
          placeholder={mode === "token" ? "粘贴 show-once Token" : "输入 X-API-Key"}
          autoFocus
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") connect();
          }}
        />
        <ErrorBox error={error} />
        <button className="btn" onClick={connect}>
          {mode === "token" ? "验证并进入 Verify" : "连接 Connect"}
        </button>
        {oidcEnabled ? (
          <>
            <div className="login-or">或 OR</div>
            <button className="btn btn-ghost" onClick={startOidc}>
              OIDC 单点登录 ({config ? config.oidc.issuer : ""})
            </button>
          </>
        ) : null}
        <div className="login-hint">
          {mode === "token"
            ? "Token 仅保存在 sessionStorage, 以 Authorization: Bearer 头发送; 失效 (401) 时所有数据接口拒绝访问 (fail-closed)。"
            : "密钥仅保存在 sessionStorage, 随所有 API 请求以 X-API-Key 头发送; 鉴权失败 (401) 时所有数据接口拒绝访问 (fail-closed)。"}
        </div>
      </div>
    </div>
  );
}
