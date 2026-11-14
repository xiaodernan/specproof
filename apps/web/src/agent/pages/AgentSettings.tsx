import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, apiGet, apiPost } from "../../api";
import { Button, ErrorBox, Input, Panel, Spinner } from "../../ui";
import { useI18n } from "../../i18n";
import { AGENT_SETTINGS_BY_LOCALE } from "./agentSettings.copy";
import "./model-settings.css";

interface ModelConfig {
  base_url: string;
  model: string;
  reasoning_effort: string;
  protocol: "responses" | "chat_completions";
  configured: boolean;
  key_hint: string;
  source: string;
}

interface ConnectionResult {
  ok: boolean;
  message: string;
  model: string;
  protocol: string;
  reasoning_effort: string;
  latency_ms: number;
  usage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number };
}

const DEFAULTS: ModelConfig = {
  base_url: "", model: "", reasoning_effort: "max", protocol: "responses",
  configured: false, key_hint: "", source: "unconfigured",
};

export default function AgentSettings() {
  const { locale } = useI18n();
  const c = AGENT_SETTINGS_BY_LOCALE[locale];
  const [config, setConfig] = useState<ModelConfig>(DEFAULTS);
  const [apiKey, setApiKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [error, setError] = useState<Error | string | null>(null);
  const [busy, setBusy] = useState<"save" | "test" | null>(null);
  const [saved, setSaved] = useState("");
  const [result, setResult] = useState<ConnectionResult | null>(null);
  const [reload, setReload] = useState(0);
  const [dirty, setDirty] = useState(false);
  const pending = useRef(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setLoadError(null);
    apiGet<ModelConfig>("/api/v1/model/config")
      .then((data) => { if (alive) { setConfig(data); setDirty(false); } })
      .catch((cause) => { if (alive) setLoadError(cause as Error); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [reload]);

  const managed = config.source === "environment";
  const patch = (values: Partial<ModelConfig>) => {
    setConfig((previous) => ({ ...previous, ...values }));
    setDirty(true);
    setSaved("");
    setResult(null);
  };

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current || managed) return;
    if (!config.base_url.trim() || !config.model.trim() || (!config.configured && !apiKey.trim())) {
      setError(c.saveError);
      return;
    }
    pending.current = true;
    setBusy("save"); setError(null); setSaved(""); setResult(null);
    try {
      const updated = await apiPost<ModelConfig>("/api/v1/model/config", {
        base_url: config.base_url.trim(), api_key: apiKey.trim(), model: config.model.trim(),
        reasoning_effort: config.reasoning_effort, protocol: config.protocol,
      });
      setConfig(updated); setApiKey(""); setDirty(false);
      setSaved(c.saved);
    } catch (cause) {
      setError(cause as Error);
    } finally {
      pending.current = false; setBusy(null);
    }
  }

  async function testConnection() {
    if (pending.current) return;
    pending.current = true;
    setBusy("test"); setError(null); setResult(null);
    try {
      setResult(await apiPost<ConnectionResult>("/api/v1/model/test", {}));
    } catch (cause) {
      setError(cause as Error);
    } finally {
      pending.current = false; setBusy(null);
    }
  }

  return (
    <div className="model-settings-page">
      <div className="page-head"><div className="eyebrow">{c.eyebrow}</div><h1>{c.title}</h1><p className="model-intro">{c.intro}</p></div>
      <div className="model-credential-note"><strong>{c.credentialStrong}</strong><p>{c.credentialBody}</p></div>
      {loading ? <Spinner /> : loadError ? (
        loadError instanceof ApiError && loadError.status === 403
          ? <Panel title={c.forbiddenTitle}><p className="model-intro">{c.forbiddenBody}</p><a className="model-return" href="#/agent">{c.forbiddenLink}</a></Panel>
          : <Panel title={c.loadFailedTitle}><ErrorBox error={loadError} /><Button onClick={() => setReload((value) => value + 1)}>{c.retry}</Button></Panel>
      ) : (
        <div className="model-settings-layout">
          <Panel title={c.configTitle} right={<span className={"model-status " + (config.configured ? "model-status-set" : "")}>{dirty ? c.dirtyStatus : result?.ok ? c.passStatus : result ? c.failStatus : config.configured ? c.configuredStatus : c.missingStatus}</span>}>
            {managed ? <div className="model-managed">{c.managedText}</div> : null}
            <form onSubmit={(event) => { void save(event); }}>
              <fieldset disabled={managed || busy !== null} className="model-fields">
                <Input label={c.urlLabel} type="url" placeholder={c.urlPlaceholder} value={config.base_url} onChange={(event) => patch({ base_url: event.target.value })} hint={c.urlHint} />
                <Input label={c.modelLabel} type="text" placeholder={c.modelPlaceholder} value={config.model} onChange={(event) => patch({ model: event.target.value })} hint={c.modelHint} />
                <Input label={c.apiKeyLabel} type="password" autoComplete="off" spellCheck={false} value={apiKey} onChange={(event) => { setApiKey(event.target.value); setDirty(true); setSaved(""); setResult(null); }} placeholder={config.configured ? c.apiKeyPlaceholderConfigured : c.apiKeyPlaceholderMissing} hint={config.configured ? c.apiKeyHintConfigured : c.apiKeyHintMissing} />
                <div className="model-options">
                  <div className="ui-field"><label className="ui-label" htmlFor="model-protocol">{c.protocolLabel}</label><select id="model-protocol" value={config.protocol} onChange={(event) => patch({ protocol: event.target.value as ModelConfig["protocol"] })}><option value="responses">{c.protocolResponses}</option><option value="chat_completions">{c.protocolChat}</option></select><span className="ui-hint">{c.protocolHint}</span></div>
                  <div className="ui-field"><label className="ui-label" htmlFor="model-reasoning">{c.reasoningLabel}</label><select id="model-reasoning" value={config.reasoning_effort} onChange={(event) => patch({ reasoning_effort: event.target.value })}><option value="">{c.reasoningDefault}</option><option value="low">{c.reasoningLow}</option><option value="medium">{c.reasoningMedium}</option><option value="high">{c.reasoningHigh}</option><option value="xhigh">{c.reasoningXhigh}</option><option value="max">{c.reasoningMax}</option></select><span className="ui-hint">{c.reasoningHint}</span></div>
                </div>
              </fieldset>
              <ErrorBox error={error} />
              {saved ? <div className="model-save-message" role="status">{saved}</div> : null}
              <div className="model-buttons">{!managed ? <Button variant="primary" type="submit" disabled={busy !== null} loading={busy === "save"}>{c.save}</Button> : null}<Button disabled={!config.configured || dirty || busy !== null} loading={busy === "test"} onClick={() => { void testConnection(); }}>{busy === "test" ? c.testing : c.test}</Button></div>
              <p className="model-action-hint">{dirty ? c.dirtyHint : c.testHint}</p>
            </form>
          </Panel>
          <aside className="model-help-panel"><span className="eyebrow">{c.helpKicker}</span><h2>{c.helpTitle}</h2><p>{c.helpIntro}</p><ol><li>{c.helpStep1}</li><li>{c.helpStep2}</li><li>{c.helpStep3}</li></ol><a href="#/guide">{c.helpLink}</a></aside>
        </div>
      )}
      {result ? <section className={"model-test-result " + (result.ok ? "model-test-success" : "model-test-failed")} role="status"><div><h2>{result.ok ? c.resultPassTitle : c.resultFailTitle}</h2><p>{result.message}</p><small>{c.resultMeta(result.model, result.protocol === "responses" ? c.protocolResponses : c.protocolChat, result.latency_ms / 1000)}</small></div>{result.ok ? <a className="ui-btn ui-btn-primary ui-btn-md" href="#/agent/new">{c.resultSuccessCta}</a> : <span>{c.resultFailHint}</span>}</section> : null}
    </div>
  );
}
