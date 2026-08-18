import { useState } from "react";
import { setApiKey } from "../api";
import { ErrorBox } from "../components";

export default function Login(props: { onConnected?: () => void }) {
  const [key, setKey] = useState("");
  const [error, setError] = useState<string | null>(null);

  function connect() {
    const k = key.trim();
    if (!k) {
      setError("请输入 API Key");
      return;
    }
    setApiKey(k);
    if (props.onConnected) props.onConnected();
    window.location.hash = "#/dashboard";
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <h1>SpecProof Control Room</h1>
        <div className="login-sub">AI CHANGE ACCEPTANCE FIREWALL — 鉴权接入</div>
        <label className="field" htmlFor="apikey">
          API Key (SPECPROOF_API_KEY)
        </label>
        <input
          id="apikey"
          type="password"
          value={key}
          placeholder="输入 X-API-Key"
          autoFocus
          onChange={(e) => setKey(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") connect();
          }}
        />
        <ErrorBox error={error} />
        <button className="btn" onClick={connect}>
          连接 Connect
        </button>
        <div className="login-hint">
          密钥仅保存在 sessionStorage, 随所有 API 请求以 X-API-Key 头发送;
          鉴权失败 (401) 时所有数据接口拒绝访问 (fail-closed)。
        </div>
      </div>
    </div>
  );
}
