import { useEffect, useState } from "react";
import { apiBase } from "../../api";
import { ErrorBox, Panel } from "../../components";

const SETTINGS_KEY = "specproof_agent_settings";

interface AgentSettingsState {
  apiBase: string;
  streamPollMs: number;
  diffContext: number;
  maxEventsBuffer: number;
}

const DEFAULTS: AgentSettingsState = {
  apiBase: "",
  streamPollMs: 1000,
  diffContext: 3,
  maxEventsBuffer: 300,
};

export function loadSettings(): AgentSettingsState {
  try {
    const raw = window.localStorage.getItem(SETTINGS_KEY);
    if (!raw) return { ...DEFAULTS };
    return { ...DEFAULTS, ...(JSON.parse(raw) as Partial<AgentSettingsState>) };
  } catch {
    return { ...DEFAULTS };
  }
}

export function saveSettings(state: AgentSettingsState): void {
  try {
    window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(state));
  } catch {
    // storage unavailable; settings stay in component state
  }
}

export default function AgentSettings() {
  const [state, setState] = useState<AgentSettingsState>(() => loadSettings());
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const base = apiBase();
    if (!state.apiBase && base) {
      setState((s) => ({ ...s, apiBase: base }));
    }
  }, [state.apiBase]);

  const persist = () => {
    setError(null);
    setSaved(null);
    if (state.streamPollMs < 100 || state.streamPollMs > 60000) {
      setError("流轮询间隔须在 100-60000 ms 之间");
      return;
    }
    if (state.maxEventsBuffer < 10 || state.maxEventsBuffer > 5000) {
      setError("事件缓冲须在 10-5000 之间");
      return;
    }
    saveSettings(state);
    setSaved("已保存 Saved");
  };

  return (
    <div>
      <div className="page-head">
        <h1>Agent 工作台设置 Settings</h1>
        <div className="page-sub">CONSOLE SETTINGS — 本地存储 (localStorage)</div>
      </div>
      <Panel title="控制台设置">
        <label className="field">API 基址 API base</label>
        <input
          type="text"
          value={state.apiBase}
          placeholder="(默认同源 — 由 verify 控制台共享)"
          onChange={(e) => setState({ ...state, apiBase: e.target.value })}
        />
        <label className="field">SSE 重连轮询 (ms) — 用于降级轮询回退</label>
        <input
          type="number"
          min={100}
          max={60000}
          value={state.streamPollMs}
          onChange={(e) => setState({ ...state, streamPollMs: Number(e.target.value) || 1000 })}
        />
        <label className="field">Diff 上下文行数 Context lines</label>
        <input
          type="number"
          min={0}
          max={10}
          value={state.diffContext}
          onChange={(e) => setState({ ...state, diffContext: Number(e.target.value) || 3 })}
        />
        <label className="field">工具流事件缓冲上限 Max buffered events</label>
        <input
          type="number"
          min={10}
          max={5000}
          value={state.maxEventsBuffer}
          onChange={(e) => setState({ ...state, maxEventsBuffer: Number(e.target.value) || 300 })}
        />
        <div style={{ marginTop: 14, display: "flex", gap: 8 }}>
          <button className="btn" onClick={persist}>
            保存 Save
          </button>
          <button
            className="btn btn-ghost"
            onClick={() => {
              saveSettings(DEFAULTS);
              setState({ ...DEFAULTS });
              setSaved("已重置 Reset to defaults");
            }}
          >
            重置 Reset
          </button>
        </div>
        {saved ? <div className="degraded" style={{ marginTop: 10 }}>{saved}</div> : null}
        <ErrorBox error={error} />
        <div className="muted" style={{ marginTop: 10 }}>
          存储说明: Agent 任务当前由后端进程内存存储 (storage/agent_jobs.py 落地后切换持久化);
          本页设置只影响控制台本地行为。
        </div>
      </Panel>
    </div>
  );
}
