import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  AuthConfig,
  apiBase,
  apiGet,
  getApiKey,
  getAuthConfig,
  getAuthMe,
  getBearerToken,
  setApiKey,
  setBearerToken,
} from "../api";
import { Button, ErrorBox } from "../ui";
import "./onboarding.css";

type Mode = "key" | "token";

function connectionError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "凭据未通过验证。请检查是否复制完整，或向工作区管理员获取新的凭据。";
    if (error.status === 403) return "当前凭据没有工作区访问权限，请联系管理员。";
    if (error.status === 429) return "连接请求过于频繁，请稍后重试。";
    if (error.status >= 500) return "服务暂时无法完成连接。请确认后端已启动、服务端已配置登录凭据，然后重试。";
    return error.message;
  }
  return "无法连接到服务。请确认本地启动脚本已完成，或联系工作区管理员检查服务地址。";
}

export default function Login(props: { onConnected?: () => void }) {
  const [mode, setMode] = useState<Mode>("key");
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [configError, setConfigError] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [showCredential, setShowCredential] = useState(false);
  const pending = useRef(false);

  useEffect(() => {
    let alive = true;
    getAuthConfig()
      .then((result) => {
        if (!alive) return;
        setConfig(result);
        if (result.auth_mode === "tenant") setMode("token");
      })
      .catch(() => { if (alive) setConfigError(true); });
    return () => { alive = false; };
  }, []);

  async function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current) return;
    const credential = value.trim();
    if (!credential) {
      setError(mode === "key" ? "请先输入工作区 API Key。" : "请先输入管理员提供的访问令牌。");
      return;
    }
    pending.current = true;
    setConnecting(true);
    setError(null);
    const previousKey = getApiKey();
    const previousToken = getBearerToken();
    try {
      // A stale credential must not override the credential being verified.
      setApiKey(mode === "key" ? credential : "");
      setBearerToken(mode === "token" ? credential : "");
      if (mode === "token") {
        await getAuthMe();
      } else {
        await apiGet("/api/v1/dashboard");
      }
      props.onConnected?.();
      window.location.hash = "#/dashboard";
    } catch (cause) {
      setApiKey(previousKey);
      setBearerToken(previousToken);
      setError(connectionError(cause));
    } finally {
      pending.current = false;
      setConnecting(false);
    }
  }

  const tenantMode = config?.auth_mode === "tenant";
  const localHost = ["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname);

  return (
    <div className="login-wrap onboarding-login">
      <main className="welcome-layout">
        <section className="welcome-story" aria-labelledby="welcome-title">
          <a className="welcome-brand" href="#/guide"><span aria-hidden="true">S</span> SpecProof</a>
          <div className="welcome-eyebrow">从需求到证据，每次交付都有依据</div>
          <h1 id="welcome-title">代码改好了。<br /><span>需求，真的实现了吗？</span></h1>
          <p className="welcome-description">SpecProof 帮团队验收代码变更：把你写下的需求与改动前后的代码放在一起检查，给出通过、阻断或待确认的结果，并保留可追溯的证据。</p>
          <div className="welcome-flow" aria-label="验证流程">
            <div><span>01</span><strong>写清需求</strong><small>你希望代码做到什么</small></div>
            <i aria-hidden="true">→</i>
            <div><span>02</span><strong>对比变更</strong><small>检查改动前后的行为</small></div>
            <i aria-hidden="true">→</i>
            <div><span>03</span><strong>查看证据</strong><small>知道哪里通过、哪里有风险</small></div>
          </div>
          <div className="welcome-example">
            <div className="welcome-example-top"><span>一个典型场景</span><span className="welcome-example-tag">权限变更</span></div>
            <p>需求：“只有管理员可以修改用户邮箱。”</p>
            <div className="welcome-example-result"><span aria-hidden="true">!</span><div><strong>发现改动移除了权限检查</strong><small>查看失败条件、受影响代码和可重放证据，再决定是否合并。</small></div></div>
          </div>
          <a className="welcome-guide-link" href="#/guide">第一次使用？先看使用指南 <span aria-hidden="true">↗</span></a>
        </section>

        <section className="login-card welcome-connect" aria-labelledby="connect-title">
          <div className="welcome-eyebrow">你的工作区</div>
          <h2 id="connect-title">连接后，开始第一次验收</h2>
          <p className="welcome-card-description">使用管理员提供的凭据，访问团队的验证任务与交付证据。</p>
          <form onSubmit={(event) => { void connect(event); }}>
            {tenantMode ? (
              <div className="login-modes" aria-label="连接方式">
                <Button variant={mode === "token" ? "secondary" : "ghost"} aria-pressed={mode === "token"} disabled={connecting} onClick={() => { setMode("token"); setError(null); setValue(""); }}>访问令牌</Button>
                <Button variant={mode === "key" ? "secondary" : "ghost"} aria-pressed={mode === "key"} disabled={connecting} onClick={() => { setMode("key"); setError(null); setValue(""); }}>API Key</Button>
              </div>
            ) : null}
            <label className="field" htmlFor="credential">{mode === "token" ? "工作区访问令牌" : "工作区 API Key"}</label>
            <div className="credential-control">
              <input id="credential" type={showCredential ? "text" : "password"} value={value} placeholder={mode === "token" ? "粘贴 sp_ 开头的访问令牌" : "粘贴管理员提供的 API Key"} autoComplete="off" spellCheck={false} disabled={connecting} aria-describedby="credential-hint" onChange={(event) => setValue(event.target.value)} />
              <button type="button" onClick={() => setShowCredential(!showCredential)} aria-label={showCredential ? "隐藏凭据" : "显示凭据"} aria-pressed={showCredential}>{showCredential ? "隐藏" : "显示"}</button>
            </div>
            <p className="welcome-input-hint" id="credential-hint">{mode === "key" ? "这里填写 SpecProof 工作区的登录密钥；模型服务商的 API Key 在进入工作区后单独配置。" : "这里填写工作区管理员签发的访问令牌。"}凭据仅保存在当前浏览器会话中。</p>
            <ErrorBox error={error} />
            <Button type="submit" variant="primary" size="lg" fullWidth loading={connecting}>{connecting ? "正在验证连接…" : "连接工作区"}</Button>
          </form>
          {config?.oidc.enabled ? (
            <div className="welcome-sso"><span>或使用组织账号</span><Button fullWidth disabled={connecting} onClick={() => { window.location.href = apiBase() + "/auth/oidc/login?return_to=" + encodeURIComponent("#/dashboard"); }}>企业单点登录</Button></div>
          ) : null}
          {configError ? <p className="welcome-connection-note" role="status">暂时未获取到工作区配置。仍可尝试使用 API Key 连接；连接失败时请检查服务是否已启动。</p> : null}
          <details className="welcome-help">
            <summary>还没有凭据，如何开始？</summary>
            <p>团队用户：请向工作区管理员索取 API Key、访问令牌或单点登录入口。</p>
            {localHost ? <><p>本机体验：在项目根目录运行下方命令，等待服务启动后，使用终端输出的登录密钥。</p><code>pwsh scripts/start_local.ps1</code><p>初次运行需要 Python 3.12、Node.js 18+ 和 Docker Desktop。</p></> : <p>自己部署：按项目的本地体验指南启动服务，在后端配置工作区凭据。</p>}
          </details>
          <div className="welcome-connect-foot"><span aria-hidden="true">◇</span> 先看证据，再做交付决定</div>
        </section>
      </main>
    </div>
  );
}
