import { Fragment, useEffect, useRef, useState, type FormEvent } from "react";
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
import { useI18n } from "../i18n";
import { LOGIN_BY_LOCALE, type LoginCopy } from "./login.copy";
import "./onboarding.css";

type Mode = "key" | "token";

function connectionError(error: unknown, c: LoginCopy): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return c.error401;
    if (error.status === 403) return c.error403;
    if (error.status === 429) return c.error429;
    if (error.status >= 500) {
      // A 5xx here means the server *answered*. Measured live against a running
      // API: the only 503 the audit endpoint gives is "auth not enabled", so
      // telling that user to check whether the backend is up sends them to the
      // one thing already proven.
      if (error.code === "PROVIDER_UNAVAILABLE") {
        return c.error5xxProvider(error.detail);
      }
      return c.error5xxAnswered(error.status, error.detail);
    }
    return error.message;
  }
  return c.errorNetwork;
}

export default function Login(props: { onConnected?: () => void }) {
  const { locale } = useI18n();
  const c = LOGIN_BY_LOCALE[locale];
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
      setError(mode === "key" ? c.emptyCredentialKey : c.emptyCredentialToken);
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
      setError(connectionError(cause, c));
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
          <a className="welcome-brand" href="#/guide"><span aria-hidden="true">S</span>{c.brandSuffix}</a>
          <div className="welcome-eyebrow">{c.eyebrow}</div>
          <h1 id="welcome-title">{c.welcomeH1[0]}<br /><span>{c.welcomeH1[1]}</span></h1>
          <p className="welcome-description">{c.welcomeDescription}</p>
          <div className="welcome-flow" aria-label={c.flowAria}>
            {c.flow.map((item, index) => (
              <Fragment key={item.step}>
                <div>
                  <span>{item.step}</span><strong>{item.title}</strong><small>{item.text}</small>
                </div>
                {index < c.flow.length - 1 ? <i aria-hidden="true">→</i> : null}
              </Fragment>
            ))}
          </div>
          <div className="welcome-example">
            <div className="welcome-example-top"><span>{c.exampleLabel}</span><span className="welcome-example-tag">{c.exampleTag}</span></div>
            <p>{c.exampleText}</p>
            <div className="welcome-example-result"><span aria-hidden="true">!</span><div><strong>{c.exampleFindingStrong}</strong><small>{c.exampleFindingSmall}</small></div></div>
          </div>
          <a className="welcome-guide-link" href="#/guide">{c.guideLink}<span aria-hidden="true">→</span></a>
        </section>

        <section className="login-card welcome-connect" aria-labelledby="connect-title">
          <div className="welcome-eyebrow">{c.cardEyebrow}</div>
          <h2 id="connect-title">{c.cardTitle}</h2>
          <p className="welcome-card-description">{c.cardDescription}</p>
          <form onSubmit={(event) => { void connect(event); }}>
            {tenantMode ? (
              <div className="login-modes" aria-label={c.modesAria}>
                <Button variant={mode === "token" ? "secondary" : "ghost"} aria-pressed={mode === "token"} disabled={connecting} onClick={() => { setMode("token"); setError(null); setValue(""); }}>{c.modeToken}</Button>
                <Button variant={mode === "key" ? "secondary" : "ghost"} aria-pressed={mode === "key"} disabled={connecting} onClick={() => { setMode("key"); setError(null); setValue(""); }}>{c.modeKey}</Button>
              </div>
            ) : null}
            <label className="field" htmlFor="credential">{mode === "token" ? c.labelToken : c.labelKey}</label>
            <div className="credential-control">
              <input id="credential" type={showCredential ? "text" : "password"} value={value} placeholder={mode === "token" ? c.placeholderToken : c.placeholderKey} autoComplete="off" spellCheck={false} disabled={connecting} aria-describedby="credential-hint" onChange={(event) => setValue(event.target.value)} />
              <button type="button" onClick={() => setShowCredential(!showCredential)} aria-label={showCredential ? c.revealAriaHide : c.revealAriaShow} aria-pressed={showCredential}>{showCredential ? c.hide : c.reveal}</button>
            </div>
            <p className="welcome-input-hint" id="credential-hint">{mode === "key" ? c.hintKey : c.hintToken}</p>
            <ErrorBox error={error} />
            <Button type="submit" variant="primary" size="lg" fullWidth loading={connecting}>{connecting ? c.connecting : c.connect}</Button>
          </form>
          {config?.oidc.enabled ? (
            <div className="welcome-sso"><span>{c.oidcNote}</span><Button fullWidth disabled={connecting} onClick={() => { window.location.href = apiBase() + "/auth/oidc/login?return_to=" + encodeURIComponent("#/dashboard"); }}>{c.oidcButton}</Button></div>
          ) : null}
          {configError ? <p className="welcome-connection-note" role="status">{c.configError}</p> : null}
          <details className="welcome-help">
            <summary>{c.noCredential}</summary>
            <p>{c.noCredentialBody}</p>
            {localHost ? <><p>{c.localBody}</p><code>{c.localCommand}</code><p>{c.localBodyWindows}</p></> : <p>{c.nonLocalBody}</p>}
          </details>
          <div className="welcome-connect-foot"><span aria-hidden="true">→</span> {c.foot}</div>
        </section>
      </main>
    </div>
  );
}
