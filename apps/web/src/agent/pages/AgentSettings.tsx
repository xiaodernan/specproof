import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, apiGet, apiPost } from "../../api";
import { Button, ErrorBox, Input, Panel, Spinner } from "../../ui";
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
  configured: false, key_hint: "未设置", source: "unconfigured",
};

export default function AgentSettings() {
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
      setError("请填写模型服务地址、模型名称和模型服务商提供的 API Key。");
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
      setSaved("模型配置已保存。点击测试连接，确认服务能够实际返回内容。");
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
      <div className="page-head"><div className="eyebrow">AI CONNECTION</div><h1>模型连接</h1><p className="model-intro">接入你的 AI 模型服务，为开发助手提供实际推理能力。先保存配置，再验证一次真实连接。</p></div>
      <div className="model-credential-note"><strong>这是模型服务商的 API Key</strong><p>工作区登录密钥用于进入 SpecProof；这里的密钥用于服务端调用 AI。模型密钥保存在部署服务器，保存后不会返回浏览器。</p></div>
      {loading ? <Spinner /> : loadError ? (
        loadError instanceof ApiError && loadError.status === 403
          ? <Panel title="由部署管理员管理"><p className="model-intro">模型连接是整个部署共享的配置。请联系部署管理员设置模型服务；团队访问令牌不能修改共享模型配置。</p><a className="model-return" href="#/agent">返回 AI 开发 →</a></Panel>
          : <Panel title="暂时无法加载模型配置"><ErrorBox error={loadError} /><Button onClick={() => setReload((value) => value + 1)}>重新加载</Button></Panel>
      ) : (
        <div className="model-settings-layout">
          <Panel title="模型服务配置" right={<span className={"model-status " + (config.configured ? "model-status-set" : "")}>{dirty ? "有未保存更改" : result?.ok ? "连接已验证" : result ? "连接测试失败" : config.configured ? "已配置 · 待测试" : "尚未配置"}</span>}>
            {managed ? <div className="model-managed">当前配置由部署环境变量管理。如需修改，请联系部署管理员更新配置并重启服务。</div> : null}
            <form onSubmit={(event) => { void save(event); }}>
              <fieldset disabled={managed || busy !== null} className="model-fields">
                <Input label="模型服务地址" type="url" placeholder="https://your-model-service.example/v1" value={config.base_url} onChange={(event) => patch({ base_url: event.target.value })} hint="使用服务商提供的接口地址。系统会统一处理 /v1 或完整接口路径。" />
                <Input label="模型名称" type="text" placeholder="填写服务商实际支持的模型 ID" value={config.model} onChange={(event) => patch({ model: event.target.value })} hint="模型名称需要与服务商提供的 ID 完全一致。" />
                <Input label="模型 API Key" type="password" autoComplete="off" spellCheck={false} value={apiKey} onChange={(event) => { setApiKey(event.target.value); setDirty(true); setSaved(""); setResult(null); }} placeholder={config.configured ? "已保存；留空保留现有密钥" : "粘贴模型服务商提供的密钥"} hint={config.configured ? "更新其他选项时可以留空，现有密钥会保留。" : "仅用于模型调用，不会写入浏览器本地存储。"} />
                <div className="model-options">
                  <div className="ui-field"><label className="ui-label" htmlFor="model-protocol">接口协议</label><select id="model-protocol" value={config.protocol} onChange={(event) => patch({ protocol: event.target.value as ModelConfig["protocol"] })}><option value="responses">Responses API</option><option value="chat_completions">Chat Completions API</option></select><span className="ui-hint">按服务商支持的接口选择。</span></div>
                  <div className="ui-field"><label className="ui-label" htmlFor="model-reasoning">推理强度</label><select id="model-reasoning" value={config.reasoning_effort} onChange={(event) => patch({ reasoning_effort: event.target.value })}><option value="">模型默认</option><option value="low">Low · 较快</option><option value="medium">Medium · 均衡</option><option value="high">High · 深入</option><option value="xhigh">XHigh · 更深入</option><option value="max">Max · 最大</option></select><span className="ui-hint">高强度可能增加耗时与费用，须由模型支持。</span></div>
                </div>
              </fieldset>
              <ErrorBox error={error} />
              {saved ? <div className="model-save-message" role="status">{saved}</div> : null}
              <div className="model-buttons">{!managed ? <Button variant="primary" type="submit" disabled={busy !== null} loading={busy === "save"}>保存配置</Button> : null}<Button disabled={!config.configured || dirty || busy !== null} loading={busy === "test"} onClick={() => { void testConnection(); }}>{busy === "test" ? "正在请求模型…" : "测试连接"}</Button></div>
              <p className="model-action-hint">{dirty ? "配置已更改，请保存后再测试。" : "测试会发起一次小型模型请求，可能产生少量费用；最长等待约 50 秒。"}</p>
            </form>
          </Panel>
          <aside className="model-help-panel"><span className="eyebrow">连接检查</span><h2>配置完成 ≠ 模型可用</h2><p>点击测试连接后，服务端会使用已保存的配置发送一次请求。通过测试后，再开始 AI 开发任务。</p><ol><li>确认模型服务地址可访问</li><li>确认 API Key 具有模型权限</li><li>确认模型支持所选协议与推理强度</li></ol><a href="#/guide">查看上手指南 →</a></aside>
        </div>
      )}
      {result ? <section className={"model-test-result " + (result.ok ? "model-test-success" : "model-test-failed")} role="status"><div><h2>{result.ok ? "连接测试通过" : "连接测试未通过"}</h2><p>{result.message}</p><small>{result.model} · {result.protocol === "responses" ? "Responses API" : "Chat Completions API"} · {(result.latency_ms / 1000).toFixed(1)} 秒</small></div>{result.ok ? <a className="ui-btn ui-btn-primary ui-btn-md" href="#/agent/new">开始 AI 开发 →</a> : <span>检查配置后可再次测试</span>}</section> : null}
    </div>
  );
}
